# -*- coding: utf-8 -*-
"""Genera Grano Claro 1.1 (index.html) a partir de la versión 1.0 (versions/v1.0/index.html).

Regenera desde data.py todo lo que depende del catálogo (filas de la tabla, JSON-LD, esquemas de
herramientas, filtros y guía de variedades) y aplica reemplazos exactos sobre la 1.0: cada uno debe
coincidir una sola vez, de modo que el programa se detiene si la base cambia.

Uso:
    python3 build/build.py             # escribe index.html
    python3 build/build.py --artifact  # además, dist/grano-claro.artifact.html (fragmento sin <html>,
                                       # para publicarlo como artefacto de claude.ai)
"""
import hashlib
import html
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from data import P, ROAST_ES, VARIETIES, ORIGINS, CR, SOURCES, GUIDE, DATE_ISO, DATE_ES, VERSION, name  # noqa: E402

SRC = ROOT / 'versions' / 'v1.0' / 'index.html'
V10_SHA256 = '79e8af1cf9b05cf95440ac69f1bfb24b11752b451511d22adbd46782908cf340'
src = SRC.read_text(encoding='utf-8').replace('\r\n', '\n')
assert hashlib.sha256(src.encode('utf-8')).hexdigest() == V10_SHA256, 'versions/v1.0/index.html no es la versión 1.0 publicada'
E = html.escape


def rep(s, old, new, count=1):
    n = s.count(old)
    assert n == count, f'{n} coincidencias para: {old[:90]!r}'
    return s.replace(old, new)


def block(s, start, end, new):
    """Reemplaza desde `start` (único) hasta el primer `end` posterior, ambos incluidos."""
    assert s.count(start) == 1, start
    i = s.index(start)
    j = s.index(end, i) + len(end)
    return s[:i] + new + s[j:]


def between(s, start, end):
    i = s.index(start) + len(start)
    return s[i:s.index(end, i)]


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))


# ---------------------------------------------------------------- partes de la versión 1.0
head_links = between(src, '<meta name="color-scheme" content="light dark">\n', '<script type="application/ld+json">\n')
ld_src = between(src, '<script type="application/ld+json">\n', '\n</script>')
tools_src = between(src, '<script type="application/json" id="agent-tools">\n', '\n</script>')
css = between(src, '<style>\n', '</style>')
body = between(src, '<body>\n', '\n<script>\n(() => {')
js = '(() => {' + between(src, '\n<script>\n(() => {', '\n</script>\n</body>')
assert dumps(json.loads(tools_src)) == tools_src and dumps(json.loads(ld_src)) == ld_src

# Los seis cafés de la 1.0 no cambian de precio, peso ni existencias.
orig_rows = dict(re.findall(r'<tr id="product-(GC-\d{3})"([^>]*)>', body))
assert len(orig_rows) == 6
for p in P[:6]:
    a = dict(re.findall(r'data-([a-z-]+)="([^"]*)"', orig_rows[p['sku']]))
    assert (a['name'], a['origin'], a['origin-name'], a['process'], a['roast'], int(a['weight-g']), a['price-usd'],
            int(a['stock'])) == (name(p), p['origin'], p['country'], p['process'], p['roast'], p['weight'], p['price'],
                                 p['stock']), p['sku']


# ---------------------------------------------------------------- generadores
def bags(n):
    return f"{n} {'bolsa' if n == 1 else 'bolsas'}"


def join_es(items):
    return items[0] if len(items) == 1 else ', '.join(items[:-1]) + ' y ' + items[-1]


def variety_text(p):
    v = p['varieties']
    if v == ['Variedades locales']:
        return 'variedades locales'
    return ('variedad ' if len(v) == 1 else 'variedades ') + join_es(v)


def description(p):
    region = f"región {p['region']}" + (f" ({p['alt']} m)" if p['alt'] else '')
    notes = p['notes'][0].lower() + p['notes'][1:]
    return (f"Café de especialidad de {p['country']}, {region}, {variety_text(p)}, proceso {p['process'].lower()}, "
            f"tueste {ROAST_ES[p['roast']].lower()}. Bolsa de {p['weight']} g. Notas de cata: {notes}")


