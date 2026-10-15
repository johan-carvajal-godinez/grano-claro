# -*- coding: utf-8 -*-
"""Pruebas de extremo a extremo de los requisitos de diseño R1–R9 (Chromium con Playwright).

Las pruebas ubican los controles por rol y nombre accesible, como lo hace un agente que lee el árbol de
accesibilidad, y no por selectores CSS; llaman a la API de script (granoClaro.call) y simulan WebMCP con un
document.modelContext sustituto. Incluyen axe-core (WCAG 2.0–2.2, niveles A y AA, y buenas prácticas), el
desplazamiento del diseño durante la carga (PerformanceObserver), la ventana móvil de 390 px con un oráculo
fijo, la lectura sin JavaScript, la aritmética de los montos y el gobierno de la transacción de dos fases.

Valen para cualquier versión de la página:
    python3 tests/probar_pagina.py                            # index.html (versión actual)
    python3 tests/probar_pagina.py versions/v1.0/index.html   # versión 1.0
Requisitos: pip install -r requirements-dev.txt; python3 -m playwright install chromium; npm install.
Salidas: tests/salida/ (instantánea ARIA de la página probada).
"""
import importlib.metadata
import json
import re
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
RUTA = sys.argv[1] if len(sys.argv) > 1 else 'index.html'
PAGINA = (ROOT / RUTA).resolve()
URL = PAGINA.as_uri() + '#modo-agente'   # la 1.1 abre su vista Agente; la 1.0 ignora el fragmento
SALIDA = ROOT / 'tests' / 'salida'
NM = ROOT / 'node_modules'
AXE_JS = NM / 'axe-core' / 'axe.min.js'
FUENTES = {(fam, w): NM / '@fontsource' / slug / 'files' / f'{slug}-latin-{w}-normal.woff2'
           for fam, slug, pesos in (('Atkinson Hyperlegible Next', 'atkinson-hyperlegible-next', (400, 600, 700)),
                                    ('Atkinson Hyperlegible Mono', 'atkinson-hyperlegible-mono', (400, 600)))
           for w in pesos}
FUENTES = {k: p for k, p in FUENTES.items() if p.exists()}
# Igual que la hoja de Google Fonts que pide la página (display=optional): una fuente tardía no desplaza el diseño.
CSS_FUENTES = ''.join(f"@font-face{{font-family:'{fam}';font-weight:{w};font-display:optional;"
                      f"src:url(https://fonts.gstatic.com/local/{p.name}) format('woff2')}}" for (fam, w), p in FUENTES.items())
POR_NOMBRE = {p.name: p for p in FUENTES.values()}
RE_FUENTES = re.compile(r'https://fonts\.(googleapis|gstatic)\.com/.*')

# El orden de la tienda: UTC−06:00.
HOY_TIENDA = (datetime.now(timezone.utc) - timedelta(hours=6)).date()

STUB_WEBMCP = """(() => {
  const registradas = [];
  const oyentes = {};
  const mc = {
    registerTool: async (tool) => { registradas.push(tool); },
    addEventListener: (tipo, fn) => { (oyentes[tipo] = oyentes[tipo] || []).push(fn); }
  };
  Object.defineProperty(document, 'modelContext', { value: mc, configurable: true });
  window.__webmcp = {
    registradas,
    disparar: (tipo, datos) => (oyentes[tipo] || []).forEach((fn) => fn(Object.assign(new Event(tipo), datos)))
  };
})();"""
MEDIR_CLS = """(() => {
  window.__cls = 0;
  try {
    new PerformanceObserver((lista) => {
      for (const e of lista.getEntries()) if (!e.hadRecentInput) window.__cls += e.value;
    }).observe({ type: 'layout-shift', buffered: true });
  } catch (err) { window.__cls = -1; }
})();"""
SIN_ALMACENAMIENTO = "Object.defineProperty(window, 'localStorage', { get() { throw new Error('almacenamiento bloqueado'); } });"
OBJETIVOS_PEQUENOS = """() => {
  const visible = (el) => { const r = el.getBoundingClientRect(); return el.checkVisibility() && r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden'; };
  const out = [];
  for (const el of document.querySelectorAll('button, input:not([type=hidden]), select, textarea, summary')) {
    if (!visible(el)) continue;
    let alto = el.getBoundingClientRect().height;
    if (el.matches('input[type=radio], input[type=checkbox]')) {
      for (const l of el.labels || []) if (visible(l)) alto = Math.max(alto, l.getBoundingClientRect().height);
    }
    if (alto < 43.5) out.push(`${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''} (${Math.round(alto)} px)`);
  }
  return out;
}"""
SOBRESALEN = """(ancho) => {
  const desplaza = (el) => { for (let a = el.parentElement; a; a = a.parentElement) {
    const ox = getComputedStyle(a).overflowX; if (['auto', 'scroll', 'hidden', 'clip'].includes(ox)) return a; } return null; };
  const fuera = [];
  for (const el of document.body.querySelectorAll('*')) {
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height || (r.width <= 1 && r.height <= 1) || !el.checkVisibility()) continue;
    if ((r.right > ancho + 0.5 || r.left < -0.5) && !desplaza(el)) {
      fuera.push(`${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}${el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\\s+/).join('.') : ''} (${Math.round(r.left)}–${Math.round(r.right)} px)`);
    }
  }
  const contenedores = Array.from(document.body.querySelectorAll('*')).filter((el) => {
    const ox = getComputedStyle(el).overflowX;
    return ['auto', 'scroll'].includes(ox) && el.scrollWidth > el.clientWidth + 1 && el.checkVisibility();
  }).map((el) => ({ desc: `${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}`,
                    tabla: el.tagName === 'PRE' || (el.firstElementChild ? el.firstElementChild.tagName === 'TABLE' : false) }));
  return { ancho: document.documentElement.clientWidth, fuera, contenedores };
}"""
ENVIO_DE_AGENTE = """(f) => new Promise((resolver) => {
  const ev = new SubmitEvent('submit', { cancelable: true, bubbles: true });
  ev.agentInvoked = true;
  ev.respondWith = (p) => Promise.resolve(p).then(resolver);
  f.dispatchEvent(ev);
})"""

