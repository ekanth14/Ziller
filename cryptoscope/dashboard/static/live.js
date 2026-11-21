/* ZILLERS Live Tradebot view.
 * One tile per coin the fleet trades; the grid re-fits so every coin stays visible.
 * /api/live/stream pushes marks + per-coin P&L every second; candles come from /api/live/candles
 * (refreshed every 60 s) and the forming bar is updated from the live price in between.
 * Click a tile (or open /live#SYMBOL) for the full chart and that coin's P&L dashboard. */
(() => {
'use strict';
const $ = id => document.getElementById(id);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const store = (k, d) => { try { return localStorage.getItem(k) || d; } catch { return d; } };
const save = (k, v) => { try { localStorage.setItem(k, v); } catch {} };
const IV_SEC = {'1m': 60, '5m': 300, '15m': 900, '1h': 3600, '4h': 14400};
const S = {tz: store('desk.tz', 'IST'), ccy: store('desk.ccy', 'INR'), tileIv: store('live.iv', '15m'), fx: null,
           data: null, tiles: new Map(), open: null, big: null, bigIv: store('live.bigiv', '5m'), es: null, lastMsg: 0};

const inr = () => S.ccy === 'INR' && S.fx;
const k = () => inr() ? S.fx.rate : 1;
const money = (v, sign = false) => {
  if (v == null || !isFinite(v)) return '—';
  const x = v * k(), a = Math.abs(x);
  const s = a.toLocaleString(inr() ? 'en-IN' : 'en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  return (x < 0 ? '-' : sign && x > 0 ? '+' : '') + (inr() ? '₹' : '$') + s;
};
const px = v => v == null ? '—' : (inr() ? '₹' : '$') + (v * k()).toLocaleString(inr() ? 'en-IN' : 'en-US',
  {maximumFractionDigits: v * k() >= 100 ? 2 : v * k() >= 1 ? 4 : 8});
const raw = v => v == null ? '—' : (+v).toLocaleString('en-US', {maximumFractionDigits: v >= 100 ? 2 : v >= 1 ? 4 : 8});
const pct = (v, d = 2) => v == null || !isFinite(v) ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(d)}%`;
const cls = v => v == null || v === 0 ? '' : v > 0 ? 'up' : 'dn';
const off = () => S.tz === 'IST' ? 19800 : 0;
const when = t => t ? new Date((+t + off()) * 1000).toISOString().replace('T', ' ').slice(5, 16) + ' ' + S.tz : '—';
const dur = s => s == null ? '—' : s < 3600 ? `${Math.max(1, Math.round(s / 60))}m` : s < 86400 ? `${(s / 3600).toFixed(1)}h` : `${(s / 86400).toFixed(1)}d`;
const badge = st => st === 'IN POSITION' ? ['in', 'IN POSITION'] : st.startsWith('BLOCKED') ? ['blk', st] : ['', st];
const table = (id, head, rows, empty) => {
  $(id).innerHTML = rows.length ? `<tr>${head.map(h => `<th class="${h[1] || ''}">${h[0]}</th>`).join('')}</tr>` + rows.join('')
    : `<tr><td class="empty">${empty}</td></tr>`;
};

// ------------------------------------------------------------------ charts
const LC = window.LightweightCharts;
const chartBase = (small) => ({
  autoSize: true,
  layout: {background: {color: 'transparent'}, textColor: '#8b919e', fontFamily: 'Consolas, monospace', fontSize: small ? 9 : 11, attributionLogo: false},
  grid: {vertLines: {color: 'rgba(220,225,235,0.05)'}, horzLines: {color: 'rgba(220,225,235,0.05)'}},
  rightPriceScale: {borderColor: 'rgba(220,225,235,0.14)', scaleMargins: {top: 0.12, bottom: 0.08}},
  timeScale: {borderColor: 'rgba(220,225,235,0.14)', timeVisible: true, secondsVisible: false, rightOffset: small ? 2 : 6,
              tickMarkFormatter: t => new Date((t + off()) * 1000).toISOString().slice(11, 16)},
  crosshair: {mode: 0}, handleScroll: !small, handleScale: !small,
  localization: {timeFormatter: t => new Date((t + off()) * 1000).toISOString().slice(11, 16)},
});
const candleOpts = {upColor: '#2ee6a6', downColor: '#ff5d7d', borderVisible: false, wickUpColor: '#2ee6a6', wickDownColor: '#ff5d7d',
  priceFormat: {type: 'price', precision: 6, minMove: 0.000001}};
const fmtPrecision = p => p >= 100 ? 2 : p >= 1 ? 4 : p >= 0.01 ? 6 : 8;

function setLines(series, lines, pos) {
  for (const l of lines.splice(0)) series.removePriceLine(l);
  if (!pos) return;
  const add = (price, color, title, style) => price && lines.push(series.createPriceLine({price: +price, color, lineWidth: 1, lineStyle: style, axisLabelVisible: true, title}));
  add(pos.entry, '#d9dde6', 'entry', 2);
  add(pos.stop, '#ff5d7d', 'stop', 0);
  add(pos.target, '#2ee6a6', 'target', 0);
}

function liveBar(bars, series, ivSec, price) {
  if (!bars.length || price == null) return;
  const t = Math.floor(Date.now() / 1000 / ivSec) * ivSec;
  const last = bars[bars.length - 1];
  if (t === last.time) {
    last.close = price; last.high = Math.max(last.high, price); last.low = Math.min(last.low, price);
    series.update(last);
  } else if (t > last.time) {
    const b = {time: t, open: last.close, high: Math.max(last.close, price), low: Math.min(last.close, price), close: price};
    bars.push(b); series.update(b);
  }
}

async function loadCandles(sym, iv, limit) {
  const r = await fetch(`/api/live/candles?symbol=${encodeURIComponent(sym)}&interval=${iv}&limit=${limit}`);
  if (!r.ok) throw new Error(r.status);
  const d = await r.json();
  d.bars = d.candles.map(c => ({time: Math.floor(c.open_time), open: c.open, high: c.high, low: c.low, close: c.close}));
  return d;
}

function markers(fills, ivSec) {
  return (fills || []).slice().sort((a, b) => a.timestamp - b.timestamp).map(f => ({
    time: Math.floor(f.timestamp / ivSec) * ivSec,
    position: f.side === 'BUY' ? 'belowBar' : 'aboveBar', shape: f.side === 'BUY' ? 'arrowUp' : 'arrowDown',
    color: f.side === 'BUY' ? '#2ee6a6' : '#ff5d7d', text: f.side === 'BUY' ? 'B' : 'S'}));
}

// ------------------------------------------------------------------ tiles
function makeTile(sym) {
  const el = document.createElement('article');
  el.className = 'tile'; el.tabIndex = 0; el.dataset.sym = sym;
  el.setAttribute('aria-label', `${sym} chart, open details`);
  el.innerHTML = `<div class="th"><span class="sym">${esc(sym.replace(/USDT$/, ''))}<span class="muted" style="font-size:10px">/USDT</span></span>
    <span class="px">—</span><span class="chg">—</span><span class="badge">…</span></div>
    <div class="tc"></div>
    <div class="tf"><div><span>INVESTED</span><b class="inv">—</b></div><div><span>VALUE</span><b class="val">—</b></div>
    <div><span>P&amp;L</span><b class="pl">—</b></div><div><span>P&amp;L %</span><b class="plp">—</b></div></div>`;
  const box = el.querySelector('.tc');
  const chart = LC.createChart(box, chartBase(true));
  const series = chart.addCandlestickSeries(candleOpts);
  // Tiles resize whenever the grid re-fits; keep every bar in view at the new size.
  new ResizeObserver(() => requestAnimationFrame(() => chart.timeScale().fitContent())).observe(box);
  const t = {sym, el, chart, series, bars: [], lines: [], iv: null, fetched: 0, pos: null, busy: false};
  el.addEventListener('click', () => openCoin(sym));
  el.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openCoin(sym); } });
  S.tiles.set(sym, t);
  return t;
}

async function refreshTileCandles(t, force = false) {
  if (t.busy || (!force && t.iv === S.tileIv && Date.now() - t.fetched < 60000)) return;
  t.busy = true;
  try {
    const d = await loadCandles(t.sym, S.tileIv, 120);
    t.bars = d.bars; t.iv = S.tileIv; t.fetched = Date.now();
    const p = fmtPrecision(d.bars.length ? d.bars[d.bars.length - 1].close : 1);
    t.series.applyOptions({priceFormat: {type: 'price', precision: p, minMove: Math.pow(10, -p)}});
    t.series.setData(t.bars);
    t.series.setMarkers(markers(d.fills, IV_SEC[t.iv]).filter(m => m.time >= (t.bars[0] || {}).time));
    t.chart.timeScale().fitContent();
  } catch (e) { /* keep the last good chart; the next refresh retries */ }
  t.busy = false;
}

function renderTile(t, c) {
  const q = s => t.el.querySelector(s);
  q('.px').textContent = px(c.price);
  q('.chg').textContent = pct(c.change_24h); q('.chg').className = 'chg ' + cls(c.change_24h);
  const [bc, bt] = badge(c.status); q('.badge').className = 'badge ' + bc; q('.badge').textContent = bt; q('.badge').title = c.status;
  const pos = c.position || null;
  t.el.classList.toggle('pos', !!pos); t.el.classList.toggle('loss', !!pos && (c.upnl || 0) < 0);
  q('.inv').textContent = pos ? money(c.invested) : '—';
  q('.val').textContent = pos ? money(c.value) : '—';
  q('.pl').textContent = pos ? money(c.upnl, true) : (c.realized ? money(c.realized, true) : '—');
  q('.pl').className = 'pl ' + cls(pos ? c.upnl : c.realized);
  q('.plp').textContent = pos ? pct(c.upnl_pct) : (c.closed_trades ? `${c.closed_trades} closed` : 'no trade');
  q('.plp').className = 'plp ' + (pos ? cls(c.upnl_pct) : '');
  const key = pos ? `${pos.entry}|${pos.stop}|${pos.target}` : '';
  if (key !== t.pos) { setLines(t.series, t.lines, pos); t.pos = key; }
  liveBar(t.bars, t.series, IV_SEC[t.iv || S.tileIv], c.price);
}

// Choose columns + tile height so every coin fits in the viewport (scroll only past a minimum size).
function layout() {
  const grid = $('grid'), n = S.tiles.size;
  if (!n) return;
  const W = grid.clientWidth, gap = 10, top = grid.getBoundingClientRect().top + window.scrollY;
  const H = Math.max(260, window.innerHeight - top - 54);
  if (W < 640) { grid.style.setProperty('--cols', 1); grid.style.setProperty('--tile-h', Math.max(290, Math.min(360, H / Math.min(n, 2))) + 'px'); return; }
  let best = {score: -1, cols: 1, h: 220};
  for (let cols = 1; cols <= Math.min(n, 6); cols++) {
    const rows = Math.ceil(n / cols), w = (W - gap * (cols - 1)) / cols, hFit = (H - gap * (rows - 1)) / rows;
    const h = Math.min(hFit, w * 0.82);                       // keep tiles roughly landscape
    const score = Math.min(w, h * 1.5) * (hFit >= 190 ? 1 : 0.5);   // prefer layouts that fit without scrolling
    if (score > best.score) best = {score, cols, h};
  }
  grid.style.setProperty('--cols', best.cols);
  grid.style.setProperty('--tile-h', Math.round(Math.max(190, Math.min(560, best.h))) + 'px');
}

function renderGrid() {
  const d = S.data, grid = $('grid');
  const coins = d && d.coins || [];
  if (!coins.length) {
    for (const t of S.tiles.values()) t.chart.remove();
    S.tiles.clear();
    grid.style.setProperty('--cols', 1);
    grid.innerHTML = `<div class="empty-live panel"><b>${d && d.running ? 'The fleet has no coins right now' : 'The trading fleet is not running'}</b>` +
      `Release the kill switch if needed, then press START ALL on the <a href="/system">System</a> page. Coins appear here as soon as the bot trades them.</div>`;
    return;
  }
  const want = coins.map(c => c.symbol);
  for (const [sym, t] of S.tiles) if (!want.includes(sym)) { t.chart.remove(); t.el.remove(); S.tiles.delete(sym); }
  if (grid.querySelector('.empty-live')) grid.innerHTML = '';
  let changed = false;
  want.forEach((sym, i) => {
    const t = S.tiles.get(sym) || (changed = true, makeTile(sym));
    if (grid.children[i] !== t.el) { grid.insertBefore(t.el, grid.children[i] || null); changed = true; }
  });
  if (changed) layout();
  coins.forEach(c => { const t = S.tiles.get(c.symbol); renderTile(t, c); refreshTileCandles(t); });
}

function renderTotals() {
  const d = S.data; if (!d) return;
  const t = d.totals;
  $('totals').innerHTML = [
    ['NET P&L', money(t.net, true), 'open + closed trades', cls(t.net), 'hero'],
    ['UNREALISED', money(t.upnl, true), 'after fees + est. exit fee', cls(t.upnl)],
    ['REALISED', money(t.realized, true), 'closed trades, these coins', cls(t.realized)],
    ['INVESTED', money(t.invested), `${t.in_position} open position${t.in_position === 1 ? '' : 's'}`, ''],
    ['CURRENT VALUE', money(t.value), 'marked to live price', ''],
    ['COINS', `${t.coins}`, d.running ? `${d.mode} fleet · since ${when(d.started_at)}` : 'fleet off', ''],
  ].map(([k1, v, s, c, x]) => `<div class="kpi ${x || ''}"><div class="k">${k1}</div><div class="v ${c}">${v}</div><div class="s">${s}</div></div>`).join('');
  $('fleet').textContent = d.running ? `FLEET ${d.mode}` : 'FLEET OFF';
  $('fleet').className = 'gov ' + (d.running ? 'ok' : '');
  $('updated').textContent = 'updated ' + when(d.generated_at).slice(6);
}

// ------------------------------------------------------------------ expanded coin view
function openCoin(sym) {
  S.open = sym;
  if (location.hash !== '#' + sym) history.replaceState(null, '', '#' + sym);
  $('ov').classList.add('open'); document.body.style.overflow = 'hidden';
  if (!S.big) {
    const chart = LC.createChart($('big'), chartBase(false));
    S.big = {chart, series: chart.addCandlestickSeries(candleOpts), bars: [], lines: [], iv: null, sym: null, fetched: 0, pos: null};
    new ResizeObserver(() => requestAnimationFrame(() => chart.timeScale().fitContent())).observe($('big'));
  }
  S.big.sym = null;
  loadBig(true);
  renderOpen();
  $('ov-close').focus();
}

function closeCoin() {
  S.open = null; $('ov').classList.remove('open'); document.body.style.overflow = '';
  history.replaceState(null, '', location.pathname);
  const t = S.tiles.get(document.activeElement?.dataset?.sym); if (t) t.el.focus();
}

async function loadBig(force) {
  const b = S.big, sym = S.open;
  if (!b || !sym) return;
  if (!force && b.sym === sym && b.iv === S.bigIv && Date.now() - b.fetched < 30000) return;
  try {
    const d = await loadCandles(sym, S.bigIv, 400);
    if (S.open !== sym) return;
    b.bars = d.bars; b.iv = S.bigIv; b.sym = sym; b.fetched = Date.now(); b.detail = d;
    const p = fmtPrecision(d.bars.length ? d.bars[d.bars.length - 1].close : 1);
    b.series.applyOptions({priceFormat: {type: 'price', precision: p, minMove: Math.pow(10, -p)}});
    b.series.setData(b.bars);
    b.series.setMarkers(markers(d.fills, IV_SEC[b.iv]).filter(m => m.time >= (b.bars[0] || {}).time));
    b.pos = null; b.chart.timeScale().fitContent();
    renderOpen();
  } catch (e) { $('ov-pos').innerHTML = '<div class="wide note">Chart data unavailable right now; retrying.</div>'; }
  document.querySelectorAll('#ov-iv button').forEach(x => x.classList.toggle('on', x.dataset.iv === S.bigIv));
}

function renderOpen() {
  if (!S.open || !S.data) return;
  const c = S.data.coins.find(x => x.symbol === S.open);
  if (!c) { $('ov-badge').textContent = 'NO LONGER TRADED'; return; }
  const p = c.position, L = c.last || {}, b = S.big;
  $('ov-sym').textContent = c.symbol; $('ov-px').textContent = px(c.price);
  $('ov-chg').innerHTML = `<span class="${cls(c.change_24h)}">${pct(c.change_24h)} 24h</span>`;
  const [bc, bt] = badge(c.status); $('ov-badge').className = 'badge ' + bc; $('ov-badge').textContent = bt;
  if (b && b.sym === c.symbol) {
    const key = p ? `${p.entry}|${p.stop}|${p.target}` : '';
    if (key !== b.pos) { setLines(b.series, b.lines, p); b.pos = key; }
    liveBar(b.bars, b.series, IV_SEC[b.iv], c.price);
  }
  const kv = rows => rows.map(([k1, v, c2, wide]) => `<div class="${wide ? 'wide' : ''}"><span>${k1}</span><b class="${c2 || ''}">${v}</b></div>`).join('');
  if (p) {
    const span = p.target - p.stop, at = span > 0 && c.price ? Math.max(0, Math.min(1, (c.price - p.stop) / span)) : 0.5;
    $('ov-pos').innerHTML = kv([
      ['INVESTED', money(c.invested)], ['CURRENT VALUE', money(c.value)],
      ['UNREALISED P&L', money(c.upnl, true), cls(c.upnl)], ['RETURN', pct(c.upnl_pct), cls(c.upnl_pct)],
      ['QUANTITY', `${(+p.quantity).toLocaleString('en-US', {maximumFractionDigits: 6})}`], ['ENTRY (avg)', `${raw(p.entry)} USDT`],
      ['STOP', `${raw(p.stop)} · ${pct(c.to_stop)}`, 'dn'], ['TARGET', `${raw(p.target)} · ${pct(c.to_target)}`, 'up'],
      ['FEES PAID', money(p.entry_fees)], ['HELD FOR', dur(c.held_s)],
      ['OPENED', when(p.opened_at)], ['MODE · FILLS', `${p.mode} · ${p.fills}`],
    ]) + `<div class="wide"><span>PRICE BETWEEN STOP AND TARGET</span><div class="bar"><div class="stop"></div><div class="tgt"></div><i style="left:calc(${(at * 100).toFixed(1)}% - 1px)"></i></div></div>`;
  } else {
    $('ov-pos').innerHTML = `<div class="wide note">No open position. The bot is ${esc(c.status.toLowerCase())}; P&amp;L shows here when it buys.</div>`;
  }
  const winRate = c.closed_trades ? Math.round(c.wins / c.closed_trades * 100) + '%' : '—';
  $('ov-hist').innerHTML = kv([
    ['REALISED P&L', money(c.realized, true), cls(c.realized)], ['CLOSED TRADES', `${c.closed_trades}`],
    ['WIN RATE', winRate], ['SIGNALS · DEBATES', `${(c.counts || {}).signals ?? '—'} · ${(c.counts || {}).debates ?? '—'}`],
  ]);
  const deb = L.debate, meta = L.meta, risk = L.risk, sig = L.signal;
  $('ov-dec').innerHTML = kv([
    ['LAST SIGNAL', sig ? `${esc(sig.direction)} · ${esc(sig.strategy_id)} · ${when(sig.timestamp)}` : '—', '', true],
    ['LLM DEBATE', deb ? `${esc(deb.verdict)} · conviction ${(+deb.conviction_score).toFixed(1)}` : '—', deb && deb.verdict === 'APPROVE' ? 'up' : 'dn'],
    ['THX-02 · LAYA', meta ? `${meta.thx02_p == null ? '—' : Math.round(meta.thx02_p * 100) + '%'} · ${meta.laya_p == null ? '—' : Math.round(meta.laya_p * 100) + '%'}${meta.enforced ? '' : ' (shadow)'}` : '—'],
    ['RISK', risk ? `${esc(risk.decision)}${risk.position_size_usd ? ' · ' + money(+risk.position_size_usd) : ''}` : '—', risk && risk.decision === 'APPROVED' ? 'up' : 'dn'],
    ['WHY', risk && risk.veto_reasons ? esc(String(risk.veto_reasons).split('; ').slice(0, 2).join(' · ')) : '—', '', true],
  ]);
  const det = b && b.detail;
  if (det && b.sym === c.symbol) {
    table('ov-fills', [['TIME'], ['SIDE'], ['PRICE', 'num'], ['QTY', 'num'], ['VALUE', 'num'], ['FEE', 'num']],
      det.fills.slice(0, 30).map(f => `<tr><td class="muted">${when(f.timestamp)}</td><td class="${f.side === 'BUY' ? 'up' : 'dn'}">${esc(f.side)}</td>` +
        `<td class="num">${raw(f.fill_price)}</td><td class="num">${(+f.quantity).toPrecision(6)}</td><td class="num">${money(f.fill_price * f.quantity)}</td><td class="num">${money(f.fee_usd)}</td></tr>`),
      'No fills for this coin yet.');
  }
  const closed = (c.detail && c.detail.closed) || (det && det.closed) || [];
  if (closed.length || (det && b.sym === c.symbol)) {
    table('ov-closed', [['CLOSED'], ['ENTRY', 'num'], ['EXIT', 'num'], ['P&L', 'num'], ['%', 'num'], ['HELD', 'num'], ['WHY']],
      closed.slice(0, 20).map(x => `<tr><td class="muted">${when(x.timestamp)}</td><td class="num">${raw(x.entry_price)}</td><td class="num">${raw(x.exit_price)}</td>` +
        `<td class="num ${cls(x.pnl_usd)}">${money(x.pnl_usd, true)}</td><td class="num ${cls(x.pnl_pct)}">${pct(x.pnl_pct / 100)}</td><td class="num">${dur(x.duration_seconds)}</td><td>${esc(x.exit_reason)}</td></tr>`),
      'No closed trades for this coin yet.');
  }
}

// ------------------------------------------------------------------ stream
function connect() {
  if (S.es) S.es.close();
  const url = '/api/live/stream' + (S.open ? '?symbol=' + encodeURIComponent(S.open) : '');
  S.es = new EventSource(url);
  S.es.onmessage = ev => {
    try { S.data = JSON.parse(ev.data); } catch { return; }
    S.lastMsg = Date.now();
    $('live-dot').className = 'dot'; $('live-label').textContent = 'LIVE';
    renderTotals(); renderGrid(); renderOpen();
  };
  S.es.onerror = () => { $('live-dot').className = 'dot off'; $('live-label').textContent = 'RECONNECTING'; };
}
// Stream stalled (laptop sleep, proxy): reconnect.
setInterval(() => { if (S.lastMsg && Date.now() - S.lastMsg > 8000) connect(); }, 4000);
setInterval(() => { for (const t of S.tiles.values()) refreshTileCandles(t); loadBig(false); }, 15000);

// ------------------------------------------------------------------ controls
function toggles() {
  document.querySelectorAll('#tz-seg button').forEach(b => b.classList.toggle('on', b.dataset.tz === S.tz));
  document.querySelectorAll('#iv-seg button').forEach(b => b.classList.toggle('on', b.dataset.iv === S.tileIv));
  document.querySelectorAll('#ccy-seg button').forEach(b => {
    b.classList.toggle('on', b.dataset.ccy === (inr() ? 'INR' : 'USD'));
    if (b.dataset.ccy === 'INR') b.disabled = !S.fx;
  });
  $('fx').textContent = S.fx ? `₹${S.fx.rate.toFixed(2)}/USD` : '';
}
const rerender = () => { toggles(); renderTotals(); if (S.data) S.data.coins.forEach(c => { const t = S.tiles.get(c.symbol); if (t) renderTile(t, c); }); renderOpen(); };
document.querySelectorAll('#tz-seg button').forEach(b => b.addEventListener('click', () => { S.tz = b.dataset.tz; save('desk.tz', S.tz); rerender(); }));
document.querySelectorAll('#ccy-seg button').forEach(b => b.addEventListener('click', () => { S.ccy = b.dataset.ccy; save('desk.ccy', S.ccy); rerender(); }));
document.querySelectorAll('#iv-seg button').forEach(b => b.addEventListener('click', () => {
  S.tileIv = b.dataset.iv; save('live.iv', S.tileIv); toggles();
  for (const t of S.tiles.values()) refreshTileCandles(t, true);
}));
document.querySelectorAll('#ov-iv button').forEach(b => b.addEventListener('click', () => { S.bigIv = b.dataset.iv; save('live.bigiv', S.bigIv); loadBig(true); }));
$('ov-close').addEventListener('click', closeCoin);
$('ov').addEventListener('click', e => { if (e.target === $('ov')) closeCoin(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape' && S.open) closeCoin(); });
window.addEventListener('resize', layout);
window.addEventListener('hashchange', () => { const s = location.hash.slice(1).toUpperCase(); if (s && s !== S.open) openCoin(s); });

fetch('/api/fx/rate').then(r => r.json()).then(r => { S.fx = (r.status === 'available' || r.status === 'stale') && r.rate > 0 ? r : null; rerender(); }).catch(toggles);
toggles();
connect();
const h = location.hash.slice(1).toUpperCase(); if (h) openCoin(h);
})();