def row(p):
    s = p['sku']
    out = p['stock'] <= 0
    attrs = [f'id="product-{s}"', 'class="is-out"' if out else '', f'data-sku="{s}"', f'data-name="{E(name(p))}"',
             f'data-origin="{p["origin"]}"', f'data-origin-name="{E(p["country"])}"', f'data-region="{E(p["region"])}"',
             f'data-varieties="{E("|".join(p["varieties"]))}"',
             f'data-altitude-m="{p["alt"]}"' if p['alt'] else '', f'data-process="{E(p["process"])}"',
             f'data-roast="{p["roast"]}"', f'data-weight-g="{p["weight"]}"', f'data-price-usd="{p["price"]}"',
             f'data-stock="{p["stock"]}"', f'data-notes="{E(p["notes"])}"']
    sub = f'<span class="cell-sub">Región {E(p["region"])}, {p["alt"]}&nbsp;m</span>' if p['alt'] else ''
    stock = '<data value="0">Agotado</data>' if out else f'<data value="{p["stock"]}">{bags(p["stock"])}</data>'
    t = '              '
    return (f'            <tr {" ".join(a for a in attrs if a)}>\n'
            f'{t}<td class="pick"><label class="pick-hit" for="sku-{s}"><input type="radio" id="sku-{s}" name="sku" value="{s}" '
            f'required{" disabled" if out else ""} aria-labelledby="label-{s} origin-{s} weight-{s}" '
            f'aria-describedby="variety-{s} price-{s} stock-{s} err-sku" toolparamdescription="SKU del café elegido."></label></td>\n'
            f'{t}<td><code>{s}</code></td>\n'
            f'{t}<th scope="row" id="name-{s}"><label id="label-{s}" for="sku-{s}">{E(p["short"])}</label>{sub}</th>\n'
            f'{t}<td id="origin-{s}">{E(p["country"])} ({p["origin"]})</td>\n'
            f'{t}<td id="variety-{s}">{E(", ".join(p["varieties"]))}</td>\n'
            f'{t}<td>{E(p["process"])}</td>\n'
            f'{t}<td>{ROAST_ES[p["roast"]]}</td>\n'
            f'{t}<td class="num" id="weight-{s}"><data value="{p["weight"]}">{p["weight"]} g</data></td>\n'
            f'{t}<td class="num" id="price-{s}"><data value="{p["price"]}">USD {p["price"]}</data></td>\n'
            f'{t}<td class="num" id="stock-{s}">{stock}</td>\n'
            f'            </tr>\n')


def product_ld(i, p):
    url = f'https://granoclaro.example/#product-{p["sku"]}'
    props = [{'@type': 'PropertyValue', 'name': 'proceso', 'value': p['process'].lower()},
             {'@type': 'PropertyValue', 'name': 'tueste', 'value': p['roast']}]
    props += [{'@type': 'PropertyValue', 'name': 'variedad', 'value': v} for v in p['varieties']]
    props.append({'@type': 'PropertyValue', 'name': 'región', 'value': p['region']})
    if p['alt']:
        props.append({'@type': 'PropertyValue', 'name': 'altitud', 'value': p['alt'], 'unitCode': 'MTR', 'unitText': 'm'})
    props.append({'@type': 'PropertyValue', 'name': 'notas de cata', 'value': p['notes']})
    return {'@type': 'ListItem', 'position': i, 'item': {
        '@type': 'Product', '@id': url, 'sku': p['sku'], 'name': name(p), 'description': description(p),
        'brand': {'@type': 'Brand', 'name': 'Grano Claro'},
        'countryOfOrigin': {'@type': 'Country', 'name': p['country'], 'identifier': p['origin']},
        'weight': {'@type': 'QuantitativeValue', 'value': p['weight'], 'unitCode': 'GRM', 'unitText': 'g'},
        'additionalProperty': props,
        'offers': {'@type': 'Offer', 'url': url, 'price': p['price'], 'priceCurrency': 'USD',
                   'availability': 'https://schema.org/InStock' if p['stock'] > 0 else 'https://schema.org/OutOfStock',
                   'inventoryLevel': {'@type': 'QuantitativeValue', 'value': p['stock']},
                   'seller': {'@id': 'https://granoclaro.example/#store'}}}}


