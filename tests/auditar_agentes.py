# -*- coding: utf-8 -*-
"""Auditoría estática de páginas orientadas a agentes (sin navegador).

Analiza el HTML tal como lo recibe un agente que no ejecuta scripts y revisa:
identificadores únicos, referencias ARIA, nombres accesibles únicos de controles y botones, orden de
encabezados, regiones, JSON incrustado, esquemas de herramientas (JSON Schema 2020-12), coherencia entre
cada formulario declarativo de WebMCP y su esquema, coherencia entre la tabla del catálogo y el JSON-LD,
ausencia de alert/confirm/prompt, formatos canónicos, recursos externos y descubribilidad.

Uso:
    python3 tests/auditar_agentes.py                      # index.html y versions/v1.0/index.html
    python3 tests/auditar_agentes.py ruta/a/pagina.html   # una o varias páginas
Requisito: pip install -r requirements-dev.txt (jsonschema).
Sale con código 1 si alguna página tiene errores; los avisos no cambian el código de salida.
"""
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

ROOT = Path(__file__).resolve().parent.parent
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}
CONTROLS = ('input', 'select', 'textarea')
NOT_CONTROL_TYPES = {'hidden', 'submit', 'button', 'reset', 'image'}
REF_ATTRS = ('aria-labelledby', 'aria-describedby', 'aria-controls', 'aria-owns', 'aria-details', 'aria-errormessage',
             'aria-activedescendant', 'for')
NATIVE_PICKERS = {'date', 'datetime-local', 'month', 'week', 'time'}
SITE_FILES = ('index.md', 'llms.txt', 'robots.txt', 'sitemap.xml', '.well-known/api-catalog', 'openapi.yaml')


class Node:
    __slots__ = ('tag', 'attrs', 'children', 'parent', 'line')

    def __init__(self, tag, attrs, parent, line):
        self.tag, self.attrs, self.children, self.parent, self.line = tag, dict(attrs), [], parent, line

    def iter(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.iter()

    def get(self, key, default=None):
        return self.attrs.get(key, default)

    def has(self, key):
        return key in self.attrs

    def ancestors(self):
        node = self.parent
        while node is not None:
            yield node
            node = node.parent

    def raw_text(self):
        return ''.join(c if isinstance(c, str) else c.raw_text() for c in self.children)


class TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node('#document', {}, None, 0)
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, [(k, '' if v is None else v) for k, v in attrs], self.stack[-1], self.getpos()[0])
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        node = Node(tag, [(k, '' if v is None else v) for k, v in attrs], self.stack[-1], self.getpos()[0])
        self.stack[-1].children.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def norm(s):
    return re.sub(r'\s+', ' ', s or '').strip()


def name_text(node):
    """Texto que aporta un subárbol a un nombre accesible (omite aria-hidden, scripts y controles)."""
    if isinstance(node, str):
        return node
    if node.get('aria-hidden') == 'true' or node.tag in ('script', 'style', 'template') or node.tag in CONTROLS:
        return ''
    return ''.join(name_text(c) for c in node.children)


class Page:
    def __init__(self, path):
        self.path = path
        self.html = path.read_text(encoding='utf-8')
        builder = TreeBuilder()
        builder.feed(self.html)
        builder.close()
        self.root = builder.root
        self.nodes = list(self.root.iter())
        self.by_id = {}
        self.dup_ids = []
        for n in self.nodes:
            if n.has('id'):
                if n.get('id') in self.by_id:
                    self.dup_ids.append(n)
                else:
                    self.by_id[n.get('id')] = n
        self.labels_for = {}
        for n in self.nodes:
            if n.tag == 'label' and n.get('for'):
                self.labels_for.setdefault(n.get('for'), []).append(n)
        self.errors, self.warnings, self.stats = [], [], {}

    def error(self, msg, node=None):
        self.errors.append(f'línea {node.line}: {msg}' if node is not None else msg)

    def warn(self, msg, node=None):
        self.warnings.append(f'línea {node.line}: {msg}' if node is not None else msg)

    def find_all(self, tag=None, **attrs):
        for n in self.nodes:
            if n.tag == '#document' or (tag and n.tag != tag):
                continue
            if all((n.get(k.replace('_', '-')) == v) if v is not True else n.has(k.replace('_', '-'))
                   for k, v in attrs.items()):
                yield n

    def acc_name(self, n):
        ids = n.get('aria-labelledby')
        if ids:
            return norm(' '.join(norm(name_text(self.by_id[i])) for i in ids.split() if i in self.by_id))
        if norm(n.get('aria-label')):
            return norm(n.get('aria-label'))
        if n.tag in CONTROLS:
            labels = list(self.labels_for.get(n.get('id'), [])) if n.get('id') else []
            wrapper = next((a for a in n.ancestors() if a.tag == 'label'), None)
            if wrapper is not None and wrapper not in labels:
                labels.append(wrapper)
            text = norm(' '.join(name_text(l) for l in labels))
            return text or norm(n.get('title')) or ''
        if n.tag == 'button':
            return norm(name_text(n)) or norm(n.get('title'))
        if n.tag == 'fieldset':
            legend = next((c for c in n.children if isinstance(c, Node) and c.tag == 'legend'), None)
            return norm(name_text(legend)) if legend is not None else ''
        return norm(name_text(n))