PRUEBAS = []
CONSOLA, DIALOGOS = [], []
NAV = None
AXE = AXE_JS.read_text(encoding='utf-8') if AXE_JS.exists() else None
# La 1.0 queda congelada tal como se publicó; sus fallos conocidos se informan sin ocultarlos.
CONOCIDOS = {
    'versions/v1.0/index.html': {
        'R3 Controles de formulario y botones visibles de al menos 44 px de alto':
            'En la 1.0, los botones de opción de la tabla y los botones «Quitar» miden menos de 44 px; se corrigió en la 1.1.',
    },
}


class Omitida(Exception):
    pass


def prueba(nombre):
    def registrar(fn):
        PRUEBAS.append((nombre, fn))
        return fn
    return registrar


def esperar(condicion, detalle=''):
    if not condicion:
        raise AssertionError(detalle)


def servir_fuentes(route):
    url = route.request.url
    if url.startswith('https://fonts.googleapis.com/'):
        return route.fulfill(status=200, content_type='text/css', body=CSS_FUENTES)
    archivo = POR_NOMBRE.get(url.rsplit('/', 1)[-1])
    if archivo:
        return route.fulfill(status=200, content_type='font/woff2', body=archivo.read_bytes())
    return route.fulfill(status=404, body='')


@contextmanager
def abrir(*, js=True, webmcp=True, almacenamiento=True, esquema='light', ancho=1280, alto=900, movil=False, reloj=False):
    ctx = NAV.new_context(viewport={'width': ancho, 'height': alto}, color_scheme=esquema, java_script_enabled=js,
                          is_mobile=movil, has_touch=movil, device_scale_factor=3 if movil else 1)
    ctx.route(RE_FUENTES, servir_fuentes)
    page = ctx.new_page()
    errores = []
    page.on('console', lambda m: errores.append(m.text) if m.type == 'error' else None)
    page.on('pageerror', lambda e: errores.append(str(e)))
    page.on('dialog', lambda d: (DIALOGOS.append(d.message), d.dismiss()))
    page.add_init_script(MEDIR_CLS)
    if webmcp:
        page.add_init_script(STUB_WEBMCP)
    if not almacenamiento:
        page.add_init_script(SIN_ALMACENAMIENTO)
    if reloj:
        page.clock.install()
    page.goto(URL)   # espera al evento load; la página termina de iniciarse antes
    if js and page.evaluate('document.documentElement.dataset.ready') != 'true':
        raise AssertionError('la página no terminó de iniciarse')
    try:
        yield page
    finally:
        CONSOLA.extend(errores)
        ctx.close()


# ---------------------------------------------------------------- acciones por rol y nombre
def estado(page):
    s = page.get_by_role('status')
    return {'code': s.get_attribute('data-code'), 'state': s.get_attribute('data-state'),
            'seq': int(s.get_attribute('data-seq')), 'texto': s.inner_text()}


def agregar(page, cafe, molienda='Molido para filtro', cantidad=1):
    page.get_by_role('radio', name=cafe, exact=True).check()
    page.get_by_role('radio', name=molienda, exact=True).check()
    page.get_by_role('spinbutton', name='Cantidad de bolsas').fill(str(cantidad))
    page.get_by_role('button', name='Agregar al carrito', exact=True).click()


def preparar(page, entrega='retiro', fecha=None):
    page.get_by_role('textbox', name='Nombre y apellido').fill('Ana Rojas')
    page.get_by_role('textbox', name='Correo electrónico').fill('ana.rojas@example.com')
    if entrega == 'envio':
        page.get_by_role('radio', name=re.compile(r'^Envío a domicilio')).check()
        page.get_by_role('textbox', name='Dirección de entrega').fill('Calle 5, San José')
    else:
        page.get_by_role('radio', name='Retiro en tienda (sin costo)').check()
    campo = page.get_by_role('textbox', name='Fecha de entrega')
    campo.fill(fecha or campo.get_attribute('data-min'))
    page.get_by_role('button', name='Preparar pedido (sin cobro)').click()


def vista_persona(page):
    """En la 1.1 el pago solo se hace desde la vista Persona; la 1.0 no tiene selector de vista."""
    radio = page.get_by_role('radio', name='Persona', exact=True)
    if radio.count():
        radio.check()


def vista_agente(page):
    radio = page.get_by_role('radio', name='Agente', exact=True)
    if radio.count():
        radio.check()