# ---------------------------------------------------------------- JSON-LD
ld = json.loads(ld_src)
item_list = next(g for g in ld['@graph'] if g['@type'] == 'ItemList')
old_items = {x['item']['sku']: x['item'] for x in item_list['itemListElement']}
item_list['numberOfItems'] = len(P)
item_list['dateModified'] = DATE_ISO
item_list['itemListElement'] = [product_ld(i, p) for i, p in enumerate(P, 1)]
for x in item_list['itemListElement'][:6]:  # mismos datos comerciales que en la 1.0
    o = old_items[x['item']['sku']]
    for k in ('@id', 'name', 'brand', 'countryOfOrigin', 'weight', 'offers'):
        assert x['item'][k] == o[k], (x['item']['sku'], k)
    assert all(pv in x['item']['additionalProperty'] for pv in o['additionalProperty'])
ld_out = dumps(ld)

# ---------------------------------------------------------------- esquemas de herramientas
SEARCH_DESC = ('Busca y filtra el catálogo de cafés por texto, país de origen, variedad, tueste, precio máximo en USD y '
               'disponibilidad. Devuelve los cafés que coinciden, con SKU, variedad, precio y bolsas disponibles, y aplica '
               'el mismo filtro en la página.')
QUERY_DESC = 'Texto libre: nombre, región, país, variedad, proceso o notas de cata. Vacío significa sin filtro de texto.'
VARIETY_DESC = 'Variedad de café, por ejemplo Villa Sarchí o Geisha. Vacío significa cualquier variedad.'
tools = json.loads(tools_src)
tools['version'] = VERSION
sp = tools['tools'][0]
assert sp['name'] == 'search_products'
old_search_desc = sp['description']
sp['description'] = SEARCH_DESC
props = sp['inputSchema']['properties']
props['query']['description'] = QUERY_DESC
props['origin']['anyOf'] = [props['origin']['anyOf'][0]] + [
    {'type': 'string', 'const': c, 'title': n} for c, n in ORIGINS]
props['origin']['enum'] = [''] + [c for c, _ in ORIGINS]
variety = {'type': 'string', 'description': VARIETY_DESC,
           'anyOf': [{'type': 'string', 'const': '', 'title': 'Cualquier variedad'}] +
                    [{'type': 'string', 'const': v, 'title': v} for v in VARIETIES],
           'enum': [''] + VARIETIES}
sp['inputSchema']['properties'] = {k: v for k, v in [('query', props['query']), ('origin', props['origin']),
                                                       ('variety', variety)] +
                                   [(k, props[k]) for k in ('roast', 'max_price_usd', 'in_stock_only')]}
add = tools['tools'][1]
assert add['name'] == 'add_to_cart'
sku = add['inputSchema']['properties']['sku']
sku['anyOf'] = [{'type': 'string', 'const': p['sku'],
                 'title': f"{name(p)}, USD {p['price']}" + (' (agotado)' if p['stock'] <= 0 else '')} for p in P]
sku['enum'] = [p['sku'] for p in P]
tools_out = dumps(tools)

# ---------------------------------------------------------------- CSS
css = rep(css, '  --select: #e8edf8;\n  --font-text',
          '  --select: #e8edf8;\n  --origin: #7b4a1f;\n  --origin-bg: #f7efe6;\n  --font-text')
css = rep(css, '    --select: #1a2a4d;\n  }\n}',
          '    --select: #1a2a4d;\n    --origin: #e3b98f;\n    --origin-bg: #2a1f16;\n    color-scheme: dark;\n  }\n}')
