/* ZILLERS Strategy Lab: compare 13 classic strategies on the same real candles. */
(() => {
'use strict';
const $ = id => document.getElementById(id);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct = (v, d = 1) => v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(d)}%`;
const cls = v => v == null ? '' : v >= 0 ? 'up' : 'dn';
const COLORS = ['#22e39b', '#4aa8ff', '#ffb547', '#a98bff', '#ff6fb1', '#38e1ff', '#ff4d6a', '#c9d4e0', '#9be36b', '#e36bd6', '#e3b36b', '#6be3d2', '#8f9cff'];
const state = {data: null, shown: new Set(), chart: null, series: {}};

function chart() {
  if (state.chart) return state.chart;
  const el = $('eq');
  state.chart = LightweightCharts.createChart(el, {width: el.clientWidth, height: el.clientHeight,
    layout: {background: {color: 'transparent'}, textColor: '#5f7186', fontFamily: 'Consolas, monospace', fontSize: 10, attributionLogo: false},
    grid: {vertLines: {color: '#0f1822'}, horzLines: {color: '#0f1822'}}, rightPriceScale: {borderColor: '#18222f'},
    timeScale: {borderColor: '#18222f'}});
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
  state.series.hold = line(d.buy_hold_curve, '#5f7186', 1, 2);
  d.results.forEach((r, i) => { if (state.shown.has(r.key) && r.curve) state.series[r.key] = line(r.curve, COLORS[i % COLORS.length], 2); });
  c.timeScale().fitContent();
}

function render() {
  const d = state.data;
  $('meta').textContent = `${d.symbol} · ${d.interval} · ${d.bars} bars (${new Date(d.from * 1000).toISOString().slice(0, 10)} → ${new Date(d.to * 1000).toISOString().slice(0, 10)}) · ${d.fee_bps} bp/side`;
  const ok = d.results.filter(r => !r.error);
  $('warn').textContent = ok.some(r => r.significant) ? '' : 'No strategy beats random timing on this history after correcting for testing 13 at once — treat the ranking as descriptive, not predictive.';
  $('tbl').innerHTML = '<tr><th></th><th>STRATEGY</th><th>FAMILY</th><th class="num">RETURN</th><th class="num">CAGR</th><th class="num">SHARPE</th><th class="num">SORTINO</th>' +
    '<th class="num">MAX DD</th><th class="num">CALMAR</th><th class="num">TRADES</th><th class="num">WIN</th><th class="num">PF</th><th class="num">EXPOSURE</th>' +
    '<th class="num">IN-SAMPLE</th><th class="num">OOS</th><th class="num">p</th></tr>' +
    `<tr><td><span class="sw" style="background:#5f7186"></span></td><td class="muted">Buy &amp; hold</td><td></td><td class="num ${cls(d.buy_hold.total_return)}">${pct(d.buy_hold.total_return)}</td>` +
    `<td colspan="3"></td><td class="num dn">${pct(d.buy_hold.max_drawdown)}</td><td colspan="8"></td></tr>` +
    d.results.map((r, i) => r.error ? `<tr><td></td><td>${esc(r.label)}</td><td colspan="14" class="dn">error ${esc(r.error)}</td></tr>` :
      `<tr data-k="${r.key}" class="${state.shown.has(r.key) ? 'sel' : ''}"><td><span class="sw" style="background:${state.shown.has(r.key) ? COLORS[i % COLORS.length] : 'transparent'};border:1px solid ${COLORS[i % COLORS.length]}"></span></td>` +
      `<td><b>${esc(r.label)}</b>${r.beats_hold ? ' <span class="up" title="beat buy & hold">▲</span>' : ''}</td><td class="muted">${esc(r.family)}</td>` +
      `<td class="num ${cls(r.total_return)}">${pct(r.total_return)}</td><td class="num ${cls(r.cagr)}">${pct(r.cagr)}</td>` +
      `<td class="num">${r.sharpe.toFixed(2)}</td><td class="num">${r.sortino == null ? '—' : r.sortino.toFixed(2)}</td><td class="num dn">${pct(r.max_drawdown)}</td>` +
      `<td class="num">${r.calmar == null ? '—' : r.calmar.toFixed(2)}</td><td class="num">${r.trades}</td><td class="num">${r.win_rate == null ? '—' : Math.round(r.win_rate * 100) + '%'}</td>` +
      `<td class="num">${r.profit_factor == null ? '—' : r.profit_factor.toFixed(2)}</td><td class="num">${Math.round(r.exposure * 100)}%</td>` +
      `<td class="num ${cls(r.in_sample_return)}">${pct(r.in_sample_return)}</td><td class="num ${cls(r.out_of_sample_return)}">${pct(r.out_of_sample_return)}</td>` +
      `<td class="num ${r.significant ? 'up' : ''}">${r.p_value == null ? '—' : r.p_value.toFixed(3) + (r.significant ? ' ✓' : '')}</td></tr>`).join('');
  $('method').textContent = d.method;
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