def confirmar(page, total):
    vista_persona(page)
    page.get_by_role('textbox', name='Total aprobado (USD)').fill(total)
    page.get_by_role('button', name=re.compile(r'^Confirmar y pagar')).click()


def enviar_formulario(page, nombre):
    """Reenvía un formulario por programa, como un agente WebMCP que invoca su herramienta."""
    page.get_by_role('form', name=nombre).evaluate('(f) => f.requestSubmit()')


def llamar(page, herramienta, args=None):
    return page.evaluate('([n, a]) => granoClaro.call(n, a)', [herramienta, args or {}])


def pendiente(page):
    return llamar(page, 'get_cart')['data']['pending_order']


def herramientas(page):
    return json.loads(page.locator('#agent-tools').text_content())['tools']


def productos_ld(page):
    ld = json.loads(page.locator('script[type="application/ld+json"]').text_content())
    return next(g for g in ld['@graph'] if g['@type'] == 'ItemList')


def tabla_catalogo(page):
    return page.get_by_role('table', name=re.compile(r'\bcafés\b'))


def nombres_interactivos(page):
    cdp = page.context.new_cdp_session(page)
    nodos = cdp.send('Accessibility.getFullAXTree')['nodes']
    roles = {'button', 'radio', 'checkbox', 'textbox', 'searchbox', 'combobox', 'spinbutton', 'slider', 'switch', 'listbox'}
    out = []
    for n in nodos:
        if n.get('ignored'):
            continue
        rol = (n.get('role') or {}).get('value')
        if rol in roles:
            out.append((rol, ((n.get('name') or {}).get('value') or '').strip()))
    return out


def axe(page):
    if AXE is None:
        raise Omitida('falta node_modules/axe-core (ejecute npm install)')
    page.add_script_tag(content=AXE)
    return page.evaluate("""async () => (await axe.run(document, { runOnly: { type: 'tag',
        values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'] } }))
        .violations.map((v) => `${v.id} (${v.nodes.length}): ${v.nodes.slice(0, 2).map((n) => n.target.join(' ')).join(', ')}`)""")


NYERI = 'Nyeri Kenia (KE) 250 g'           # GC-004: 18.50, 5 bolsas
YIRGA = 'Yirgacheffe Etiopía (ET) 340 g'   # GC-002: 17.00
HUILA = 'Huila Colombia (CO) 340 g'        # GC-001: 14.50
CERRADO = 'Cerrado Mineiro Brasil (BR) 500 g'  # GC-005: 15.00, 20 bolsas


# ================================================================ R1 Direccionamiento inequívoco
@prueba('R1 Los controles y botones visibles tienen nombres accesibles no vacíos y únicos')
def _():
    with abrir() as page:
        agregar(page, NYERI)
        agregar(page, YIRGA, 'Grano entero')
        nombres = nombres_interactivos(page)
        vacios = [rol for rol, n in nombres if not n]
        solo = [n for _, n in nombres]
        repetidos = sorted({n for n in solo if solo.count(n) > 1})
        esperar(len(nombres) > 20 and not vacios and not repetidos, f'vacíos={vacios} repetidos={repetidos}')


@prueba('R1 Cada botón de opción del catálogo nombra producto, origen y peso')
def _():
    with abrir() as page:
        radio = page.get_by_role('radio', name=NYERI, exact=True)
        esperar(radio.count() == 1 and radio.get_attribute('value') == 'GC-004', 'falta «Nyeri Kenia (KE) 250 g»')
        n = productos_ld(page)['numberOfItems']
        esperar(tabla_catalogo(page).get_by_role('radio').count() == n, f'se esperaban {n} botones de opción')


@prueba('R1 Cada botón «Quitar» nombra su línea y su producto')
def _():
    with abrir() as page:
        agregar(page, NYERI)
        agregar(page, YIRGA, 'Grano entero')
        b1 = page.get_by_role('button', name=re.compile(r'^Quitar línea L1: Nyeri, Kenia, 250 g, molido para filtro$'))
        b2 = page.get_by_role('button', name=re.compile(r'^Quitar línea L2: Yirgacheffe, Etiopía, 340 g, grano entero$'))
        esperar(b1.count() == 1 and b2.count() == 1)
        b1.click()
        esperar(estado(page)['code'] == 'CART_REMOVED')


# ================================================================ R2 Efectos observables
@prueba('R2 Cada acción escribe estado, código y número de evento en la región de estado')
def _():
    with abrir() as page:
        e0 = estado(page)
        page.get_by_role('button', name='Aplicar filtros').click()
        e1 = estado(page)
        esperar(e1['seq'] == e0['seq'] + 1 and e1['code'] == 'SEARCH_OK' and e1['state'] == 'success', str(e1))
        agregar(page, NYERI)
        e2 = estado(page)
        esperar(e2['seq'] == e1['seq'] + 1 and e2['code'] == 'CART_ADDED' and f'Evento {e2["seq"]}' in e2['texto'], str(e2))


@prueba('R2 La región de estado es persistente: role=status, aria-live y mensajes que no desaparecen')
def _():
    with abrir() as page:
        s = page.get_by_role('status')
        esperar(s.get_attribute('aria-live') == 'polite' and s.get_attribute('aria-atomic') == 'true')
        agregar(page, NYERI)
        antes = s.inner_text()
        page.wait_for_timeout(2500)
        esperar(s.inner_text() == antes, 'el mensaje cambió solo')