css = rep(css, '  --select: #1a2a4d;\n}',
          '  --select: #1a2a4d;\n  --origin: #e3b98f;\n  --origin-bg: #2a1f16;\n  color-scheme: dark;\n}')
css = rep(css, 'h1, h2, h3 { margin: 0; line-height: 1.2; font-weight: 700; }',
          'h1, h2, h3, h4, h5 { margin: 0; line-height: 1.2; font-weight: 700; }')
css = rep(css, '#catalog-table { min-width: 47rem; }', '#catalog-table { min-width: 54rem; }')
css = rep(css, 'button.small { min-height: 2.25rem;', 'button.small { min-height: 2.75rem;')  # R3: 44 px
css = rep(css, '@media (max-width: 40rem) {\n', (HERE / 'new.css').read_text(encoding='utf-8') + '\n@media (max-width: 40rem) {\n')
css = rep(css, '  .row-end .field { width: 100%; }\n}',
          '  .row-end .field { width: 100%; }\n' + (HERE / 'new-mobile.css').read_text(encoding='utf-8') + '}')

# ---------------------------------------------------------------- HTML
T = {}
for part in re.split(r'^@@ ', (HERE / 'parts.html').read_text(encoding='utf-8'), flags=re.M)[1:]:
    key, _, content = part.partition('\n')
    T[key.strip()] = content.rstrip('\n')

WALK_JSON = {  # se muestran tal cual en el recorrido
    'search': dumps({'origin': 'CR', 'in_stock_only': True}),
    'add': dumps({'sku': 'GC-007', 'grind': 'filter', 'quantity': 2}),
}


def fill(t):
    t = t.replace('@@N@@', str(len(P))).replace('@@NCR@@', str(len(CR)))
    t = t.replace('@@WALK_SEARCH@@', E(WALK_JSON['search'], quote=False)).replace('@@WALK_ADD@@', E(WALK_JSON['add'], quote=False))
    for k, v in SOURCES.items():
        t = t.replace(f'@@SRC_{k}@@', v)
    return t


lots = {}
for p in CR:
    for v in p['varieties']:
        lots.setdefault(v, []).append(p)
guide_items = []
for v, text in GUIDE:
    assert v in lots, v
    where = join_es([f'{E(p["short"])} ({p["sku"]})' for p in lots[v]])
    guide_items.append(f'      <dt>{E(v)}</dt><dd>{E(text, quote=False)} <span class="guide-lot">En la tienda: {where}.</span></dd>')
assert sorted(lots) == sorted(v for v, _ in GUIDE), 'cada variedad de Costa Rica necesita su entrada en la guía'
assert len({p['region'] for p in CR}) == len(CR) == len(GUIDE) == 7

body = rep(body, '<div class="page">', '<div class="page" lang="es">')
body = block(body, '<header class="box box--header" id="top">', '</header>', fill(T['header']))
body = block(body, '<section class="box" id="for-agents"', '</section>', fill(T['for-agents']) + '\n\n' + fill(T['console']))
body = rep(body, '<p class="prose">6 cafés de especialidad en bolsas selladas.',
           f'<p class="prose">{len(P)} cafés de especialidad en bolsas selladas, {len(CR)} de ellos de Costa Rica.')
body = rep(body, f'tooldescription="{old_search_desc}"', f'tooldescription="{E(SEARCH_DESC)}"')
body = rep(body, 'toolparamdescription="Texto libre: nombre, región, país o proceso. Vacío significa sin filtro de texto."',
           f'toolparamdescription="{E(QUERY_DESC)}"')
body = rep(body, '<span class="hint" id="f-query-hint">Nombre, región, país o proceso. Ejemplo: natural.</span>',
           '<span class="hint" id="f-query-hint">Nombre, región, país, variedad, proceso o notas. Ejemplo: honey.</span>')
