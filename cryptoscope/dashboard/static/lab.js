/* ZILLERS Strategy Lab: compare every candidate strategy on the same real candles, with the promotion gate. */
(() => {
'use strict';
const $ = id => document.getElementById(id);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct = (v, d = 1) => v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(d)}%`;
const cls = v => v == null ? '' : v >= 0 ? 'up' : 'dn';
const COLORS = ['#22e39b', '#4aa8ff', '#ffb547', '#a98bff', '#ff6fb1', '#38e1ff', '#ff4d6a', '#d4d8e0', '#9be36b', '#e36bd6', '#e3b36b', '#6be3d2', '#8f9cff'];
const state = {data: null, shown: new Set(), chart: null, series: {}};
window.__lab = state;   // read by the report panel below

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
  document.dispatchEvent(new CustomEvent('lab:rendered'));
}

async function run() {
  $('run').disabled = true; $('meta').textContent = 'running…';
  try {
    const sym = $('symbol').value.trim().toUpperCase();
    const r = await fetch(`/api/lab?symbol=${encodeURIComponent(sym)}&interval=${$('interval').value}&fee_bps=${$('fee').value}&slippage_bps=${$('slip').value}`);
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
    const r = await fetch(`/api/lab/rotation?k=${$('rot-k').value}&n=${$('rot-n').value}&weighting=${$('rot-w').value}`);
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
    $('rot-meta').textContent = `hold ${d.params.k} of top ${d.params.top_liquid} · ${d.params.weighting.replace('_', ' ')} · weekly · ${d.params.fee_bps} bp/side · BTC > SMA${d.params.gate_sma} gate`;
    draw(d);
  } catch (e) {
    $('rot-kpis').innerHTML = `<span class="dn">Rotation unavailable: ${esc(e.message)}</span>`;
  }
  $('rot-run').disabled = false;
}
$('rot-run').addEventListener('click', run);
})();

/* Meta-labeling panel: ML filter evaluation on one strategy (research; nothing trades from it). */
(() => {
'use strict';
const $ = id => document.getElementById(id);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct = v => v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(3)}%`;
const cls = v => v == null ? '' : v >= 0 ? 'up' : 'dn';
// Fill the strategy list from the Lab table once it renders (rows carry data-k; label in the 2nd cell).
new MutationObserver(() => {
  const rows = [...document.querySelectorAll('#tbl tr[data-k]')];
  if (!rows.length || $('ml-strat').options.length === rows.length) return;
  const cur = $('ml-strat').value;
  $('ml-strat').innerHTML = rows.map(r => `<option value="${esc(r.dataset.k)}">${esc(r.children[1].textContent.replace('▲', '').trim())}</option>`).join('');
  if (cur) $('ml-strat').value = cur;
}).observe($('tbl'), {childList: true, subtree: true});

$('ml-run').addEventListener('click', async () => {
  $('ml-run').disabled = true; $('ml-out').textContent = 'Training walk-forward models…';
  try {
    const q = new URLSearchParams({symbol: $('symbol').value.trim().toUpperCase(), interval: $('interval').value, strategy: $('ml-strat').value});
    const d = await fetch('/api/lab/metalabel?' + q).then(r => r.json());
    if (d.status === 'INSUFFICIENT_DATA') {
      $('ml-out').innerHTML = `<span class="dn">Not enough trades:</span> ${esc(d.label)} produced ${d.trades} bracket trades on these candles; at least ${d.needed} are needed to train and test. Try a shorter interval or a more active strategy.`;
    } else if (d.status !== 'OK') {
      throw new Error(d.error || d.status);
    } else {
      const a = d.oos_all, t = d.oos_taken, s = d.oos_skipped;
      $('ml-out').innerHTML = `<b>${esc(d.label)}</b> · model ${esc(d.model)} · out-of-sample AUC ${d.auc == null ? '—' : d.auc.toFixed(3)} (0.5 = coin flip)<br>` +
        `All entries: ${a.trades} trades, win ${a.win_rate == null ? '—' : Math.round(a.win_rate * 100) + '%'}, avg <b class="${cls(a.expectancy)}">${pct(a.expectancy)}</b> · ` +
        `Model takes: ${t.trades}, avg <b class="${cls(t.expectancy)}">${pct(t.expectancy)}</b> · Model skips: ${s.trades}, avg <span class="${cls(s.expectancy)}">${pct(s.expectancy)}</span><br>` +
        `<b class="${d.verdict.startsWith('Filter improves') ? 'up' : 'dn'}">${esc(d.verdict)}</b> <span class="muted">Bracket: target ${pct(d.bracket.target)}, stop ${pct(d.bracket.stop)}, ${d.bracket.horizon_bars} bars.</span>`;
    }
  } catch (e) { $('ml-out').innerHTML = `<span class="dn">Unavailable: ${esc(e.message)}</span>`; }
  $('ml-run').disabled = false;
});
})();