# ================================================================ R3 Estabilidad perceptiva
@prueba('R3 Sin desplazamiento del diseño durante la carga (CLS = 0)')
def _():
    with abrir() as page:
        page.wait_for_timeout(1200)
        cls = page.evaluate('window.__cls')
        esperar(cls == 0, f'CLS = {cls}')


@prueba('R3 Sin animaciones, transiciones ni ventanas modales')
def _():
    with abrir() as page:
        agregar(page, NYERI)
        page.get_by_role('button', name='Aplicar filtros').click()
        animaciones = page.evaluate('document.getAnimations().length')
        transiciones = page.evaluate("""Array.from(document.querySelectorAll('*')).filter((e) => {
            const cs = getComputedStyle(e);
            return cs.animationName !== 'none' || cs.transitionDuration.split(',').some((d) => parseFloat(d) > 0);
          }).length""")
        modales = page.evaluate("document.querySelectorAll('dialog[open], [aria-modal=\"true\"]').length")
        esperar(animaciones == transiciones == modales == 0, f'{animaciones} animaciones, {transiciones} transiciones, {modales} modales')


@prueba('R3 Controles de formulario y botones visibles de al menos 44 px de alto')
def _():
    with abrir() as page:
        agregar(page, NYERI)          # aparecen los botones «Quitar»
        preparar(page)                # el formulario de pago se habilita
        pequenos = page.evaluate(OBJETIVOS_PEQUENOS)
        esperar(not pequenos, f'{len(pequenos)} objetivos pequeños: ' + '; '.join(pequenos[:10]))


# ================================================================ R4 Formatos canónicos
@prueba('R4 La fecha de entrega se escribe como texto ISO 8601, con la ventana válida en atributos data')
def _():
    with abrir() as page:
        f = page.get_by_role('textbox', name='Fecha de entrega')
        esperar(f.get_attribute('type') == 'text' and f.get_attribute('pattern') and f.get_attribute('placeholder') == 'AAAA-MM-DD')
        dmin, dmax = f.get_attribute('data-min'), f.get_attribute('data-max')
        esperar(dmin == (HOY_TIENDA + timedelta(days=2)).isoformat() and dmax == (HOY_TIENDA + timedelta(days=30)).isoformat(),
                f'{dmin}–{dmax}')


@prueba('R4 Una fecha fuera de la ventana de 2 a 30 días se rechaza y se indica el rango válido')
def _():
    with abrir() as page:
        agregar(page, NYERI)
        preparar(page, fecha=(HOY_TIENDA + timedelta(days=1)).isoformat())
        e = estado(page)
        rango = (HOY_TIENDA + timedelta(days=2)).isoformat()
        esperar(e['code'] == 'ERR_VALIDATION' and rango in e['texto'], e['texto'])
        esperar(page.get_by_role('textbox', name='Fecha de entrega').get_attribute('aria-invalid') == 'true')


@prueba('R4 Montos con punto decimal y código ISO 4217, calculados en centavos (3 × 14.50 = 43.50)')
def _():
    with abrir() as page:
        agregar(page, HUILA, cantidad=3)
        carrito = llamar(page, 'get_cart')['data']['cart']
        esperar(carrito['subtotal_usd'] == '43.50' and carrito['currency'] == 'USD', str(carrito))
        esperar('USD 43.50' in page.get_by_role('table', name=re.compile('carrito')).inner_text())
        esperar(all(re.fullmatch(r'\d+\.\d{2}', it['item']['offers']['price']) and it['item']['offers']['priceCurrency'] == 'USD'
                    for it in productos_ld(page)['itemListElement']))


@prueba('R4 Orígenes con códigos ISO 3166-1 alfa-2 en el filtro, la tabla y la API')
def _():
    with abrir() as page:
        codigos = page.get_by_role('combobox', name='Origen').evaluate('(s) => Array.from(s.options, (o) => o.value).filter(Boolean)')
        api = [p['origin'] for p in llamar(page, 'search_products')['data']['products']]
        esperar(codigos and all(re.fullmatch(r'[A-Z]{2}', c) for c in codigos + api) and set(api) <= set(codigos))
        esperar('Kenia (KE)' in tabla_catalogo(page).inner_text())


# ================================================================ R5 Errores recuperables
@prueba('R5 Un error de campo muestra código, causa, campo marcado y sugerencia')
def _():
    with abrir() as page:
        page.get_by_role('radio', name='Grano entero', exact=True).check()
        page.get_by_role('button', name='Agregar al carrito').click()
        e = estado(page)
        esperar(e['code'] == 'ERR_VALIDATION' and 'Falta elegir el café' in e['texto'], e['texto'])
        radio = page.get_by_role('radio', name=NYERI, exact=True)
        esperar(radio.get_attribute('aria-invalid') == 'true')
        descripcion = radio.evaluate("""(r) => r.getAttribute('aria-describedby').split(' ').map((id) => document.getElementById(id))
            .filter((el) => el && !el.hidden).map((el) => el.textContent).join(' ')""")
        esperar('Falta elegir el café' in descripcion and 'Marque una fila' in descripcion, descripcion)