origin_opts = '\n'.join(f'          <option value="{c}">{E(n)} ({c})</option>' for c, n in ORIGINS)
body = block(body, '          <option value="">Cualquier origen</option>', '<option value="KE">Kenia (KE)</option>',
             '          <option value="">Cualquier origen</option>\n' + origin_opts)
variety_opts = '\n'.join(f'          <option value="{E(v)}">{E(v)}</option>' for v in VARIETIES)
body = rep(body, '<span class="field-error" id="err-origin" data-error-for="origin" hidden></span>\n      </div>\n',
           '<span class="field-error" id="err-origin" data-error-for="origin" hidden></span>\n      </div>\n' +
           T['variety-field'].replace('@@VARIETY_DESC@@', E(VARIETY_DESC)).replace('@@VARIETY_OPTIONS@@', variety_opts) + '\n')
body = rep(body, 'Mostrando 6 de 6 cafés.', f'Mostrando {len(P)} de {len(P)} cafés.')
body = rep(body, '<legend>Café <span class="hint">(marque una fila)</span></legend>',
           '<legend>Café <span class="hint agent-only">(marque una fila)</span>'
           '<span class="hint human-only" id="pick-hint-cards" hidden>(elija una tarjeta)</span></legend>')
body = rep(body, '<div class="table-wrap">\n        <table id="catalog-table">',
           '<div class="table-wrap agent-only" id="catalog-table-wrap">\n        <table id="catalog-table">')
body = rep(body, '<caption>6 cafés. Precio por bolsa en USD, impuestos incluidos.</caption>',
           f'<caption>{len(P)} cafés, {len(CR)} de Costa Rica. Precio por bolsa en USD, impuestos incluidos.</caption>')
body = rep(body, '              <th scope="col">Origen</th>\n',
           '              <th scope="col">Origen</th>\n              <th scope="col">Variedad</th>\n')
i = body.index('<tbody>\n', body.index('<table id="catalog-table">')) + len('<tbody>\n')
j = body.index('          </tbody>', i)
body = body[:i] + ''.join(row(p) for p in P) + body[j:]
body = rep(body, 'Use «Quitar filtros» para ver los 6.</p>\n',
           f'Use «Quitar filtros» para ver los {len(P)}.</p>\n' + T['cards'] + '\n')
body = rep(body, '    <p class="local-result below-result" id="add-result"></p>\n  </form>\n</section>',
           '    <p class="local-result below-result" id="add-result"></p>\n  </form>\n\n' +
           fill(T['guide']).replace('@@GUIDE_ITEMS@@', '\n'.join(guide_items)) + '\n</section>')
body = rep(body, 'Escribir el total es la prueba de que se revisó.</p>\n',
           'Escribir el total es la prueba de que se revisó.</p>\n' + T['confirm-note'] + '\n')
body = rep(body, '<h2 id="policies-title">Políticas para agentes</h2>',
           '<h2 id="policies-title">Políticas<span class="agent-only"> para agentes</span></h2>')
body = rep(body, '<dt>Identificación</dt><dd>', '<dt class="agent-only">Identificación</dt><dd class="agent-only">')
body = rep(body, 'Catálogo actualizado el <time datetime="2026-10-06">6 de octubre de 2026</time>. Interfaz para agentes, versión 1.0.',
           f'Catálogo actualizado el <time datetime="{DATE_ISO}">{DATE_ES}</time>. Interfaz para agentes, versión {VERSION}.')
assert 'GC-006</code>' not in body.split('id="for-agents"')[1].split('</section>')[0]

# ---------------------------------------------------------------- JavaScript
J = {}
for part in re.split(r'^//@@ ', (HERE / 'parts.js').read_text(encoding='utf-8'), flags=re.M)[1:]:
    key, _, content = part.partition('\n')
    J[key.strip()] = content.rstrip('\n')

js = rep(js, "  const STORAGE_KEY = 'granoclaro:v1';\n", "  const STORAGE_KEY = 'granoclaro:v1';\n  const MODE_KEY = 'granoclaro:modo';\n")
js = rep(js, '  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));\n',
         '  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));\n  const root = document.documentElement;\n')
