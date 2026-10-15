# -*- coding: utf-8 -*-
"""Pruebas de Grano Claro 1.1 en Chromium (Playwright): vistas, compra completa, recorrido del agente,
filtros, envío gratis, API, JSON, integridad del DOM, desbordamiento, axe-core, instantáneas ARIA y capturas.

Uso: python3 tests/probar_v1_1.py [ruta de la página, relativa al repositorio; por omisión index.html]
Requisitos: pip install -r requirements-dev.txt; python3 -m playwright install chromium; npm install
(axe-core y las fuentes; sin ellos se omiten las pruebas de axe y se usan fuentes del sistema).
Salidas: tests/salida/ (capturas, árboles e instantáneas ARIA)."""
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / (sys.argv[1] if len(sys.argv) > 1 else 'index.html')
URL = PAGE.as_uri()
OUT = ROOT / 'tests' / 'salida'
OUT.mkdir(parents=True, exist_ok=True)
SHOTS = OUT
NM = ROOT / 'node_modules'
AXE_PATH = NM / 'axe-core' / 'axe.min.js'
AXE = AXE_PATH.read_text(encoding='utf-8') if AXE_PATH.exists() else None
FONT_FILES = {
    ('Atkinson Hyperlegible Next', w): NM / '@fontsource/atkinson-hyperlegible-next/files' /
    f'atkinson-hyperlegible-next-latin-{w}-normal.woff2' for w in (400, 600, 700)}
FONT_FILES.update({
    ('Atkinson Hyperlegible Mono', w): NM / '@fontsource/atkinson-hyperlegible-mono/files' /
    f'atkinson-hyperlegible-mono-latin-{w}-normal.woff2' for w in (400, 600)})
FONT_FILES = {k: p for k, p in FONT_FILES.items() if p.exists()}
FONT_CSS = ''.join(
    f"@font-face{{font-family:'{fam}';font-style:normal;font-weight:{w};font-display:swap;"
    f"src:url(https://fonts.gstatic.com/local/{p.name}) format('woff2');}}" for (fam, w), p in FONT_FILES.items())
BY_NAME = {p.name: p for p in FONT_FILES.values()}

results = []


def check(cond, label, detail=''):
    results.append((bool(cond), label))
    print(('PASS  ' if cond else 'FAIL  ') + label + (f'  [{detail}]' if detail and not cond else ''))


def serve_fonts(route):
    url = route.request.url
    if url.startswith('https://fonts.googleapis.com/'):
        return route.fulfill(status=200, content_type='text/css', body=FONT_CSS)
    name = url.rsplit('/', 1)[-1]
    if name in BY_NAME:
        return route.fulfill(status=200, content_type='font/woff2', body=BY_NAME[name].read_bytes())
    return route.abort()