@prueba('R5 El error permanece hasta la siguiente acción y desaparece con un acierto')
def _():
    with abrir() as page:
        page.get_by_role('button', name='Agregar al carrito').click()
        radio = page.get_by_role('radio', name=NYERI, exact=True)
        page.wait_for_timeout(2000)
        esperar(radio.get_attribute('aria-invalid') == 'true' and estado(page)['code'] == 'ERR_VALIDATION')
        agregar(page, NYERI)
        esperar(radio.get_attribute('aria-invalid') is None and estado(page)['code'] == 'CART_ADDED')


@prueba('R5 ERR_UNKNOWN_SKU devuelve los SKU válidos')
def _():
    with abrir() as page:
        r = llamar(page, 'add_to_cart', {'sku': 'GC-999', 'grind': 'whole'})
        esperar(r['code'] == 'ERR_UNKNOWN_SKU' and 'GC-001' in r['hint'] and r['field'] == 'sku', str(r))


@prueba('R5 ERR_OUT_OF_STOCK sugiere buscar con in_stock_only=true')
def _():
    with abrir() as page:
        r = llamar(page, 'add_to_cart', {'sku': 'GC-003', 'grind': 'whole'})
        esperar(r['code'] == 'ERR_OUT_OF_STOCK' and 'in_stock_only=true' in r['hint'], str(r))
        esperar(page.get_by_role('radio', name='Huehuetenango Guatemala (GT) 340 g').is_disabled())


@prueba('R5 ERR_STOCK indica la mayor cantidad que aún se puede agregar')
def _():
    with abrir() as page:
        agregar(page, NYERI, cantidad=4)
        agregar(page, NYERI, cantidad=2)
        e = estado(page)
        esperar(e['code'] == 'ERR_STOCK' and 'como máximo 1' in e['texto'], e['texto'])


@prueba('R5 ERR_UNKNOWN_LINE lista las líneas actuales del carrito')
def _():
    with abrir() as page:
        agregar(page, NYERI)
        r = llamar(page, 'remove_from_cart', {'line_id': 'L7'})
        esperar(r['code'] == 'ERR_UNKNOWN_LINE' and 'L1' in r['hint'], str(r))


@prueba('R5 ERR_CART_EMPTY al preparar un pedido con el carrito vacío')
def _():
    with abrir() as page:
        preparar(page)
        esperar(estado(page)['code'] == 'ERR_CART_EMPTY')


@prueba('R5 ERR_NO_PENDING_ORDER al confirmar un pedido anulado')
def _():
    with abrir() as page:
        agregar(page, NYERI)
        preparar(page)
        agregar(page, YIRGA)          # el cambio anula el pedido
        vista_persona(page)
        enviar_formulario(page, 'Paso 2. Confirmar y pagar')
        esperar(estado(page)['code'] == 'ERR_NO_PENDING_ORDER')


@prueba('R5 ERR_UNKNOWN_TOOL nombra las herramientas disponibles')
def _():
    with abrir() as page:
        r = llamar(page, 'pagar_todo')
        esperar(r['code'] == 'ERR_UNKNOWN_TOOL' and 'search_products' in r['hint'], str(r))


@prueba('R5 ERR_VALIDATION indica el campo y los valores permitidos')
def _():
    with abrir() as page:
        r = llamar(page, 'search_products', {'origin': 'XX'})
        esperar(r['code'] == 'ERR_VALIDATION' and r['field'] == 'origin' and 'KE' in r['hint'], str(r))


# ================================================================ R6 Una semántica, varios transportes
@prueba('R6 El formulario y la API de script devuelven el mismo resultado')
def _():
    with abrir() as page:
        api = llamar(page, 'search_products', {'roast': 'light', 'in_stock_only': True})
        page.get_by_role('combobox', name='Tueste').select_option('light')
        page.get_by_role('checkbox', name='Solo cafés disponibles').check()
        form = json.loads(page.get_by_role('search', name='Filtrar el catálogo').evaluate(ENVIO_DE_AGENTE))
        esperar((form['ok'], form['code'], form['message'], form['data']['count']) ==
                (api['ok'], api['code'], api['message'], api['data']['count']), f'{form["message"]} ≠ {api["message"]}')


@prueba('R6 WebMCP declarativo: el envío del agente recibe por respondWith el resultado JSON')
def _():
    with abrir() as page:
        page.get_by_role('radio', name=NYERI, exact=True).check()
        page.get_by_role('radio', name='Grano entero', exact=True).check()
        r = json.loads(page.get_by_role('form', name='Agregar al carrito').evaluate(ENVIO_DE_AGENTE))
        esperar(r['ok'] and r['code'] == 'CART_ADDED' and r['data']['line_id'] == 'L1', str(r))
        esperar(estado(page)['code'] == 'CART_ADDED')


@prueba('R6 WebMCP imperativo: se registran remove_from_cart y get_cart con los esquemas de #agent-tools')
def _():
    with abrir() as page:
        registradas = page.evaluate('window.__webmcp.registradas.map((t) => ({ name: t.name, inputSchema: t.inputSchema, annotations: t.annotations }))')
        esperadas = [{'name': t['name'], 'inputSchema': t['inputSchema'], 'annotations': t['annotations']}
                     for t in herramientas(page) if t['binding']['webmcp'] == 'imperative']
        esperar(registradas == esperadas and {t['name'] for t in registradas} == {'remove_from_cart', 'get_cart'}, str(registradas))