js = rep(js, """    catalog.set(d.sku, {
      sku: d.sku, name: d.name, origin: d.origin, origin_name: d.originName, process: d.process,
      roast: d.roast, weight_g: Number(d.weightG), price_cents: toCents(d.priceUsd), stock: Number(d.stock)
    });
  });
""", """    catalog.set(d.sku, {
      sku: d.sku, name: d.name, short: d.name.split(',')[0], origin: d.origin, origin_name: d.originName,
      region: d.region || '', varieties: d.varieties ? d.varieties.split('|') : [], altitude_m: d.altitudeM ? Number(d.altitudeM) : null,
      process: d.process, roast: d.roast, weight_g: Number(d.weightG), price_cents: toCents(d.priceUsd), stock: Number(d.stock), notes: d.notes || ''
    });
  });
  const VARIETIES = Array.from(new Set(Array.from(catalog.values()).flatMap((p) => p.varieties))).sort((a, b) => a.localeCompare(b, 'es'));
""")
js = rep(js, """  const productView = (p) => ({
    sku: p.sku, name: p.name, origin: p.origin, origin_name: p.origin_name, process: p.process,
    roast: p.roast, roast_label: ROASTS[p.roast], weight_g: p.weight_g,
    price_usd: money(p.price_cents), stock: p.stock, available: p.stock > 0
  });""", """  const productView = (p) => ({
    sku: p.sku, name: p.name, origin: p.origin, origin_name: p.origin_name, region: p.region, varieties: p.varieties,
    altitude_m: p.altitude_m, process: p.process, roast: p.roast, roast_label: ROASTS[p.roast], weight_g: p.weight_g,
    price_usd: money(p.price_cents), stock: p.stock, available: p.stock > 0, notes: p.notes
  });""")
js = rep(js, '    renderStateLine();\n    return result;\n  }\n',
         '    renderStateLine();\n    refreshConsole();\n    return result;\n  }\n')
js = rep(js, "    const roast = args.roast == null ? '' : String(args.roast).trim().toLowerCase();\n",
         "    const roast = args.roast == null ? '' : String(args.roast).trim().toLowerCase();\n"
         "    const rawVariety = args.variety == null ? '' : String(args.variety).trim();\n")
js = rep(js, "    if (roast && !ROASTS[roast]) return failure('ERR_VALIDATION', `Tueste desconocido: «${args.roast}».`, 'Use light, medium o dark, o déjelo vacío.', 'roast');\n",
         "    if (roast && !ROASTS[roast]) return failure('ERR_VALIDATION', `Tueste desconocido: «${args.roast}».`, 'Use light, medium o dark, o déjelo vacío.', 'roast');\n"
         "    const variety = rawVariety ? VARIETIES.find((v) => norm(v) === norm(rawVariety)) : '';\n"
         "    if (rawVariety && !variety) return failure('ERR_VALIDATION', `Variedad desconocida: «${args.variety}».`, `Use una de: ${VARIETIES.join(', ')}, o déjela vacía.`, 'variety');\n")
js = rep(js, '      if (roast && p.roast !== roast) return false;\n',
         '      if (roast && p.roast !== roast) return false;\n      if (variety && !p.varieties.includes(variety)) return false;\n')
js = rep(js, "        const haystack = norm([p.sku, p.name, p.origin, p.origin_name, p.process, ROASTS[p.roast]].join(' '));",
         "        const haystack = norm([p.sku, p.name, p.origin, p.origin_name, p.region, p.varieties.join(' '), p.process, ROASTS[p.roast], p.notes].join(' '));")
js = rep(js, '    applyFilterUI({ query, origin, roast, maxCents, inStock }, matches);',
         '    applyFilterUI({ query, origin, variety, roast, maxCents, inStock }, matches);')
js = rep(js, "    form.elements.namedItem('origin').value = f.origin;\n",
         "    form.elements.namedItem('origin').value = f.origin;\n    form.elements.namedItem('variety').value = f.variety;\n")
