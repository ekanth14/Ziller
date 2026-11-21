/* ZILLERS Strategy Lab: compare every candidate strategy on the same real candles, with the promotion gate. */
(() => {
'use strict';
const $ = id => document.getElementById(id);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct = (v, d = 1) => v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(d)}%`;
const cls = v => v == null ? '' : v >= 0 ? 'up' : 'dn';
const COLORS = ['#22e39b', '#4aa8ff', '#ffb547', '#a98bff', '#ff6fb1', '#38e1ff', '#ff4d6a', '#d4d8e0', '#9be36b', '#e36bd6', '#e3b36b', '#6be3d2', '#8f9cff'];
const state = {data: null, shown: new Set(), chart: null, series: {}};

function chart() {
  if (state.chart) return state.chart;
  const el = $('eq');
  state.chart = LightweightCharts.createChart(el, {width: el.clientWidth, height: el.clientHeight,
    layout: {background: {color: 'transparent'}, textColor: '#8b919e', fontFamily: 'Consolas, monospace', fontSize: 10, attributionLogo: false},
    grid: {vertLines: {color: 'rgba(220,225,235,0.06)'}, horzLines: {color: 'rgba(220,225,235,0.06)'}}, rightPriceScale: {borderColor: 'rgba(220,225,235,0.16)'},
    timeScale: {borderColor: 'rgba(220,225,235,0.16)'}});
  new ResizeObserver(() => state.chart.applyOptions({width: el.clientWidth})).observe(el);
  return state.chart;
}

function draw() {
  const d = state.data, c = chart();
  Object.values(state.series).forEach(s => c.removeSeries(s));
  state.series = {};
  const line = (vals, color, width, style) => {
    const s = c.addLineSeries({color, lineWidth: width, lineStyle: style || 0, priceLineVisible: false, lastValueVisible: false});
    s.setData(vals.map((v, i) => ({time: d.times[i], value: (v - 1) * 100})));
    return s;
  };
  state.series.hold = line(d.buy_hold_curve, '#8b919e', 1, 2);
  d.results.forEach((r, i) => { if (state.shown.has(r.key) && r.curve) state.series[r.key] = line(r.curve, COLORS[i % COLORS.length], 2); });
  c.timeScale().fitContent();
}

function gateCells(gt) {
  if (!gt) return '<td colspan="4" class="muted">—</td>';
  const verdict = gt.passed ? '<span class="gate-ok">PROMOTED</span>'
    : `<span class="gate-no" title="${esc((gt.reasons || []).join(' · '))}">✗ ${esc((gt.reasons || ['fail'])[0])}${(gt.reasons || []).length > 1 ? ` +${gt.reasons.length - 1}` : ''}</span>`;
  return `<td class="num">${gt.oos_trades ?? '—'}</td><td class="num ${cls(gt.expectancy)}">${pct(gt.expectancy, 2)}</td>` +
    `<td class="num">${gt.dsr_p == null ? '—' : gt.dsr_p.toFixed(3)}</td><td>${verdict}</td>`;
}

function renderCatalog(cat) {
  if (!cat || cat.status !== 'OK') {
    $('cat-meta').textContent = cat ? cat.status.toLowerCase() : '';
    $('catalog').textContent = cat && cat.error ? `Catalog unavailable: ${cat.error}` : '';
    return;
  }
  $('cat-meta').textContent = `${cat.library} · ${cat.indicators} indicators → ${cat.features} no-lookahead features`;
  const per = Object.entries(cat.per_category).map(([k, v]) => `${esc(k)} ${v}`).join(' · ');
  const excl = Object.entries(cat.excluded).map(([k, v]) => `<li><b>${esc(k)}</b> — ${esc(v)}</li>`).join('');
  const feats = Object.entries(cat.latest).map(([k, v]) => `<div>${esc(k)} <span style="color:var(--txt)">${v == null ? '—' : Number(v).toPrecision(5)}</span></div>`).join('');
  $('catalog').innerHTML = `<p style="margin:0">${per}</p><p style="margin:6px 0 0">Each value at bar t uses bars ≤ t only (tested by truncating later bars). Rule candidates built from the catalog appear in the table; the rest are features.</p>` +
    `<details><summary>Excluded (${Object.keys(cat.excluded).length})</summary><ul style="margin:4px 0;padding-left:16px">${excl}</ul></details>` +
    `<details><summary>Latest values (${cat.features})</summary><div class="feat">${feats}</div></details>`;
}

function render() {
  const d = state.data;
  $('meta').textContent = `${d.symbol} · ${d.interval} · ${d.bars} bars (${new Date(d.from * 1000).toISOString().slice(0, 10)} → ${new Date(d.to * 1000).toISOString().slice(0, 10)}) · ${d.fee_bps} bp/side`;
  const ok = d.results.filter(r => !r.error);
  const g = d.gate || {}, passed = ok.filter(r => r.gate && r.gate.passed).length;
  const gateLine = g.status === 'OK'
    ? `Gate: PBO ${g.pbo == null ? 'n/a' : g.pbo.toFixed(2)} over ${g.pbo_splits} CSCV splits · ${g.n_candidates} candidates · ${g.horizon_bars}-bar time limit · ${g.fee_bps} bp/side · ${passed} promoted.`
    : `Gate unavailable (${esc(g.error || 'not run')}) — nothing is promoted.`;
  $('warn').textContent = (ok.some(r => r.significant) ? '' : `No strategy beats random timing on this history after correcting for testing ${ok.length} at once — treat the ranking as descriptive, not predictive. `) + gateLine;
  $('tbl').innerHTML = '<tr><th></th><th>STRATEGY</th><th>FAMILY</th><th class="num">RETURN</th><th class="num">CAGR</th><th class="num">SHARPE</th><th class="num">SORTINO</th>' +
    '<th class="num">MAX DD</th><th class="num">CALMAR</th><th class="num">TRADES</th><th class="num">WIN</th><th class="num">PF</th><th class="num">EXPOSURE</th>' +
    '<th class="num">IN-SAMPLE</th><th class="num">OOS</th><th class="num">p</th>' +
    '<th class="num" title="Bracket trades whose signal and exit fall inside one CPCV group">OOS TR</th><th class="num" title="Mean net return per bracket trade after fees">EXPECT</th>' +
    '<th class="num" title="1 - Deflated Sharpe probability (trials = candidates)">DSR p</th>' +
    '<th class="num" title="Probabilistic Sharpe ratio: chance the true Sharpe is above 0, corrected for skew and fat tails (Bailey &amp; Lopez de Prado)">PSR</th>' +
    '<th class="num" title="Van Tharp System Quality Number: sqrt(min(N,100)) x mean / sd of trade returns">SQN</th><th title="≥100 OOS trades, DSR p < 0.05, PBO < 0.3, expectancy > 0">GATE</th></tr>' +
    `<tr><td><span class="sw" style="background:#8b919e"></span></td><td class="muted">Buy &amp; hold</td><td></td><td class="num ${cls(d.buy_hold.total_return)}">${pct(d.buy_hold.total_return)}</td>` +
    `<td colspan="3"></td><td class="num dn">${pct(d.buy_hold.max_drawdown)}</td><td colspan="14"></td></tr>` +
    d.results.map((r, i) => r.error ? `<tr><td></td><td>${esc(r.label)}</td><td colspan="20" class="dn">error ${esc(r.error)}</td></tr>` :
      `<tr data-k="${r.key}" class="${state.shown.has(r.key) ? 'sel' : ''}"><td><span class="sw" style="background:${state.shown.has(r.key) ? COLORS[i % COLORS.length] : 'transparent'};border:1px solid ${COLORS[i % COLORS.length]}"></span></td>` +
      `<td><b>${esc(r.label)}</b>${r.beats_hold ? ' <span class="up" title="beat buy & hold">▲</span>' : ''}</td><td class="muted">${esc(r.family)}</td>` +
      `<td class="num ${cls(r.total_return)}">${pct(r.total_return)}</td><td class="num ${cls(r.cagr)}">${pct(r.cagr)}</td>` +
      `<td class="num">${r.sharpe.toFixed(2)}</td><td class="num">${r.sortino == null ? '—' : r.sortino.toFixed(2)}</td><td class="num dn">${pct(r.max_drawdown)}</td>` +
      `<td class="num">${r.calmar == null ? '—' : r.calmar.toFixed(2)}</td><td class="num">${r.trades}</td><td class="num">${r.win_rate == null ? '—' : Math.round(r.win_rate * 100) + '%'}</td>` +
      `<td class="num">${r.profit_factor == null ? '—' : r.profit_factor.toFixed(2)}</td><td class="num">${Math.round(r.exposure * 100)}%</td>` +
      `<td class="num ${cls(r.in_sample_return)}">${pct(r.in_sample_return)}</td><td class="num ${cls(r.out_of_sample_return)}">${pct(r.out_of_sample_return)}</td>` +
      `<td class="num ${r.significant ? 'up' : ''}">${r.p_value == null ? '—' : r.p_value.toFixed(3) + (r.significant ? ' ✓' : '')}</td>` + `<td class="num ${r.psr != null && r.psr >= 0.95 ? 'up' : ''}">${r.psr == null ? '—' : Math.round(r.psr * 100) + '%'}</td>` +
      `<td class="num">${r.sqn == null ? '—' : r.sqn.toFixed(2)}</td>` + gateCells(r.gate) + '</tr>').join('');
  $('method').textContent = d.method;
  renderCatalog(d.catalog);
  draw();
}

async function run() {
  $('run').disabled = true; $('meta').textContent = 'running…';
  try {
    const sym = $('symbol').value.trim().toUpperCase();
    const r = await fetch(`/api/lab?symbol=${encodeURIComponent(sym)}&interval=${$('interval').value}&fee_bps=${$('fee').value}`);
    const d = await r.json();
    if (d.status === 'INSUFFICIENT_DATA') throw new Error(`only ${d.bars} bars (needs ${d.required})`);
    if (d.status !== 'OK') throw new Error(d.error || d.status);
    state.data = d;
    if (!state.shown.size) d.results.filter(x => !x.error).slice(0, 3).forEach(x => state.shown.add(x.key));
    render();
    $('live-dot').className = 'dot'; $('live-label').textContent = 'LIVE';
  } catch (e) { $('meta').textContent = `failed: ${e.message}`; $('live-dot').className = 'dot off'; }
  $('run').disabled = false;
}

$('run').addEventListener('click', run);
$('tbl').addEventListener('click', e => {
  const k = e.target.closest('tr')?.dataset.k; if (!k) return;
  state.shown.has(k) ? state.shown.delete(k) : state.shown.add(k); render();
});
const q = new URLSearchParams(location.search).get('symbol');
if (q) $('symbol').value = q.toUpperCase();
fetch('/api/desk/symbols').then(r => r.json()).then(r => { $('syms').innerHTML = r.symbols.map(s => `<option value="${esc(s.symbol)}">`).join(''); }).catch(() => {});
run();
})();

/* Cross-sectional momentum rotation panel (research only; the fleet never trades it). */
(() => {
'use strict';
const $ = id => document.getElementById(id);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct = (v, d = 1) => v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(d)}%`;
const cls = v => v == null ? '' : v >= 0 ? 'up' : 'dn';
const num = (v, d = 2) => v == null ? '—' : (+v).toFixed(d);
let chart = null;

function draw(d) {
  const el = $('rot-eq'); el.style.display = '';
  const LC = window.LightweightCharts;
  if (!chart) {
    chart = LC.createChart(el, {autoSize: true, layout: {background: {color: 'transparent'}, textColor: '#8b919e', fontSize: 10, attributionLogo: false},
      grid: {vertLines: {color: 'rgba(220,225,235,0.05)'}, horzLines: {color: 'rgba(220,225,235,0.05)'}},
      rightPriceScale: {mode: 1, borderColor: 'rgba(220,225,235,0.14)'}, timeScale: {borderColor: 'rgba(220,225,235,0.14)'}});
    chart.s = [['#2ee6a6', 'Rotation'], ['#8b919e', 'Equal-weight basket'], ['#ffc56b', 'BTC']]
      .map(([color, title]) => chart.addLineSeries({color, lineWidth: 2, title, priceLineVisible: false}));
  }
  [d.curve, d.benchmark, d.btc].forEach((pts, i) => chart.s[i].setData(pts.map(p => ({time: Math.floor(p.time), value: p.equity}))));
  if (d.oos_from) chart.s[0].setMarkers([{time: Math.floor(d.oos_from), position: 'aboveBar', color: '#6aa8ff', shape: 'arrowDown', text: 'OOS starts'}]);
  chart.timeScale().fitContent();
}

async function run() {
  $('rot-run').disabled = true;
  $('rot-kpis').textContent = 'Downloading daily history and running…';
  try {
    const r = await fetch(`/api/lab/rotation?k=${$('rot-k').value}&n=${$('rot-n').value}`);
    const d = await r.json();
    if (d.status !== 'OK') throw new Error(d.error || d.status);
    const f = d.full, o = d.oos, m = d.oos_metrics || {}, c = d.checks;
    const tick = ok => ok ? '<span class="up">✓</span>' : '<span class="dn">✗</span>';
    $('rot-kpis').innerHTML =
      `<b>${d.passes ? '<span class="up">PASSES</span>' : '<span class="dn">DOES NOT PASS</span>'}</b> the out-of-sample check · ` +
      `full period <b class="${cls(f.total_return)}">${pct(f.total_return)}</b> (Sharpe ${num(f.sharpe)}, max DD ${pct(f.max_drawdown)}, ${d.entries} entries) · ` +
      `out-of-sample <b class="${cls(o.total_return)}">${pct(o.total_return)}</b> (Sharpe ${num(o.sharpe)}, max DD ${pct(o.max_drawdown)}, PSR ${m.psr == null ? '—' : Math.round(m.psr * 100) + '%'}, SQN ${num(m.sqn)}) · ` +
      `basket ${pct(d.benchmark[d.benchmark.length - 1].equity - 1)} · BTC ${pct(d.btc[d.btc.length - 1].equity - 1)}<br>` +
      `${tick(c.oos_entries_100)} ≥ 100 out-of-sample entries (${d.oos_entries}) · ${tick(c.psr_95)} PSR ≥ 95% · ${tick(c.positive_oos_after_fees)} positive out-of-sample return after fees` +
      (d.last_holdings ? ` · latest holdings: ${d.last_holdings.btc_gate ? esc(d.last_holdings.holdings.join(', ') || 'none qualified') : 'cash (BTC below its 50-day average)'}` : '');
    $('rot-notes').textContent = (d.caveats || []).join(' ');
    $('rot-meta').textContent = `hold ${d.params.k} of top ${d.params.top_liquid} · weekly · ${d.params.fee_bps} bp/side · BTC > SMA${d.params.gate_sma} gate`;
    draw(d);
  } catch (e) {
    $('rot-kpis').innerHTML = `<span class="dn">Rotation unavailable: ${esc(e.message)}</span>`;
  }
  $('rot-run').disabled = false;
}
$('rot-run').addEventListener('click', run);
})();