@prueba('R6 Las herramientas imperativas devuelven lo mismo que la API de script')
def _():
    with abrir() as page:
        agregar(page, NYERI, cantidad=2)
        via_webmcp = json.loads(page.evaluate("window.__webmcp.registradas.find((t) => t.name === 'get_cart').execute({})"))
        esperar(via_webmcp == llamar(page, 'get_cart'))


@prueba('R6 Todo resultado tiene la forma {ok, code, message, hint?, field?, data?}')
def _():
    with abrir() as page:
        resultados = [llamar(page, *c) for c in (
            ('search_products', {'origin': 'CO'}), ('add_to_cart', {'sku': 'GC-001', 'grind': 'whole'}), ('get_cart',),
            ('add_to_cart', {'sku': 'GC-003', 'grind': 'whole'}), ('remove_from_cart', {'line_id': 'L9'}), ('confirm_order',))]
        for r in resultados:
            esperar(set(r) <= {'ok', 'code', 'message', 'hint', 'field', 'data'} and isinstance(r['ok'], bool)
                    and re.fullmatch(r'[A-Z_]+', r['code']) and r['message'], str(r))
        esperar(page.evaluate('granoClaro.tools.map((t) => t.name)') ==
                [t['name'] for t in herramientas(page) if t['binding']['javascript']])


# ================================================================ R7 Autoridad humana
@prueba('R7 confirm_order declara consequentialHint y su formulario no se envía solo')
def _():
    with abrir() as page:
        conf = next(t for t in herramientas(page) if t['name'] == 'confirm_order')
        esperar(conf['annotations']['consequentialHint'] is True and conf['binding']['autosubmit'] is False)
        esperar(page.get_by_role('form', name='Paso 2. Confirmar y pagar').get_attribute('toolautosubmit') is None)
        for nombre in ('Agregar al carrito', 'Paso 1. Preparar el pedido'):
            esperar(page.get_by_role('form', name=nombre).get_attribute('toolautosubmit') is not None, nombre)
        esperar(page.get_by_role('search', name='Filtrar el catálogo').get_attribute('toolautosubmit') is not None)


@prueba('R7 La API de script rechaza confirm_order con ERR_HUMAN_STEP y el pedido sigue pendiente')
def _():
    with abrir() as page:
        agregar(page, NYERI, cantidad=2)
        preparar(page)
        r = llamar(page, 'confirm_order', {'total_confirmation': '37.00'})
        esperar(r['code'] == 'ERR_HUMAN_STEP' and pendiente(page)['status'] == 'pending_confirmation', str(r))


@prueba('R7 El botón de pago está deshabilitado mientras no hay un pedido pendiente')
def _():
    with abrir() as page:
        vista_persona(page)
        esperar(page.get_by_role('button', name='Confirmar y pagar', exact=True).is_disabled())


@prueba('R7 El botón de pago muestra el monto exacto del pedido')
def _():
    with abrir() as page:
        agregar(page, NYERI, cantidad=2)
        preparar(page)
        vista_persona(page)
        boton = page.get_by_role('button', name='Confirmar y pagar USD 37.00', exact=True)
        esperar(boton.count() == 1 and boton.is_enabled())


@prueba('R7 Si un agente activa confirm_order, la página avisa a la persona (AWAITING_USER)')
def _():
    with abrir() as page:
        page.evaluate("window.__webmcp.disparar('toolactivated', { toolName: 'confirm_order' })")
        e = estado(page)
        esperar(e['code'] == 'AWAITING_USER' and e['state'] == 'info', str(e))


# ================================================================ Aritmética y gobierno de la transacción
@prueba('Aritmética: 2 × 18.50 = 37.00 con retiro en tienda')
def _():
    with abrir() as page:
        agregar(page, NYERI, cantidad=2)
        preparar(page)
        p = pendiente(page)
        esperar((p['subtotal_usd'], p['shipping_usd'], p['total_usd']) == ('37.00', '0.00', '37.00'), str(p))


@prueba('Aritmética: 17.00 + 5.00 de envío = 22.00')
def _():
    with abrir() as page:
        agregar(page, YIRGA)
        preparar(page, entrega='envio')
        p = pendiente(page)
        esperar((p['subtotal_usd'], p['shipping_usd'], p['total_usd']) == ('17.00', '5.00', '22.00'), str(p))


@prueba('Aritmética: 17.00 + 29.00 = 46.00 con envío gratis, porque 46.00 ≥ 40.00')
def _():
    with abrir() as page:
        agregar(page, YIRGA)
        agregar(page, HUILA, cantidad=2)
        preparar(page, entrega='envio')
        p = pendiente(page)
        esperar((p['subtotal_usd'], p['shipping_usd'], p['total_usd']) == ('46.00', '0.00', '46.00'), str(p))


@prueba('Aritmética: como máximo 10 bolsas por producto, aunque haya más existencias')
def _():
    with abrir() as page:
        agregar(page, CERRADO, cantidad=10)
        esperar(estado(page)['code'] == 'CART_ADDED')
        agregar(page, CERRADO, cantidad=1)
        e = estado(page)
        esperar(e['code'] == 'ERR_STOCK' and 'máximo por pedido es 10 bolsas' in e['texto'], e['texto'])