/* Strategy report (QuantConnect LEAN-style): statistics, monthly heatmap, worst drawdowns, rolling Sharpe,
   returns-per-trade histogram for one strategy of the current Lab run. */
(() => {
'use strict';
const $ = id => document.getElementById(id);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct = (v, d = 1) => v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(d)}%`;
const num = (v, d = 2) => v == null || !isFinite(v) ? '—' : (+v).toFixed(d);
const cls = v => v == null ? '' : v >= 0 ? 'up' : 'dn';
const day = t => t == null ? 'not yet' : new Date(t * 1000).toISOString().slice(0, 10);
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
let rs = null, current = null;

function heat(v) {                       // red..green, saturating at +/-10% like LEAN's report
  if (v == null) return 'transparent';
  const a = Math.min(1, Math.abs(v) / 0.10) * 0.55 + 0.08;
  return v >= 0 ? `rgba(46,230,166,${a})` : `rgba(255,93,125,${a})`;
}

function render() {
  const d = window.__lab && window.__lab.data;
  if (!d) return;
  const ok = d.results.filter(r => !r.error);
  const sel = $('rep-strat');
  if (sel.options.length !== ok.length) {
    sel.innerHTML = ok.map(r => `<option value="${esc(r.key)}">${esc(r.label)}</option>`).join('');
  }
  if (!current || !ok.some(r => r.key === current)) current = ok.length ? ok[0].key : null;
  sel.value = current;
  const r = ok.find(x => x.key === current);
  if (!r) return;
  const kv = (k, v, c = '') => `<div><span>${k}</span><b class="${c}">${v}</b></div>`;
  $('rep-stats').innerHTML = [
    kv('RETURN', pct(r.total_return), cls(r.total_return)), kv('SHARPE', num(r.sharpe)), kv('PSR', r.psr == null ? '—' : Math.round(r.psr * 100) + '%'),
    kv('ALPHA (ann.)', pct(r.alpha), cls(r.alpha)), kv('BETA', num(r.beta)), kv('TREYNOR', num(r.treynor)),
    kv('INFO RATIO', num(r.information_ratio)), kv('TRACKING ERR', r.tracking_error == null ? '—' : (r.tracking_error * 100).toFixed(1) + '%'),
    kv('VaR 95 / 99', `${pct(r.var95 == null ? null : -r.var95, 2)} / ${pct(r.var99 == null ? null : -r.var99, 2)}`, 'dn'),
    kv('MAX DD', pct(r.max_drawdown), 'dn'), kv('ULCER', num(r.ulcer_index)), kv('OMEGA', num(r.omega)),
    kv('TRADES', r.trades), kv('WIN RATE', r.win_rate == null ? '—' : Math.round(r.win_rate * 100) + '%'),
    kv('P/L RATIO', num(r.profit_loss_ratio)), kv('LEAN EXPECTANCY', num(r.lean_expectancy), cls(r.lean_expectancy)),
    kv('AVG MAE / MFE', `${pct(r.avg_mae, 2)} / ${pct(r.avg_mfe, 2)}`), kv('STREAK W / L', `${r.max_consecutive_wins ?? '—'} / ${r.max_consecutive_losses ?? '—'}`),
    kv('BEST / WORST', `${pct(r.largest_win)} / ${pct(r.largest_loss)}`), kv('SQN', num(r.sqn)),
  ].join('');
  const rep = r.report || {};
  // monthly heatmap: years x months
  const m = rep.monthly || [];
  const years = [...new Set(m.map(x => x.year))].sort();
  $('rep-monthly').innerHTML = years.length ? `<tr><th></th>${MONTHS.map(x => `<th>${x}</th>`).join('')}<th>YEAR</th></tr>` +
    years.map(y => {
      const row = MONTHS.map((_, i) => m.find(x => x.year === y && x.month === i + 1));
      const yr = row.filter(Boolean).reduce((a, x) => a * (1 + x.ret), 1) - 1;
      return `<tr><th>${y}</th>${row.map(x => `<td style="background:${heat(x && x.ret)}">${x ? (x.ret * 100).toFixed(1) : ''}</td>`).join('')}` +
        `<td class="${cls(yr)}"><b>${pct(yr)}</b></td></tr>`;
    }).join('') : '<tr><td class="empty">No data.</td></tr>';
  // worst drawdowns
  const dds = rep.drawdowns || [];
  $('rep-dd').innerHTML = dds.length ? '<tr><th>#</th><th class="num">DEPTH</th><th>PEAK</th><th>TROUGH</th><th>RECOVERED</th><th class="num">BARS</th></tr>' +
    dds.map((x, i) => `<tr><td>${i + 1}</td><td class="num dn">${pct(x.depth)}</td><td>${day(x.start)}</td><td>${day(x.trough)}</td>` +
      `<td class="${x.recovered ? '' : 'dn'}">${x.recovered ? day(x.end) : 'not yet'}</td><td class="num">${x.bars}</td></tr>`).join('')
    : '<tr><td class="empty">No drawdowns.</td></tr>';
  // rolling Sharpe
  const pts = (rep.rolling_sharpe || []).map(p => ({time: Math.floor(p.time), value: p.value}));
  $('rep-win').textContent = rep.rolling_window ? `· ${rep.rolling_window}-bar window` : '';
  if (!rs) {
    rs = LightweightCharts.createChart($('rep-rs'), {autoSize: true, layout: {background: {color: 'transparent'}, textColor: '#8b919e', fontSize: 10, attributionLogo: false},
      grid: {vertLines: {color: 'rgba(220,225,235,0.05)'}, horzLines: {color: 'rgba(220,225,235,0.05)'}},
      rightPriceScale: {borderColor: 'rgba(220,225,235,0.14)'}, timeScale: {borderColor: 'rgba(220,225,235,0.14)'}});
    rs.line = rs.addBaselineSeries({baseValue: {type: 'price', price: 0}, topLineColor: '#2ee6a6', bottomLineColor: '#ff5d7d',
      topFillColor1: 'rgba(46,230,166,.25)', topFillColor2: 'rgba(46,230,166,0)', bottomFillColor1: 'rgba(255,93,125,0)', bottomFillColor2: 'rgba(255,93,125,.25)', priceLineVisible: false});
  }
  rs.line.setData(pts); rs.timeScale().fitContent();
  // returns-per-trade histogram (20 bins), median marked in the title
  const tr = rep.trade_returns || [];
  if (!tr.length) { $('rep-hist').innerHTML = '<span class="muted" style="margin:auto">No closed trades.</span>'; return; }
  const lo = Math.min(...tr), hi = Math.max(...tr), bins = 20, w = (hi - lo) / bins || 1;
  const counts = Array(bins).fill(0);
  tr.forEach(x => counts[Math.min(bins - 1, Math.floor((x - lo) / w))]++);
  const top = Math.max(...counts), med = [...tr].sort((a, b) => a - b)[Math.floor(tr.length / 2)];
  $('rep-hist').innerHTML = counts.map((n, i) => {
    const mid = lo + (i + 0.5) * w;
    return `<i title="${pct(lo + i * w)} to ${pct(lo + (i + 1) * w)}: ${n} trades" style="height:${(n / top * 100).toFixed(1)}%;background:${mid >= 0 ? 'var(--green)' : 'var(--red)'}"></i>`;
  }).join('');
  $('rep-hist').title = `${tr.length} trades · median ${pct(med, 2)}`;
}

document.addEventListener('lab:rendered', render);
$('rep-strat').addEventListener('change', e => { current = e.target.value; render(); });
$('tbl').addEventListener('click', e => { const row = e.target.closest('tr[data-k]'); if (row) { current = row.dataset.k; render(); } });
})();