def is_control(n):
    return n.tag in CONTROLS and not (n.tag == 'input' and n.get('type', 'text').lower() in NOT_CONTROL_TYPES)


def audit(page):
    # 1. Identificadores
    for n in page.dup_ids:
        page.error(f'id duplicado «{n.get("id")}»', n)
    page.stats['ids'] = len(page.by_id)

    # 2. Referencias ARIA y de etiquetas
    for n in page.nodes:
        for attr in REF_ATTRS:
            if n.tag == '#document' or not n.get(attr):
                continue
            if attr == 'for' and n.tag not in ('label', 'output'):
                continue
            for ref in n.get(attr).split():
                if ref not in page.by_id:
                    page.error(f'{attr} apunta a un id inexistente «{ref}»', n)

    # 3. Nombres accesibles de controles y botones (no vacíos y únicos)
    controls = [n for n in page.nodes if is_control(n)]
    buttons = [n for n in page.nodes if n.tag == 'button']
    for group, label in ((controls, 'control'), (buttons, 'botón')):
        names = {}
        for n in group:
            name = page.acc_name(n)
            if not name:
                page.error(f'{label} sin nombre accesible ({n.tag}{"#" + n.get("id") if n.get("id") else ""})', n)
            else:
                names.setdefault(name, []).append(n)
        for name, nodes in names.items():
            if len(nodes) > 1:
                page.error(f'{len(nodes)} {label}es comparten el nombre accesible «{name}»'.replace('botónes', 'botones'), nodes[1])
    page.stats['controls'] = len(controls)
    page.stats['buttons'] = len(buttons)

    # 4. Encabezados
    headings = [n for n in page.nodes if re.fullmatch(r'h[1-6]', n.tag)]
    levels = [int(n.tag[1]) for n in headings]
    if levels.count(1) != 1:
        page.error(f'debe haber exactamente un h1 (hay {levels.count(1)})')
    if levels and levels[0] != 1:
        page.error('el primer encabezado no es h1', headings[0])
    for prev, (n, lvl) in zip(levels, list(zip(headings, levels))[1:]):
        if lvl > prev + 1:
            page.error(f'salto de h{prev} a h{lvl} («{norm(name_text(n))}»)', n)
    for n in headings:
        if not norm(name_text(n)):
            page.error('encabezado vacío', n)
    page.stats['headings'] = len(headings)

    # 5. Regiones de referencia
    mains = list(page.find_all('main'))
    if len(mains) != 1:
        page.error(f'debe haber exactamente un <main> (hay {len(mains)})')
    if not any(n for n in page.find_all('header') if not any(a.tag in ('main', 'section', 'article') for a in n.ancestors())):
        page.error('falta la cabecera de la página (<header> fuera de <main>)')
    if not any(n for n in page.find_all('footer') if not any(a.tag in ('main', 'section', 'article') for a in n.ancestors())):
        page.error('falta el pie de página (<footer> fuera de <main>)')
    navs = list(page.find_all('nav'))
    for n in navs:
        if len(navs) > 1 and not (n.get('aria-label') or n.get('aria-labelledby')):
            page.error('hay varias <nav> y esta no tiene nombre', n)
    for n in page.find_all('section'):
        if not (n.get('aria-labelledby') or n.get('aria-label')):
            page.warn(f'<section id="{n.get("id", "")}"> sin nombre: no será una región', n)

    # 6. JSON incrustado
    data = {}
    for n in page.find_all('script'):
        kind = n.get('type', '')
        if kind in ('application/ld+json', 'application/json'):
            try:
                data.setdefault(kind, []).append((n, json.loads(n.raw_text())))
            except json.JSONDecodeError as exc:
                page.error(f'JSON inválido en <script type="{kind}">: {exc}', n)
    tools_node = page.by_id.get('agent-tools')
    tools = None
    if tools_node is None:
        page.error('falta el bloque de esquemas de herramientas (#agent-tools)')
    else:
        tools = next((d for n, d in data.get('application/json', []) if n is tools_node), None)

    # 7. Coherencia entre la tabla del catálogo y el JSON-LD
    rows = [n for n in page.nodes if n.tag == 'tr' and n.get('data-sku')]
    if not rows:
        page.error('el catálogo no está en el HTML estático (no hay filas con data-sku)')
    item_lists = [g for _, d in data.get('application/ld+json', [])
                  for g in (d.get('@graph', [d]) if isinstance(d, dict) else []) if g.get('@type') == 'ItemList']
    if not item_lists:
        page.error('el JSON-LD no tiene un ItemList con el catálogo')
    for il in item_lists:
        items = [x.get('item', {}) for x in il.get('itemListElement', [])]
        if il.get('numberOfItems') != len(items) or len(items) != len(rows):
            page.error(f'ItemList: numberOfItems={il.get("numberOfItems")}, elementos={len(items)}, filas={len(rows)}')
        by_sku = {r.get('data-sku'): r for r in rows}
        for it in items:
            r = by_sku.get(it.get('sku'))
            offer = it.get('offers', {})
            if r is None:
                page.error(f'el JSON-LD describe {it.get("sku")} pero no hay fila en la tabla')
                continue
            if r.get('data-price-usd') != offer.get('price') or str(offer.get('inventoryLevel', {}).get('value')) != r.get('data-stock') \
                    or r.get('data-name') != it.get('name'):
                page.error(f'{it.get("sku")}: la tabla y el JSON-LD no coinciden en nombre, precio o existencias', r)
            if offer.get('priceCurrency') != 'USD' or not re.fullmatch(r'\d+\.\d{2}', offer.get('price', '')):
                page.error(f'{it.get("sku")}: precio sin punto decimal o moneda distinta de USD')
    for r in rows:
        if not re.fullmatch(r'[A-Z]{2}', r.get('data-origin', '')):
            page.error(f'{r.get("data-sku")}: origen sin código ISO 3166-1 alfa-2', r)

    # 8. Esquemas de herramientas (JSON Schema 2020-12)
    valid_schemas = 0
    by_name = {}
    if tools:
        for t in tools.get('tools', []):
            name = t.get('name')
            by_name[name] = t
            missing = [k for k in ('name', 'description', 'inputSchema') if not t.get(k)]
            if missing:
                page.error(f'herramienta {name}: faltan {", ".join(missing)}')
                continue
            try:
                Draft202012Validator.check_schema(t['inputSchema'])
            except SchemaError as exc:
                page.error(f'herramienta {name}: esquema inválido según JSON Schema 2020-12: {exc.message}')
                continue
            if t['inputSchema'].get('type') != 'object':
                page.error(f'herramienta {name}: inputSchema debe ser de tipo object')
                continue
            for key, value in t.get('annotations', {}).items():
                if not isinstance(value, bool):
                    page.error(f'herramienta {name}: la anotación {key} no es booleana')
            valid_schemas += 1
        confirm = by_name.get('confirm_order')
        if confirm:
            if confirm.get('annotations', {}).get('consequentialHint') is not True:
                page.error('confirm_order debe declarar consequentialHint: true')
            if confirm.get('binding', {}).get('autosubmit') is not False:
                page.error('confirm_order no puede enviarse automáticamente (binding.autosubmit debe ser false)')
            if confirm.get('binding', {}).get('javascript') is not False:
                page.error('confirm_order no debe estar disponible en la API de script')
    page.stats['schemas'] = valid_schemas

    # 9. Formularios declarativos frente a sus esquemas
    coherent = 0
    forms = [n for n in page.nodes if n.tag == 'form' and n.has('toolname')]
    declared = {name for name, t in by_name.items() if t.get('binding', {}).get('webmcp') == 'declarative'}
    for form in forms:
        before = len(page.errors)
        tname = form.get('toolname')
        tool = by_name.get(tname)
        declared.discard(tname)
        if tool is None:
            page.error(f'el formulario #{form.get("id")} declara la herramienta «{tname}», que no está en #agent-tools', form)
            continue
        binding = tool.get('binding', {})
        if binding.get('webmcp') != 'declarative' or binding.get('form') != f'#{form.get("id")}':
            page.error(f'{tname}: binding no apunta al formulario #{form.get("id")}', form)
        if norm(form.get('tooldescription')) != norm(tool.get('description')):
            page.error(f'{tname}: tooldescription difiere de la descripción del esquema', form)
        if form.has('toolautosubmit') != (binding.get('autosubmit', True) is not False):
            page.error(f'{tname}: toolautosubmit no coincide con binding.autosubmit', form)
        schema = tool['inputSchema']
        props = schema.get('properties', {})
        required = set(schema.get('required', []))
        fields = {}
        for n in form.iter():
            if is_control(n) and n.get('name'):
                fields.setdefault(n.get('name'), []).append(n)
        if set(fields) != set(props):
            page.error(f'{tname}: campos del formulario {sorted(fields)} ≠ propiedades del esquema {sorted(props)}', form)
        for fname, nodes in fields.items():
            prop = props.get(fname)
            if prop is None:
                continue
            first = nodes[0]
            ftype = first.get('type', 'text').lower() if first.tag == 'input' else first.tag
            enum = prop.get('enum')
            if ftype == 'radio':
                values = [n.get('value') for n in nodes]
                if enum is not None and values != enum:
                    page.error(f'{tname}.{fname}: valores de los botones de opción {values} ≠ enum {enum}', first)
            elif first.tag == 'select':
                values = [o.get('value', norm(o.raw_text())) for o in first.iter() if o.tag == 'option']
                if enum is not None and values != enum:
                    page.error(f'{tname}.{fname}: opciones {values} ≠ enum {enum}', first)
            elif ftype == 'checkbox' and prop.get('type') != 'boolean':
                page.error(f'{tname}.{fname}: casilla de verificación con tipo {prop.get("type")}', first)
            elif ftype == 'number' and prop.get('type') not in ('number', 'integer'):
                page.error(f'{tname}.{fname}: campo numérico con tipo {prop.get("type")}', first)
            if ftype == 'email' and prop.get('format') != 'email':
                page.warn(f'{tname}.{fname}: campo de correo sin format: email en el esquema', first)
            if first.get('pattern') and prop.get('pattern') and first.get('pattern') != prop['pattern'].strip('^$'):
                page.error(f'{tname}.{fname}: el patrón del campo difiere del esquema', first)
            is_req = any(n.has('required') for n in nodes)
            if fname in required and not is_req:
                page.error(f'{tname}.{fname}: obligatorio en el esquema pero no en el formulario', first)
            if is_req and fname not in required and 'default' not in prop:
                page.error(f'{tname}.{fname}: obligatorio en el formulario pero no en el esquema (y sin valor por omisión)', first)
            if first.get('toolparamdescription') and norm(first.get('toolparamdescription')) != norm(prop.get('description')):
                page.warn(f'{tname}.{fname}: toolparamdescription distinto de la descripción del esquema', first)
        if len(page.errors) == before:
            coherent += 1
    for name in sorted(declared):
        page.error(f'{name} se declara como herramienta declarativa pero no hay formulario con toolname="{name}"')
    page.stats['forms'] = coherent
    page.stats['forms_total'] = len(forms)

    # 10. Diálogos del navegador
    for n in page.find_all('script'):
        if n.get('type', 'text/javascript') not in ('text/javascript', 'module', ''):
            continue
        code = n.raw_text()
        for m in re.finditer(r'(?<![\w$.])(alert|confirm|prompt)\s*\(|\bwindow\.(alert|confirm|prompt)\s*\(', code):
            line = n.line + code[:m.start()].count('\n')
            page.error(f'uso de {m.group(1) or m.group(2)}() (línea {line}): los diálogos bloquean a los agentes')

    # 11. Formatos canónicos (R4)
    for n in page.find_all('input'):
        if n.get('type', '').lower() in NATIVE_PICKERS:
            page.error(f'selector nativo <input type="{n.get("type")}">: los formatos canónicos se escriben, no se eligen', n)
        if 'date' in n.get('name', '') and n.get('type', 'text') == 'text' and not n.get('pattern'):
            page.error(f'el campo de fecha «{n.get("name")}» no declara su patrón', n)

    # 12. Recursos externos
    for n in page.find_all('script'):
        src = n.get('src', '')
        if re.match(r'(https?:)?//', src):
            page.error(f'script de otro origen: {src}', n)
    for n in page.find_all('link'):
        rel, href = n.get('rel', ''), n.get('href', '')
        if 'stylesheet' in rel.split() and re.match(r'(https?:)?//', href):
            if not href.startswith('https://fonts.googleapis.com/') or 'display=optional' not in href:
                page.error(f'hoja de estilos externa no permitida o sin display=optional: {href}', n)
    for n in page.nodes:
        for attr in ('src', 'srcset', 'poster'):
            if n.tag not in ('script',) and re.match(r'(https?:)?//', n.get(attr, '') or ''):
                page.error(f'recurso externo en {n.tag}[{attr}]: {n.get(attr)}', n)

    # 13. Degradación y descubribilidad (R8, R9)
    if not list(page.find_all('noscript')):
        page.warn('no hay aviso <noscript> para quien lee sin JavaScript')
    links = [(n.get('rel', ''), n.get('type', '')) for n in page.find_all('link')]
    if not any('alternate' in r.split() and t == 'text/markdown' for r, t in links):
        page.error('falta <link rel="alternate" type="text/markdown">')
    for rel in ('service-desc', 'api-catalog'):
        if not any(rel in r.split() for r, _ in links):
            page.error(f'falta <link rel="{rel}">')
    if not data.get('application/ld+json'):
        page.error('falta el JSON-LD')

    # 14. Archivos del sitio (si se publican junto a la página)
    present = [f for f in SITE_FILES if (page.path.parent / f).exists()]
    page.stats['site_files'] = present
    if (page.path.parent / 'openapi.yaml').exists():
        import yaml  # solo si hay archivos del sitio
        doc = yaml.safe_load((page.path.parent / 'openapi.yaml').read_text(encoding='utf-8'))
        if not str(doc.get('openapi', '')).startswith('3.1'):
            page.error('openapi.yaml no declara OpenAPI 3.1')