@prueba('Gobierno: un total incorrecto deja el pedido pendiente (ERR_TOTAL_MISMATCH)')
def _():
    with abrir() as page:
        agregar(page, NYERI, cantidad=2)
        preparar(page)
        confirmar(page, '36.00')
        esperar(estado(page)['code'] == 'ERR_TOTAL_MISMATCH' and pendiente(page)['status'] == 'pending_confirmation')


@prueba('Gobierno: el total correcto confirma, también con coma decimal («37,00»)')
def _():
    with abrir() as page:
        agregar(page, NYERI, cantidad=2)
        preparar(page)
        confirmar(page, '37,00')
        e = estado(page)
        esperar(e['code'] == 'ORDER_CONFIRMED' and 'USD 37.00' in e['texto'], e['texto'])


@prueba('Gobierno: repetir la confirmación no cobra de nuevo y las existencias bajan de 5 a 3 una sola vez')
def _():
    with abrir() as page:
        agregar(page, NYERI, cantidad=2)
        preparar(page)
        confirmar(page, '37.00')
        enviar_formulario(page, 'Paso 2. Confirmar y pagar')
        esperar(estado(page)['code'] == 'ORDER_ALREADY_CONFIRMED')
        nyeri = next(p for p in llamar(page, 'search_products')['data']['products'] if p['sku'] == 'GC-004')
        esperar(nyeri['stock'] == 3, f'existencias: {nyeri["stock"]}')
        vista_agente(page)
        fila = tabla_catalogo(page).get_by_role('row').filter(has=page.get_by_role('radio', name=NYERI, exact=True))
        esperar('3 bolsas' in fila.inner_text(), fila.inner_text())


@prueba('Gobierno: un cambio en el carrito anula el pedido pendiente')
def _():
    with abrir() as page:
        agregar(page, NYERI)
        preparar(page)
        agregar(page, YIRGA)
        e = estado(page)
        esperar('se anuló porque el carrito cambió' in e['texto'] and pendiente(page) is None, e['texto'])


@prueba('Gobierno: volver a preparar reemplaza el pedido pendiente')
def _():
    with abrir() as page:
        agregar(page, NYERI)
        preparar(page)
        primero = pendiente(page)['order_id']
        page.wait_for_timeout(50)
        preparar(page, entrega='envio')
        e = estado(page)
        esperar(f'Reemplaza al pedido {primero}' in e['texto'] and pendiente(page)['order_id'] != primero, e['texto'])


@prueba('Gobierno: el pedido vence a los 30 minutos (ERR_ORDER_EXPIRED)')
def _():
    with abrir(reloj=True) as page:
        agregar(page, NYERI)
        preparar(page)
        page.clock.fast_forward('31:00')
        confirmar(page, '18.50')
        esperar(estado(page)['code'] == 'ERR_ORDER_EXPIRED')


# ================================================================ R8 Degradación elegante
@prueba('R8 Sin JavaScript, el catálogo completo está en el HTML estático')
def _():
    with abrir(js=False) as page:
        n = productos_ld(page)['numberOfItems']
        filas = tabla_catalogo(page).get_by_role('row').count() - 1
        esperar(filas == n, f'{filas} filas para {n} productos')
        # Playwright desactiva la ejecución de scripts, pero el analizador sigue tratando <noscript> como texto:
        # se comprueba que el aviso exista en el HTML.
        aviso = page.locator('noscript').first.text_content() or ''
        esperar('Sin JavaScript se puede leer todo el catálogo' in aviso, 'falta el aviso <noscript>')


@prueba('R8 Sin WebMCP, los formularios y la API de script funcionan igual')
def _():
    with abrir(webmcp=False) as page:
        esperar(page.get_by_text(re.compile('no expone WebMCP')).is_visible())
        agregar(page, NYERI)
        esperar(estado(page)['code'] == 'CART_ADDED' and llamar(page, 'get_cart')['data']['cart']['units'] == 1)


@prueba('R8 Con el almacenamiento bloqueado, la página funciona en memoria')
def _():
    with abrir(almacenamiento=False) as page:
        agregar(page, NYERI)
        preparar(page)
        esperar(pendiente(page)['total_usd'] == '18.50')


# ================================================================ R9 Descubribilidad
@prueba('R9 Enlaces de descubrimiento: alternativa en Markdown, service-desc y api-catalog')
def _():
    with abrir() as page:
        for selector in ('link[rel="alternate"][type="text/markdown"]', 'link[rel="service-desc"]', 'link[rel="api-catalog"]'):
            esperar(page.locator(selector).count() == 1, selector)


@prueba('R9 JSON-LD con la tienda, el catálogo y un producto por fila de la tabla')
def _():
    with abrir() as page:
        ld = json.loads(page.locator('script[type="application/ld+json"]').text_content())
        tipos = {g['@type'] for g in ld['@graph']}
        lista = productos_ld(page)
        filas = tabla_catalogo(page).get_by_role('radio').count()
        esperar({'WebSite', 'OnlineStore', 'ItemList'} <= tipos and lista['numberOfItems'] == len(lista['itemListElement']) == filas)