js = rep(js, "      if (hidden && radio.checked) radio.checked = false;\n    });\n",
         "      if (hidden && radio.checked) radio.checked = false;\n    });\n"
         "    $$('#product-cards .card').forEach((card) => { card.hidden = !keep.has(card.dataset.sku); });\n"
         "    updateGroupCounts();\n    syncPicked();\n")
js = rep(js, "      if (f.origin) params.set('origin', f.origin);\n",
         "      if (f.origin) params.set('origin', f.origin);\n      if (f.variety) params.set('variety', f.variety);\n")
js = rep(js, '      if (radio.disabled) radio.checked = false;\n    }\n    updateQuantityLimit();\n',
         '      if (radio.disabled) radio.checked = false;\n    }\n    renderCards();\n    updateQuantityLimit();\n')
js = rep(js, '      fields.disabled = true;\n', "      fields.disabled = true;\n      button.disabled = currentMode() === 'agent';\n")
js = rep(js, '    fields.disabled = !pending;\n', "    fields.disabled = !pending;\n    button.disabled = currentMode() === 'agent';\n")
js = rep(js, "  wire('#confirm-order', '#confirm-result', confirmOrder);",
         "  wire('#confirm-order', '#confirm-result', (args) => (currentMode() === 'agent'\n"
         "    ? failure('ERR_HUMAN_STEP', 'En la vista Agente no se puede pagar.', 'Cambie a la vista Persona: la persona usuaria revisa el total y pulsa «Confirmar y pagar».')\n"
         "    : confirmOrder(args)));")
js = rep(js, "    if (event.target.name === 'sku') updateQuantityLimit();",
         "    if (event.target.name === 'sku') { updateQuantityLimit(); syncPicked(); }")
js = rep(js, "      version: '1.0',", f"      version: '{VERSION}',")
js = rep(js, '      snapshot: () => ({ cart: cartView(),',
         '      view: () => currentMode(),\n      snapshot: () => ({ view_mode: currentMode(), cart: cartView(),')
js = rep(js, '  /* ---------- Arranque ---------- */\n', J['new'] + '\n\n  /* ---------- Arranque ---------- */\n')
js = block(js, '  function init() {', '\n  }\n  init();', J['init'] + '\n  init();')

# ---------------------------------------------------------------- ensamblado
META_DESC = (f'Tienda de café de demostración para personas y agentes de IA: {len(P)} cafés, {len(CR)} de ellos de Costa Rica, '
             'con SKU, variedad, precio en USD y bolsas disponibles; vistas Persona y Agente; carrito y pedido en dos pasos, '
             'con aprobación de la persona usuaria para pagar.')
head = ('<title>Grano Claro</title>\n'
        f'<meta name="description" content="{E(META_DESC)}">\n' + head_links +
        '<style>\n' + css + '</style>\n' + J['early'] + '\n'
        '<script type="application/ld+json">\n' + ld_out + '\n</script>\n'
        '<script type="application/json" id="agent-tools">\n' + tools_out + '\n</script>\n')
page = head + body + '\n<script>\n' + js + '\n</script>\n'
assert '<!DOCTYPE' not in page and '<html' not in page and '<body' not in page and '</head>' not in page
assert page.index('<title>') < 200 and '@@' not in page

SKELETON = ('<!doctype html>\n<html lang="es">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n')
standalone = SKELETON + head + '</head>\n<body>\n' + body + '\n<script>\n' + js + '\n</script>\n</body>\n</html>\n'
(ROOT / 'index.html').write_bytes(standalone.encode('utf-8'))
if '--artifact' in sys.argv[1:]:
    (ROOT / 'dist').mkdir(exist_ok=True)
    (ROOT / 'dist' / 'grano-claro.artifact.html').write_bytes(page.encode('utf-8'))
print(f'index.html: {len(standalone.encode("utf-8"))} bytes; {len(P)} cafés ({len(CR)} de Costa Rica); '
      f'{len(VARIETIES)} variedades')