with sync_playwright() as pw:
    browser = pw.chromium.launch()

    def new_page(hash_='', width=1280, height=900, scheme='light'):
        ctx = browser.new_context(viewport={'width': width, 'height': height}, color_scheme=scheme)
        ctx.route(re.compile(r'https://fonts\.(googleapis|gstatic)\.com/.*'), serve_fonts)
        page = ctx.new_page()
        errs = []
        page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
        page.on('pageerror', lambda e: errs.append(str(e)))
        page.goto(URL + hash_)
        page.wait_for_function('document.documentElement.dataset.ready === "true"')
        page.evaluate('document.fonts.ready')
        return ctx, page, errs

    def code(page):
        return page.get_attribute('#status', 'data-code')

    def vis(page, sel):
        return page.locator(sel).first.is_visible()

    # ------------------------------------------------------------------ A. vista Persona por defecto
    ctx, page, errs = new_page()
    check(page.evaluate('document.documentElement.dataset.mode') == 'human', 'A1 vista Persona por defecto')
    check(page.evaluate('document.documentElement.lang') == 'es', 'A2 lang=es en el documento')
    check(page.title() == 'Grano Claro', 'A3 título corto', page.title())
    check(not vis(page, '#catalog-table-wrap'), 'A4 tabla oculta en vista Persona')
    check(page.locator('#product-cards .card:visible').count() == 13, 'A5 13 tarjetas visibles')
    check(page.locator('#group-cr .card').count() == 7 and page.locator('#group-other .card').count() == 6, 'A6 grupos 7 + 6')
    first_group = page.evaluate("document.querySelector('#product-cards .card-group').id")
    check(first_group == 'group-cr', 'A7 Costa Rica aparece primero')
    check(not vis(page, '#for-agents') and not vis(page, '#agent-console'), 'A8 secciones de agente ocultas')
    check(not vis(page, '.box-head .ref'), 'A9 designadores #id ocultos')
    check(vis(page, '#mode-switch') and page.is_checked('#mode-human'), 'A10 selector visible y en Persona')
    check(page.locator('#pick-GC-003').is_disabled() and page.inner_text('#pick-GC-003').strip().startswith('Agotado'),
          'A11 GC-003 agotado en tarjetas')
    check(not vis(page, '#status .meta'), 'A12 metadatos del estado ocultos para personas')
    check(page.inner_text('#add-to-cart legend >> nth=0').strip() == 'Café (elija una tarjeta)', 'A13 indicación de la leyenda en vista Persona',
          page.inner_text('#add-to-cart legend >> nth=0'))
    check(page.inner_text('#card-meta-GC-011') == 'Bolsa de 250 g · quedan 2 bolsas', 'A14 existencias en tarjeta',
          page.inner_text('#card-meta-GC-011'))
    page.screenshot(path=str(SHOTS / 'persona_desktop.png'), full_page=True)

    # ------------------------------------------------------------------ B. compra como persona
    page.get_by_role('button', name='Elegir Dota, Costa Rica, 340 g, USD 16.50').click()
    check(page.is_checked('#sku-GC-007'), 'B1 la tarjeta marca el radio GC-007')
    check(page.get_attribute('#pick-GC-007', 'aria-pressed') == 'true', 'B2 aria-pressed en la tarjeta elegida')
    check(page.evaluate('document.activeElement.id') == 'pick-summary', 'B3 el foco pasa al resumen de la elección')
    check('Café elegido: Dota, Costa Rica, 340 g, USD 16.50 por bolsa.' in page.inner_text('#pick-summary'), 'B4 resumen de la elección')
    page.get_by_label('Molido para filtro').check()
    page.fill('#add-quantity', '2')
    page.get_by_role('button', name='Agregar al carrito').click()
    check(code(page) == 'CART_ADDED', 'B5 agregado al carrito', code(page))
    check(page.inner_text('#cart-subtotal') == 'USD 33.00', 'B6 subtotal 2 × 16.50 = 33.00', page.inner_text('#cart-subtotal'))
    dmin = page.get_attribute('#p-date', 'data-min')
    page.fill('#p-full-name', 'Ana Rojas (ejemplo)')
    page.fill('#p-email', 'ana.rojas@example.com')
    page.check('#p-method-shipping')
    page.fill('#p-address', 'Calle 5, San José (ejemplo)')
    page.fill('#p-date', dmin)
    page.get_by_role('button', name='Preparar pedido (sin cobro)').click()
    check(code(page) == 'ORDER_PREPARED', 'B7 pedido preparado', code(page))
    check(page.inner_text('#summary-total') == 'USD 38.00', 'B8 total 33.00 + 5.00 de envío = 38.00', page.inner_text('#summary-total'))
    check(page.inner_text('#confirm-submit') == 'Confirmar y pagar USD 38.00' and page.is_enabled('#confirm-submit'),
          'B9 botón de pago habilitado con el monto')
    page.screenshot(path=str(SHOTS / 'persona_pedido.png'), full_page=False)

    # ------------------------------------------------------------------ C. vista Agente
    page.click('label[for="mode-agent"]')
    check(page.evaluate('document.documentElement.dataset.mode') == 'agent', 'C1 cambia a vista Agente')
    check(vis(page, '#catalog-table-wrap') and not vis(page, '#product-cards'), 'C2 tabla visible, tarjetas ocultas')
    check(vis(page, '#for-agents') and vis(page, '#agent-console') and vis(page, '.box-head .ref'), 'C3 secciones y designadores de agente')
    check(page.is_disabled('#confirm-submit') and vis(page, '#confirm-agent-note'), 'C4 pago desactivado en vista Agente, con nota')
    check(page.is_checked('#sku-GC-007'), 'C5 la elección se conserva entre vistas')
    check(page.inner_text('#add-to-cart legend >> nth=0').strip() == 'Café (marque una fila)', 'C5b leyenda de la vista Agente')
    check(page.inner_text('#mode-live').startswith('Vista Agente'), 'C6 anuncio del cambio de vista')
    page.fill('#c-total', '38.00')
    page.evaluate("document.querySelector('#confirm-order').requestSubmit()")
    check(code(page) == 'ERR_HUMAN_STEP', 'C7 enviar el pago desde la vista Agente se rechaza', code(page))
    check(page.evaluate('granoClaro.snapshot().order.status') == 'pending_confirmation', 'C8 el pedido sigue pendiente')
    check(page.evaluate("localStorage.getItem('granoclaro:modo')") == 'agent', 'C9 la vista se recuerda')
    page.reload()
    page.wait_for_function('document.documentElement.dataset.ready === "true"')
    check(page.evaluate('document.documentElement.dataset.mode') == 'agent', 'C10 tras recargar sigue en vista Agente')
    check(code(page) == 'STATE_RESTORED', 'C11 estado restaurado tras recargar', code(page))

    # ------------------------------------------------------------------ D. de vuelta a Persona: pagar
    page.click('label[for="mode-human"]')
    check(page.is_enabled('#confirm-submit'), 'D1 pago habilitado en vista Persona')
    page.fill('#c-total', '38.00')
    page.get_by_role('button', name='Confirmar y pagar USD 38.00').click()
    check(code(page) == 'ORDER_CONFIRMED', 'D2 pedido confirmado por la persona', code(page))
    check(page.inner_text('#card-meta-GC-007') == 'Bolsa de 340 g · quedan 12 bolsas', 'D3 existencias actualizadas en la tarjeta',
          page.inner_text('#card-meta-GC-007'))
    check(page.inner_text('#stock-GC-007') == '12 bolsas', 'D4 existencias actualizadas en la tabla')
    check(not errs, 'A–D sin errores de consola', '; '.join(errs))
    ctx.close()

    # ------------------------------------------------------------------ E. recorrido del agente con #modo-agente
    ctx, page, errs = new_page('#modo-agente')
    check(page.evaluate('document.documentElement.dataset.mode') == 'agent', 'E1 #modo-agente abre la vista Agente')
    page.click('#walk-all')
    page.wait_for_function("document.querySelector('#walk-mark-6').textContent.length > 0")
    m = [page.inner_text(f'#walk-mark-{i}') for i in range(1, 7)]
    check('SEARCH_OK' in m[0] and '7 de 13 cafés coinciden' in m[0], 'E2 paso 1: 7 de 13 cafés de Costa Rica', m[0])
    check('CART_ADDED' in m[1], 'E3 paso 2: agregado', m[1])
    check('CART_OK' in m[2] and 'USD 33.00' in m[2], 'E4 paso 3: carrito 33.00', m[2])
    check('ORDER_PREPARED' in m[3] and 'total USD 38.00' in m[3], 'E5 paso 4: total 38.00', m[3])
    check('AWAITING_USER' in m[4] and page.input_value('#c-total') == '38.00', 'E6 paso 5: total escrito sin enviar', m[4])
    check('ERR_HUMAN_STEP' in m[5] and page.get_attribute('#walk-mark-6', 'data-state') == 'expected', 'E7 paso 6: ERR_HUMAN_STEP esperado', m[5])
    out = json.loads(page.inner_text('#console-output'))
    check(out['code'] == 'ERR_HUMAN_STEP' and out['ok'] is False, 'E8 resultado JSON de la consola')
    check(page.locator('#console-log li').count() == 6, 'E9 registro de 6 llamadas')
    check(page.evaluate('granoClaro.snapshot().order.status') == 'pending_confirmation', 'E10 nada se cobró')
    snap = json.loads(page.text_content('#peek-snapshot'))
    check(snap['view_mode'] == 'agent' and snap['order']['total_usd'] == '38.00', 'E11 instantánea con vista y total')
    page.screenshot(path=str(SHOTS / 'agente_desktop.png'), full_page=True)
    # Llamada libre con JSON inválido
    page.select_option('#console-tool', 'get_cart')
    page.fill('#console-args', '{sku: GC-001}')
    page.click('#console-run')
    check(json.loads(page.inner_text('#console-output'))['code'] == 'ERR_JSON', 'E12 JSON inválido en la consola')
    # Árbol de accesibilidad
    page.click('#peek-ax-panel > summary')
    page.wait_for_function("document.querySelector('#peek-ax').textContent.length > 0")
    ax_agent = page.inner_text('#peek-ax')
    check('row "GC-007 | Dota Región Los Santos, 1750 m | Costa Rica (CR) | Caturra, Catuaí' in ax_agent,
          'E13 árbol (Agente) con filas de la tabla', ax_agent[:300])
    page.click('label[for="ax-human"]')
    ax_human = page.inner_text('#peek-ax')
    check('heading "Dota" (nivel 5)' in ax_human and 'button "Elegir Dota, Costa Rica, 340 g, USD 16.50"' in ax_human,
          'E14 árbol (Persona) con tarjetas')
    check('row "GC-007' not in ax_human and 'Para agentes' not in ax_human and 'group "Café (elija una tarjeta)"' in ax_human
          and 'radio "Persona" (marcado)' in ax_human, 'E15 árbol (Persona) sin tabla ni sección de agentes, con su leyenda y su radio')
    check('group "Café (marque una fila)"' in ax_agent and 'radio "Agente" (marcado)' in ax_agent, 'E15b árbol (Agente) con su leyenda y su radio')
    counts = page.inner_text('#peek-ax-count')
    check(re.search(r'Vista Persona: \d+ nodos\. Vista Agente: \d+ nodos\.', counts) is not None, 'E16 conteo de nodos', counts)
    print('      ', counts)
    check(page.evaluate('document.documentElement.dataset.mode') == 'agent', 'E17 calcular el árbol no cambia la vista')
    (OUT / 'ax_persona.txt').write_text(ax_human, encoding='utf-8')
    (OUT / 'ax_agente.txt').write_text(ax_agent, encoding='utf-8')
    # Entrega a la persona
    page.click('#walk-handoff')
    check(page.evaluate('document.documentElement.dataset.mode') == 'human', 'E18 el botón pasa a la vista Persona')
    check(page.evaluate('document.activeElement.id') == 'c-total', 'E19 el foco queda en el total escrito')
    check(page.evaluate('location.hash') == '', 'E20 se limpia #modo-agente para no contradecir la elección')
    check(page.is_enabled('#confirm-submit'), 'E21 la persona puede pagar')
    check(not errs, 'E sin errores de consola', '; '.join(errs))
    ctx.close()

    # ------------------------------------------------------------------ F. filtros y búsqueda
    ctx, page, errs = new_page()
    page.select_option('#f-variety', 'Villa Sarchí')
    page.get_by_role('button', name='Aplicar filtros').click()
    check(page.inner_text('#filters-result') == 'Mostrando 1 de 13 cafés.', 'F1 filtro por variedad', page.inner_text('#filters-result'))
    check(page.locator('#product-cards .card:visible').count() == 1 and vis(page, '#card-GC-008'), 'F2 una tarjeta: Sarchí')
    check(not vis(page, '#group-other') and page.inner_text('#group-cr-count') == '1 de 7 cafés', 'F3 grupos y conteos')
    page.click('label[for="mode-agent"]')
    check(page.locator('#catalog-table tbody tr:visible').count() == 1, 'F4 una fila en la tabla')
    api = lambda args: page.evaluate('(a) => granoClaro.call("search_products", a)', args)  # noqa: E731
    r = api({'variety': 'geisha'})
    check(r['ok'] and [p['sku'] for p in r['data']['products']] == ['GC-011'], 'F5 variedad sin distinguir mayúsculas ni tildes')
    r = api({'variety': 'Typica'})
    check(not r['ok'] and r['code'] == 'ERR_VALIDATION' and r['field'] == 'variety', 'F6 variedad desconocida')
    r = api({'query': 'honey'})
    check(r['ok'] and [p['sku'] for p in r['data']['products']] == ['GC-008', 'GC-012'], 'F7 búsqueda por proceso honey')
    r = api({'query': 'jazmin'})
    check(r['ok'] and [p['sku'] for p in r['data']['products']] == ['GC-002', 'GC-011'], 'F8 búsqueda en notas de cata')
    r = api({'query': 'los santos'})
    check(r['ok'] and [p['sku'] for p in r['data']['products']] == ['GC-007'], 'F9 búsqueda por región')
    r = api({'origin': 'cr', 'roast': 'light'})
    check(r['ok'] and [p['sku'] for p in r['data']['products']] == ['GC-008', 'GC-011'], 'F10 origen CR + tueste claro')
    p7 = next(p for p in api({'origin': 'CR'})['data']['products'] if p['sku'] == 'GC-007')
    check(p7['region'] == 'Los Santos' and p7['varieties'] == ['Caturra', 'Catuaí'] and p7['altitude_m'] == 1750, 'F11 datos nuevos en productView')
    page.get_by_role('button', name='Quitar filtros').click()
    check(page.inner_text('#filters-result') == 'Mostrando 13 de 13 cafés.', 'F12 quitar filtros')
    check(not errs, 'F sin errores de consola', '; '.join(errs))
    ctx.close()

    # ------------------------------------------------------------------ G. envío gratis y límites (API)
    ctx, page, errs = new_page('#modo-agente')
    call = lambda n, a: page.evaluate('([n, a]) => granoClaro.call(n, a)', [n, a])  # noqa: E731
    dmin = page.get_attribute('#p-date', 'data-min')
    order = {'full_name': 'Ana Rojas (ejemplo)', 'email': 'ana.rojas@example.com', 'delivery_method': 'shipping',
             'address': 'Calle 5, San José (ejemplo)', 'delivery_date': dmin}
    call('add_to_cart', {'sku': 'GC-006', 'grind': 'whole', 'quantity': 1})
    call('add_to_cart', {'sku': 'GC-011', 'grind': 'whole', 'quantity': 1})
    o = call('prepare_order', order)['data']['order']
    check((o['subtotal_usd'], o['shipping_usd'], o['total_usd']) == ('40.00', '0.00', '40.00'), 'G1 14.00 + 26.00 = 40.00: envío gratis', o['total_usd'])
    call('remove_from_cart', {'line_id': 'L1'})
    call('add_to_cart', {'sku': 'GC-013', 'grind': 'whole', 'quantity': 1})
    o = call('prepare_order', order)['data']['order']
    check((o['subtotal_usd'], o['shipping_usd'], o['total_usd']) == ('39.50', '5.00', '44.50'), 'G2 26.00 + 13.50 = 39.50 + 5.00 = 44.50', o['total_usd'])
    r = call('add_to_cart', {'sku': 'GC-011', 'grind': 'whole', 'quantity': 2})
    check(not r['ok'] and r['code'] == 'ERR_STOCK', 'G3 GC-011 solo tiene 2 bolsas', r.get('code'))
    r = call('confirm_order', {'total_confirmation': '44.50'})
    check(r['code'] == 'ERR_HUMAN_STEP', 'G4 confirm_order por JavaScript sigue rechazado')
    check(page.evaluate('granoClaro.version') == '1.1' and page.evaluate('granoClaro.tools.length') == 5, 'G5 versión 1.1 y 5 herramientas JS')
    check(page.evaluate('granoClaro.view()') == 'agent', 'G6 granoClaro.view()')
    check(not errs, 'G sin errores de consola', '; '.join(errs))

    # ------------------------------------------------------------------ I. JSON y coherencia entre fuentes
    ld = json.loads(page.evaluate("document.querySelector('script[type=\"application/ld+json\"]').textContent"))
    items = next(g for g in ld['@graph'] if g['@type'] == 'ItemList')
    check(items['numberOfItems'] == 13 and len(items['itemListElement']) == 13, 'I1 JSON-LD con 13 productos')
    cr_items = [x['item'] for x in items['itemListElement'] if x['item']['countryOfOrigin']['identifier'] == 'CR']
    check(len(cr_items) == 7 and all(any(pv['name'] == 'altitud' and pv['unitCode'] == 'MTR' for pv in x['additionalProperty'])
                                    for x in cr_items), 'I2 7 productos de CR con altitud en metros')
    tools = json.loads(page.evaluate("document.getElementById('agent-tools').textContent"))
    sp = tools['tools'][0]['inputSchema']['properties']
    check(tools['version'] == '1.1' and list(sp) == ['query', 'origin', 'variety', 'roast', 'max_price_usd', 'in_stock_only'],
          'I3 esquema search_products con variety')
    check('CR' in sp['origin']['enum'] and len(sp['variety']['enum']) == 14, 'I4 enums de origen y variedad')
    check(len(tools['tools'][1]['inputSchema']['properties']['sku']['enum']) == 13, 'I5 enum de SKU con 13')
    same = page.evaluate("""(t) => {
      const f = document.getElementById('filters');
      const sp = t.tools[0];
      return f.getAttribute('tooldescription') === sp.description
        && document.getElementById('f-variety').getAttribute('toolparamdescription') === sp.inputSchema.properties.variety.description
        && document.getElementById('f-query').getAttribute('toolparamdescription') === sp.inputSchema.properties.query.description
        && JSON.stringify(Array.from(document.querySelectorAll('#f-variety option'), (o) => o.value)) === JSON.stringify(sp.inputSchema.properties.variety.enum)
        && JSON.stringify(Array.from(document.querySelectorAll('#f-origin option'), (o) => o.value)) === JSON.stringify(sp.inputSchema.properties.origin.enum);
    }""", tools)
    check(same, 'I6 formulario y esquema coinciden (descripciones y opciones)')
    table_vs_ld = page.evaluate("""(ld) => {
      const items = ld['@graph'].find((g) => g['@type'] === 'ItemList').itemListElement.map((x) => x.item);
      return items.every((it) => {
        const tr = document.getElementById('product-' + it.sku);
        return tr && tr.dataset.priceUsd === it.offers.price && Number(tr.dataset.stock) === it.offers.inventoryLevel.value
          && tr.dataset.name === it.name;
      });
    }""", ld)
    check(table_vs_ld, 'I7 tabla y JSON-LD coinciden en nombre, precio y existencias')

    # ------------------------------------------------------------------ J. integridad del DOM
    dom = page.evaluate("""() => {
      const ids = Array.from(document.querySelectorAll('[id]'), (e) => e.id);
      const dup = ids.filter((id, i) => ids.indexOf(id) !== i);
      const broken = [];
      document.querySelectorAll('[aria-labelledby],[aria-describedby],label[for]').forEach((el) => {
        const refs = [el.getAttribute('aria-labelledby'), el.getAttribute('aria-describedby'), el.getAttribute('for')]
          .filter(Boolean).join(' ').split(/\\s+/);
        refs.forEach((r) => { if (!document.getElementById(r)) broken.push(r); });
      });
      return { dup, broken };
    }""")
    check(not dom['dup'], 'J1 sin id duplicados', str(dom['dup']))
    check(not dom['broken'], 'J2 todas las referencias de id existen', str(dom['broken']))
    ctx.close()

    # ------------------------------------------------------------------ K. desbordamiento horizontal y móvil
    for hash_, label in (('#modo-persona', 'Persona'), ('#modo-agente', 'Agente')):
        for width in (390, 1280):
            ctx, page, errs = new_page(hash_, width=width, height=844)
            # Oráculo fijo: se compara con el ancho pedido, no con el de la ventana (que puede crecer con el contenido).
            fuera = page.evaluate("""(ancho) => Array.from(document.body.querySelectorAll('*')).filter((el) => {
                const r = el.getBoundingClientRect();
                if (!r.width || !r.height || (r.width <= 1 && r.height <= 1) || !el.checkVisibility()) return false;
                for (let a = el.parentElement; a; a = a.parentElement) {
                  if (['auto', 'scroll', 'hidden', 'clip'].includes(getComputedStyle(a).overflowX)) return false;
                }
                return r.right > ancho + 0.5 || r.left < -0.5;
              }).map((el) => el.tagName.toLowerCase() + (el.id ? '#' + el.id : ''))""", width)
            check(not fuera, f'K ningún elemento sobresale de {width} px (oráculo fijo): {label}', ', '.join(fuera[:8]))
            if width == 390:
                page.screenshot(path=str(SHOTS / f'{label.lower()}_movil.png'), full_page=True)
            ctx.close()

    # ------------------------------------------------------------------ L. axe-core en ambas vistas y en oscuro
    if AXE is None:
        print('OMIT  L axe-core: falta node_modules/axe-core (ejecute npm install)')
    L_CASES = (('#modo-persona', 'Persona', 'light'), ('#modo-agente', 'Agente', 'light'),
               ('#modo-persona', 'Persona oscuro', 'dark'), ('#modo-agente', 'Agente oscuro', 'dark'))
    for hash_, label, scheme in (L_CASES if AXE else ()):
        ctx, page, errs = new_page(hash_, scheme=scheme)
        if 'Agente' in label:
            page.click('#walk-all')
            page.wait_for_function("document.querySelector('#walk-mark-6').textContent.length > 0")
            for d in page.locator('details.peek').all():
                d.evaluate('(el) => { el.open = true; }')
        else:
            page.get_by_role('button', name='Elegir Sarchí, Costa Rica, 340 g, USD 18.00').click()
        page.add_script_tag(content=AXE)
        res = page.evaluate("""async () => {
          const r = await axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'] } });
          return r.violations.map((v) => ({ id: v.id, impact: v.impact, n: v.nodes.length, sample: v.nodes.slice(0, 3).map((x) => x.target.join(' ') + ' :: ' + (x.failureSummary || '').split('\\n').slice(0, 2).join(' ')) }));
        }""")
        check(not res, f'L axe-core sin infracciones: {label}', json.dumps(res, ensure_ascii=False)[:1500])
        if scheme == 'dark':
            page.screenshot(path=str(SHOTS / f'{label.replace(" ", "_").lower()}.png'), full_page=False)
        check(not errs, f'L sin errores de consola: {label}', '; '.join(errs))
        ctx.close()

    # ------------------------------------------------------------------ M. instantáneas ARIA (formato de Playwright)
    for hash_, view in (('#modo-persona', 'persona'), ('#modo-agente', 'agente')):
        ctx, page, errs = new_page(hash_)
        snap = page.locator('body').aria_snapshot()
        (OUT / f'aria_v1.1_{view}.yml').write_text(snap + '\n', encoding='utf-8')
        check(('- row "' in snap and 'GC-007' in snap) == (view == 'agente'), f'M instantánea ARIA, vista {view}: la tabla solo existe en Agente')
        ctx.close()
    v10 = ROOT / 'versions' / 'v1.0' / 'index.html'
    if v10.exists():
        ctx = browser.new_context(viewport={'width': 1280, 'height': 900})
        ctx.route(re.compile(r'https://fonts\.(googleapis|gstatic)\.com/.*'), serve_fonts)
        page = ctx.new_page()
        page.goto(v10.as_uri())
        page.wait_for_function('document.documentElement.dataset.ready === "true"')
        (OUT / 'aria_v1.0.yml').write_text(page.locator('body').aria_snapshot() + '\n', encoding='utf-8')
        ctx.close()

    # ------------------------------------------------------------------ N. capturas para docs/
    ctx, page, errs = new_page('#modo-persona')
    box = page.locator('#top').bounding_box()
    page.screenshot(path=str(OUT / 'selector.png'), clip={'x': box['x'] - 24, 'y': max(0, box['y'] - 24),
                                                          'width': box['width'] + 48, 'height': box['height'] + 48})
    page.get_by_role('button', name='Elegir Rivas, Costa Rica, 250 g, USD 26.00').click()
    page.locator('#group-cr').screenshot(path=str(OUT / 'vista-persona.png'))
    ctx.close()
    ctx, page, errs = new_page('#modo-agente')
    page.click('#walk-all')
    page.wait_for_function("document.querySelector('#walk-mark-6').textContent.length > 0")
    page.locator('#walk').screenshot(path=str(OUT / 'vista-agente.png'))
    ctx.close()
    ctx, page, errs = new_page('#modo-persona', width=390, height=844, scheme='dark')
    page.screenshot(path=str(OUT / 'movil-oscuro.png'))
    ctx.close()

    browser.close()

failed = [l for ok, l in results if not ok]
print(f'\n{len(results) - len(failed)} de {len(results)} comprobaciones aprobadas'
      + ('.' if AXE else ' (sin axe-core: ejecute npm install para incluirlo).'))
sys.exit(1 if failed else 0)