def report(page):
    s = page.stats
    rel = page.path.relative_to(ROOT) if page.path.is_relative_to(ROOT) else page.path
    print(f'\nAuditoría estática: {rel}')
    print(f'  {len(page.errors)} errores, {len(page.warnings)} avisos')
    print(f'  {s["ids"]} identificadores únicos; {s["controls"]} controles de formulario y {s["buttons"]} botones con '
          f'nombres accesibles únicos; {s["headings"]} encabezados sin niveles omitidos; {s["forms"]} de '
          f'{s["forms_total"]} formularios declarativos coherentes con sus esquemas; {s["schemas"]} esquemas de herramientas válidos')
    if s['site_files']:
        print(f'  Archivos del sitio revisados: {", ".join(s["site_files"])}')
    else:
        print('  Archivos del sitio (index.md, llms.txt, robots.txt, sitemap.xml, api-catalog, openapi.yaml): '
              'no están junto a la página; se omite su revisión.')
    for e in page.errors:
        print(f'  ERROR  {e}')
    for w in page.warnings:
        print(f'  aviso  {w}')


def main(argv):
    paths = [Path(a) if Path(a).is_absolute() else ROOT / a for a in argv] or \
        [ROOT / 'index.html', ROOT / 'versions' / 'v1.0' / 'index.html']
    total_errors = 0
    for path in paths:
        page = Page(path)
        audit(page)
        report(page)
        total_errors += len(page.errors)
    return 1 if total_errors else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
