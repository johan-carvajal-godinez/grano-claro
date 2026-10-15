//@@ early
<script>
(() => {
  /* Aplica la vista elegida antes de pintar la página, para que la otra no parpadee. */
  const root = document.documentElement;
  root.lang = 'es';
  let mode = { '#modo-agente': 'agent', '#modo-persona': 'human' }[location.hash] || '';
  if (!mode) {
    try { const saved = localStorage.getItem('granoclaro:modo'); if (saved === 'agent' || saved === 'human') mode = saved; }
    catch (err) { /* Sin almacenamiento: vista Persona. */ }
  }
  root.dataset.mode = mode || 'human';
})();
</script>
//@@ new
  /* ---------- Vistas: Persona y Agente (mismos datos, mismo carrito, mismo pedido) ---------- */
  const MODE_HASH = { '#modo-agente': 'agent', '#modo-persona': 'human' };
  function currentMode() { return root.dataset.mode === 'agent' ? 'agent' : 'human'; }
  function storedMode() {
    try { const saved = localStorage.getItem(MODE_KEY); return saved === 'agent' || saved === 'human' ? saved : null; }
    catch (err) { return null; }
  }
  function setMode(mode, announce) {
    const m = mode === 'agent' ? 'agent' : 'human';
    root.dataset.mode = m;
    $('#mode-human').checked = m === 'human';
    $('#mode-agent').checked = m === 'agent';
    try { localStorage.setItem(MODE_KEY, m); } catch (err) { /* Sin almacenamiento: la vista vale para esta visita. */ }
    renderOrder();
    refreshConsole();
    if (announce) {
      $('#mode-live').textContent = m === 'agent'
        ? 'Vista Agente: tabla con SKU, herramientas y consola.'
        : 'Vista Persona: tarjetas con variedad, proceso y notas de cata.';
    }
  }
  function switchMode(mode) {
    const fromHash = MODE_HASH[location.hash];
    if (fromHash && fromHash !== mode) {
      try { history.replaceState(null, '', `${location.pathname}${location.search}`); } catch (err) { /* Sin history: la vista cambia igual. */ }
    }
    setMode(mode, true);
  }
  $('#mode-switch').addEventListener('change', (event) => {
    if (event.target.name === 'view_mode') switchMode(event.target.value);
  });
  window.addEventListener('hashchange', () => {
    const m = MODE_HASH[location.hash];
    if (m) setMode(m, true);
  });

  /* ---------- Vista Persona: tarjetas generadas desde las mismas filas del catálogo ---------- */
  const CHECK_ICON = '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="M2.5 8.5l3.5 3.5 7.5-8" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const GROUPS = [
    { id: 'cr', title: 'De Costa Rica', test: (p) => p.origin === 'CR' },
    { id: 'other', title: 'De otros orígenes', test: (p) => p.origin !== 'CR' }
  ];
  const joinList = (items) => (items.length < 2 ? items.join('') : `${items.slice(0, -1).join(', ')} y ${items[items.length - 1]}`);
  function cardFor(p) {
    const li = document.createElement('li');
    li.className = 'card';
    li.id = `card-${p.sku}`;
    li.dataset.sku = p.sku;
    li.innerHTML =
      `<div class="card-top"><span class="chip${p.origin === 'CR' ? ' chip--cr' : ''}">${esc(p.origin_name)}</span></div>` +
      `<h5 class="card-name">${esc(p.short)}</h5>` +
      (p.altitude_m ? `<p class="card-where">Región ${esc(p.region)} · ${p.altitude_m}\u00a0m</p>` : '') +
      '<dl class="facts">' +
      `<div><dt>${p.varieties.length > 1 ? 'Variedades' : 'Variedad'}</dt><dd>${esc(joinList(p.varieties))}</dd></div>` +
      `<div><dt>Proceso</dt><dd>${esc(p.process)}</dd></div>` +
      `<div><dt>Tueste</dt><dd>${esc(ROASTS[p.roast])}</dd></div>` +
      `<div><dt>Notas</dt><dd>${esc(p.notes)}</dd></div>` +
      '</dl>' +
      '<div class="card-foot">' +
      `<p class="card-price"><data value="${money(p.price_cents)}">${usd(p.price_cents)}</data></p>` +
      `<p class="card-meta" id="card-meta-${p.sku}"></p>` +
      `<button type="button" class="secondary small pick-btn" id="pick-${p.sku}" data-sku="${p.sku}" aria-pressed="false" aria-describedby="card-meta-${p.sku}">` +
      `${CHECK_ICON}<span class="pick-label">Elegir</span><span class="sr-only"> ${esc(p.name)}, ${usd(p.price_cents)}</span></button>` +
      '</div>';
    return li;
  }
  function buildCards() {
    const items = Array.from(catalog.values());
    $('#product-cards').replaceChildren(...GROUPS.map((g) => {
      const group = document.createElement('div');
      group.className = 'card-group';
      group.id = `group-${g.id}`;
      group.innerHTML = `<h4 class="group-title">${g.title} <span class="hint" id="group-${g.id}-count"></span></h4>`;
      const list = document.createElement('ul');
      list.className = 'cards';
      list.setAttribute('role', 'list');
      list.append(...items.filter(g.test).map(cardFor));
      group.append(list);
      return group;
    }));
    renderCards();
    updateGroupCounts();
  }
  function updateGroupCounts() {
    GROUPS.forEach((g) => {
      const group = document.getElementById(`group-${g.id}`);
      if (!group) return;
      const cards = $$('.card', group);
      const shown = cards.filter((card) => !card.hidden).length;
      group.hidden = shown === 0;
      $(`#group-${g.id}-count`).textContent = shown === cards.length ? `${cards.length} cafés` : `${shown} de ${cards.length} cafés`;
    });
  }
  function renderCards() {
    for (const p of catalog.values()) {
      const meta = document.getElementById(`card-meta-${p.sku}`);
      if (!meta) continue;
      const out = p.stock <= 0;
      document.getElementById(`card-${p.sku}`).classList.toggle('is-out', out);
      meta.textContent = `Bolsa de ${p.weight_g} g · ${out ? 'agotado' : `${p.stock === 1 ? 'queda' : 'quedan'} ${bags(p.stock)}`}`;
      const button = document.getElementById(`pick-${p.sku}`);
      button.disabled = out;
      $('.pick-label', button).textContent = out ? 'Agotado' : 'Elegir';
    }
    syncPicked();
  }
  function syncPicked() {
    const picked = $('#add-to-cart input[name="sku"]:checked');
    $$('#product-cards .pick-btn').forEach((button) => {
      const on = Boolean(picked) && picked.value === button.dataset.sku;
      button.setAttribute('aria-pressed', String(on));
      button.closest('.card').classList.toggle('is-picked', on);
    });
    const out = $('#pick-summary');
    if (!picked) {
      out.dataset.state = 'empty';
      out.textContent = 'Todavía no ha elegido un café: use «Elegir» en una tarjeta.';
      return;
    }
    const p = catalog.get(picked.value);
    out.dataset.state = 'picked';
    out.textContent = `Café elegido: ${p.name}, ${usd(p.price_cents)} por bolsa. Ahora elija la molienda y la cantidad.`;
  }
  $('#product-cards').addEventListener('click', (event) => {
    const button = event.target.closest('button.pick-btn');
    if (!button || button.disabled) return;
    const radio = document.getElementById(`sku-${button.dataset.sku}`);
    if (!radio || radio.disabled) return;
    radio.checked = true;
    updateQuantityLimit();
    syncPicked();
    $('#pick-summary').focus();
  });

  /* ---------- Vista Agente: consola sobre la misma API que usa un agente ---------- */
  let consoleReady = false;
  let callCount = 0;
  const callLog = [];
  const EXAMPLES = {
    search_products: () => ({ origin: 'CR', variety: 'Geisha' }),
    add_to_cart: () => ({ sku: 'GC-008', grind: 'whole', quantity: 1 }),
    remove_from_cart: () => ({ line_id: state.cart.length ? state.cart[0].line_id : 'L1' }),
    get_cart: () => ({}),
    prepare_order: () => ({ full_name: 'Ana Rojas (ejemplo)', email: 'ana.rojas@example.com', delivery_method: 'shipping', address: 'Calle 5, San José (ejemplo)', delivery_date: deliveryRange().min }),
    confirm_order: () => ({ total_confirmation: state.order && state.order.status === 'pending_confirmation' ? money(state.order.total_cents) : '38.00' })
  };
  const WALK = [
    { tool: 'search_products', args: () => ({ origin: 'CR', in_stock_only: true }) },
    { tool: 'add_to_cart', args: () => ({ sku: 'GC-007', grind: 'filter', quantity: 2 }) },
    { tool: 'get_cart', args: () => ({}) },
    { tool: 'prepare_order', args: EXAMPLES.prepare_order },
    { tool: 'fill_confirmation', args: () => ({}) },
    { tool: 'confirm_order', args: EXAMPLES.confirm_order }
  ];
  function fillConfirmation() {
    refreshExpiry();
    const o = state.order;
    if (!o || o.status !== 'pending_confirmation') return failure('ERR_NO_PENDING_ORDER', 'No hay ningún pedido pendiente de aprobación.', 'Prepare antes el pedido (paso 4 o prepare_order).');
    $('#c-total').value = money(o.total_cents);
    return success('AWAITING_USER', `El agente escribió ${money(o.total_cents)} en el paso 2 (#confirm-order) sin enviarlo. Falta que la persona usuaria revise el total y pulse «Confirmar y pagar» en la vista Persona.`, { order_id: o.order_id, total_confirmation: money(o.total_cents), submitted: false });
  }
  function showResult(tool, args, result) {
    callCount += 1;
    $('#console-output-label').textContent = `Resultado de ${tool} (llamada ${callCount})`;
    $('#console-output').textContent = JSON.stringify(result, null, 2);
    const summary = $('#console-summary');
    summary.dataset.state = result.ok ? 'success' : 'error';
    summary.textContent = `${tool}: ${result.ok ? 'ok' : 'error'}, ${result.code}.`;
    callLog.unshift({ n: callCount, tool, args: typeof args === 'string' ? args : JSON.stringify(args), ok: result.ok, code: result.code });
    if (callLog.length > 8) callLog.length = 8;
    $('#console-log').replaceChildren(...callLog.map((c) => {
      const li = document.createElement('li');
      li.innerHTML = `${c.n}. <code>${esc(c.tool)}</code> <code>${esc(c.args)}</code> → <strong class="${c.ok ? 'is-ok' : 'is-err'}">${esc(c.code)}</strong>`;
      return li;
    }));
  }
  async function runTool(tool, args) {
    let result;
    if (tool === 'fill_confirmation') {
      const r = fillConfirmation();
      result = report(r, r.ok ? 'info' : undefined);
    } else {
      result = await call(tool, args);
    }
    showResult(tool, args, result);
    return result;
  }
  async function runWalkStep(i) {
    const step = WALK[i];
    const args = step.args();
    if (step.tool !== 'fill_confirmation') {
      $('#console-tool').value = step.tool;
      $('#console-args').value = JSON.stringify(args, null, 2);
    }
    const result = await runTool(step.tool, args);
    const expected = step.tool === 'confirm_order' && result.code === 'ERR_HUMAN_STEP';
    const mark = $(`#walk-mark-${i + 1}`);
    mark.dataset.state = expected ? 'expected' : result.ok ? 'success' : 'error';
    const label = document.createElement('strong');
    label.textContent = expected ? `Rechazado, como se esperaba (${result.code}):` : `${result.ok ? 'Hecho' : 'Error'} (${result.code}):`;
    mark.replaceChildren(label, ` ${expected ? result.hint : result.message}${!expected && !result.ok && result.hint ? ` ${result.hint}` : ''}`);
    return { result, expected };
  }
  function loadExample() {
    const make = EXAMPLES[$('#console-tool').value];
    $('#console-args').value = JSON.stringify(make ? make() : {}, null, 2);
  }
  function refreshConsole() {
    if (!consoleReady || currentMode() !== 'agent') return;
    $('#peek-snapshot').textContent = JSON.stringify(window.granoClaro.snapshot(), null, 2);
    if ($('#peek-ax-panel').open) renderAx();
  }
  function setupConsole() {
    const select = $('#console-tool');
    select.replaceChildren(...TOOLS.map((t) => {
      const option = document.createElement('option');
      option.value = t.name;
      option.textContent = t.binding.javascript ? t.name : `${t.name} (solo la persona)`;
      return option;
    }));
    loadExample();
    select.addEventListener('change', loadExample);
    $('#console-example').addEventListener('click', loadExample);
    $('#console-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const raw = $('#console-args').value.trim();
      let args;
      try { args = raw ? JSON.parse(raw) : {}; }
      catch (err) {
        showResult(select.value, raw, failure('ERR_JSON', 'Los argumentos no son JSON válido.', `Revise comillas, comas y llaves. Detalle: ${err.message}`));
        return;
      }
      await runTool(select.value, args);
    });
    $('#walk').addEventListener('click', (event) => {
      const button = event.target.closest('button[data-walk]');
      if (button) runWalkStep(Number(button.dataset.walk));
    });
    $('#walk-all').addEventListener('click', async () => {
      for (let i = 0; i < WALK.length; i += 1) {
        const { result, expected } = await runWalkStep(i);
        if (!result.ok && !expected) break;
      }
    });
    $('#walk-handoff').addEventListener('click', () => {
      switchMode('human');
      const pending = state.order && state.order.status === 'pending_confirmation';
      (pending ? $('#c-total') : $('#cart-title')).focus();
    });
    $('#peek-tools').textContent = JSON.stringify(JSON.parse($('#agent-tools').textContent), null, 2);
    $('#peek-jsonld').textContent = JSON.stringify(JSON.parse($('script[type="application/ld+json"]').textContent), null, 2);
    $('#peek-ax-panel').addEventListener('toggle', () => { if ($('#peek-ax-panel').open) renderAx(); });
    $$('input[name="ax_view"]').forEach((radio) => radio.addEventListener('change', renderAx));
    consoleReady = true;
    refreshConsole();
  }

  /* Árbol de accesibilidad aproximado: roles y nombres calculados aquí; no es el árbol exacto del navegador. */
  const AX_LEAF = new Set(['heading', 'link', 'button', 'textbox', 'searchbox', 'combobox', 'radio', 'checkbox', 'spinbutton', 'status']);
  const AX_SHOW = new Set([...AX_LEAF, 'banner', 'navigation', 'main', 'contentinfo', 'region', 'form', 'search', 'group', 'list', 'table', 'article']);
  const clip = (s, n) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);
  const textOf = (el) => String(el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
  function accName(el) {
    const ids = el.getAttribute('aria-labelledby');
    if (ids) return ids.split(/\s+/).map((id) => { const t = document.getElementById(id); return t ? textOf(t) : ''; }).filter(Boolean).join(' ');
    const label = el.getAttribute('aria-label');
    if (label) return label.trim();
    if (el.labels && el.labels.length) return Array.from(el.labels, textOf).join(' ');
    const tag = el.localName;
    if (tag === 'fieldset') { const legend = $(':scope > legend', el); return legend ? textOf(legend) : ''; }
    if (tag === 'table') return el.caption ? textOf(el.caption) : '';
    return /^(a|button|summary|h[1-6])$/.test(tag) ? textOf(el) : '';
  }
  function roleOf(el) {
    const explicit = el.getAttribute('role');
    if (explicit) return explicit.split(/\s+/)[0];
    const tag = el.localName;
    if (/^h[1-6]$/.test(tag)) return 'heading';
    switch (tag) {
      case 'header': return el.closest('main, section, article') ? null : 'banner';
      case 'footer': return el.closest('main, section, article') ? null : 'contentinfo';
      case 'nav': return 'navigation';
      case 'main': return 'main';
      case 'section': return el.hasAttribute('aria-labelledby') || el.hasAttribute('aria-label') ? 'region' : null;
      case 'form': return accName(el) ? 'form' : null;
      case 'article': return 'article';
      case 'a': return el.hasAttribute('href') ? 'link' : null;
      case 'button': case 'summary': return 'button';
      case 'select': return 'combobox';
      case 'textarea': return 'textbox';
      case 'fieldset': case 'details': return 'group';
      case 'table': return 'table';
      case 'ul': case 'ol': return 'list';
      case 'input': {
        const type = (el.getAttribute('type') || 'text').toLowerCase();
        const map = { search: 'searchbox', checkbox: 'checkbox', radio: 'radio', number: 'spinbutton', button: 'button', submit: 'button', hidden: null };
        return type in map ? map[type] : 'textbox';
      }
      default: return null;
    }
  }
  function isHiddenEl(el) {
    if (el.hidden || el.getAttribute('aria-hidden') === 'true') return true;
    const cs = getComputedStyle(el);
    return cs.display === 'none' || cs.visibility === 'hidden';
  }
  function describe(el, role) {
    if (role === 'status') return `status "${clip(textOf(el), 100)}"`;
    const name = accName(el);
    let s = name ? `${role} "${clip(name, 100)}"` : role;
    if (role === 'heading') s += ` (nivel ${el.localName.slice(1)})`;
    if ((role === 'radio' || role === 'checkbox') && el.checked) s += ' (marcado)';
    if (el.getAttribute('aria-pressed') === 'true') s += ' (pulsado)';
    if (el.matches(':disabled')) s += ' (desactivado)';
    if (['textbox', 'searchbox', 'spinbutton'].includes(role) && el.value) s += ` = "${clip(el.value, 40)}"`;
    if (role === 'combobox' && el.selectedOptions && el.selectedOptions[0]) s += ` = "${textOf(el.selectedOptions[0])}"`;
    if (role === 'list') s += ` (${el.children.length} elementos)`;
    return s;
  }
  function axTable(table, depth, out) {
    Array.from(table.rows).forEach((tr) => {
      if (isHiddenEl(tr)) return;
      const cells = Array.from(tr.cells, textOf).filter(Boolean).join(' | ');
      const radio = $('input[type="radio"]', tr);
      const flag = radio ? (radio.checked ? ' (radio marcado)' : radio.disabled ? ' (radio desactivado)' : ' (radio)') : '';
      out.push(`${'  '.repeat(depth)}row "${clip(cells, 150)}"${flag}`);
    });
  }
  function axWalk(el, depth, out) {
    for (const child of el.children) {
      if (child.matches('script, style, template, noscript, #agent-console') || isHiddenEl(child)) continue;
      if (child.localName === 'details' && !child.open) {
        const summary = $(':scope > summary', child);
        if (summary) out.push(`${'  '.repeat(depth)}${describe(summary, 'button')} (contraído)`);
        continue;
      }
      const role = roleOf(child);
      if (role && AX_SHOW.has(role)) {
        out.push(`${'  '.repeat(depth)}${describe(child, role)}`);
        if (role === 'table') axTable(child, depth + 1, out);
        else if (!AX_LEAF.has(role)) axWalk(child, depth + 1, out);
      } else {
        axWalk(child, depth, out);
      }
    }
  }
  function axSnapshot(mode) {
    const previous = root.dataset.mode;
    const radios = [$('#mode-human'), $('#mode-agent')];
    const checked = radios.map((r) => r.checked);
    root.dataset.mode = mode;
    radios.forEach((r) => { r.checked = r.value === mode; });
    const out = [];
    try { axWalk($('.page'), 0, out); } finally {
      root.dataset.mode = previous;
      radios.forEach((r, i) => { r.checked = checked[i]; });
    }
    return out;
  }
  function renderAx() {
    const picked = $('input[name="ax_view"]:checked');
    const view = picked && picked.value === 'human' ? 'human' : 'agent';
    const human = axSnapshot('human');
    const agent = axSnapshot('agent');
    $('#peek-ax').textContent = (view === 'human' ? human : agent).join('\n');
    $('#peek-ax-count').textContent = `Vista Persona: ${human.length} nodos. Vista Agente: ${agent.length} nodos. Se omite esta consola, y cada fila de tabla se resume en una línea.`;
  }
//@@ init
  function init() {
    const restored = load();
    const range = deliveryRange();
    const date = $('#p-date');
    date.dataset.min = range.min;
    date.dataset.max = range.max;
    $('#p-date-hint').textContent = `Formato AAAA-MM-DD, entre ${range.min} y ${range.max}.`;
    buildCards();
    ['#mode-switch', '#nav-console', '#pick-hint-cards', '#product-cards', '#pick-summary', '#agent-console'].forEach((sel) => { $(sel).hidden = false; });
    setMode(MODE_HASH[location.hash] || storedMode() || 'human', false);
    renderCart();
    renderOrder();
    refreshExpiry();
    const params = new URLSearchParams(location.search);
    const filterKeys = ['query', 'origin', 'variety', 'roast', 'max_price_usd', 'in_stock_only'];
    if (filterKeys.some((k) => params.has(k))) {
      const args = {};
      filterKeys.forEach((k) => { if (params.has(k)) args[k] = params.get(k); });
      report(searchProducts(args));
    } else if (restored) {
      const t = cartTotals();
      report(success('STATE_RESTORED', `Se recuperó el estado guardado en este navegador: ${bags(t.units)} en el carrito${state.order ? `, pedido ${state.order.order_id} ${ORDER_STATUS[state.order.status]}` : ''}.`), 'info');
    }
    setupConsole();
    root.dataset.ready = 'true';
    setupWebMCP();
  }