# ================================================================ Accesibilidad con axe-core
@prueba('axe-core: 0 infracciones en el estado inicial')
def _():
    with abrir() as page:
        v = axe(page)
        esperar(not v, '; '.join(v))


@prueba('axe-core: 0 infracciones con un pedido en curso')
def _():
    with abrir() as page:
        agregar(page, NYERI, cantidad=2)
        preparar(page)
        vista_persona(page)
        page.get_by_role('textbox', name='Total aprobado (USD)').fill('37.00')
        v = axe(page)
        esperar(not v, '; '.join(v))


@prueba('axe-core: 0 infracciones en el tema oscuro')
def _():
    with abrir(esquema='dark') as page:
        agregar(page, NYERI)
        v = axe(page)
        esperar(not v, '; '.join(v))


# ================================================================ Móvil (oráculo fijo de 390 px)
@prueba('Móvil 390 px: ningún elemento sobresale de la ventana (se compara con 390 px fijos)')
def _():
    with abrir(ancho=390, alto=844, movil=True) as page:
        agregar(page, NYERI)
        preparar(page)
        r = page.evaluate(SOBRESALEN, 390)
        esperar(not r['fuera'], f'{len(r["fuera"])} elementos fuera: ' + '; '.join(r['fuera'][:8]))
        esperar(r['ancho'] == 390, f'la ventana de diseño mide {r["ancho"]} px')


@prueba('Móvil 390 px: solo las tablas y los bloques de código se desplazan, cada uno dentro de su contenedor')
def _():
    with abrir(ancho=390, alto=844, movil=True) as page:
        agregar(page, NYERI)
        r = page.evaluate(SOBRESALEN, 390)
        otros = [c['desc'] for c in r['contenedores'] if not c['tabla']]
        esperar(any(c['tabla'] for c in r['contenedores']) and not otros, f'contenedores desplazables que no son tablas: {otros}')


# ================================================================ Lo que ve un agente
@prueba('Instantánea ARIA: cada control tiene nombre y el pago está deshabilitado sin pedido')
def _():
    with abrir() as page:
        snap = page.locator('body').aria_snapshot()
        SALIDA.mkdir(parents=True, exist_ok=True)
        nombre = re.sub(r'[^a-z0-9]+', '_', RUTA.lower()).strip('_')
        (SALIDA / f'aria_{nombre}.yml').write_text(snap + '\n', encoding='utf-8')
        for linea in ('- status:', f'radio "{NYERI}"', 'spinbutton "Cantidad de bolsas": "1"', 'button "Agregar al carrito"',
                      'textbox "Fecha de entrega"', 'button "Confirmar y pagar" [disabled]'):
            esperar(linea in snap, f'falta «{linea}»')


# ================================================================ Conjunto
@prueba('Ningún diálogo del navegador (alert, confirm, prompt) durante todo el conjunto')
def _():
    esperar(not DIALOGOS, '; '.join(DIALOGOS))


@prueba('Ningún error en la consola durante todo el conjunto')
def _():
    esperar(not CONSOLA, '; '.join(sorted(set(CONSOLA)))[:600])


def main():
    global NAV
    clave = PAGINA.relative_to(ROOT).as_posix() if PAGINA.is_relative_to(ROOT) else RUTA
    conocidos = CONOCIDOS.get(clave, {})
    inicio = time.time()
    with sync_playwright() as pw:
        NAV = pw.chromium.launch()
        axe_version = json.loads((NM / 'axe-core' / 'package.json').read_text())['version'] if AXE else 'no instalado'
        print(f'Pruebas de extremo a extremo: {clave}')
        print(f'Chromium {NAV.version} · Playwright {importlib.metadata.version("playwright")} · axe-core {axe_version}\n')
        cuenta = {'aprobadas': 0, 'fallidas': 0, 'conocidas': 0, 'omitidas': 0, 'inesperadas': 0}
        for i, (nombre, fn) in enumerate(PRUEBAS, 1):
            try:
                fn()
                if nombre in conocidos:
                    cuenta['inesperadas'] += 1
                    print(f'{i:2} APROBADA (se esperaba un fallo conocido)  {nombre}')
                else:
                    cuenta['aprobadas'] += 1
                    print(f'{i:2} PASA     {nombre}')
            except Omitida as exc:
                cuenta['omitidas'] += 1
                print(f'{i:2} OMITIDA  {nombre}  [{exc}]')
            except Exception as exc:  # noqa: BLE001 (se informa cualquier fallo)
                detalle = str(exc).strip().splitlines()[0][:400] if str(exc).strip() else type(exc).__name__
                if nombre in conocidos:
                    cuenta['conocidas'] += 1
                    print(f'{i:2} CONOCIDO {nombre}\n            {conocidos[nombre]}\n            [{detalle}]')
                else:
                    cuenta['fallidas'] += 1
                    print(f'{i:2} FALLA    {nombre}\n            [{detalle}]')
        NAV.close()
    total = len(PRUEBAS)
    print(f'\n{total} pruebas en {time.time() - inicio:.0f} s: {cuenta["aprobadas"]} aprobadas, {cuenta["fallidas"]} fallidas, '
          f'{cuenta["conocidas"]} fallos conocidos, {cuenta["omitidas"]} omitidas.')
    return 1 if cuenta['fallidas'] or cuenta['inesperadas'] else 0


if __name__ == '__main__':
    sys.exit(main())
