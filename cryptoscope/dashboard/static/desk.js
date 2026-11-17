/* ZILLERS Action Desk — renders /api/desk (real Binance candles at any interval, rule-model votes, PM, paper book). */
(() => {
'use strict';
const $ = id => document.getElementById(id);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const COLORS = {trend:'#ffb547', momentum:'#a98bff', volume:'#4aa8ff', drawdown:'#ff6fb1', pm:'#e8f0f8'};
const GREEN = '#22e39b', RED = '#ff4d6a', MUTED = '#5f7186';
const pct = (v, d = 2) => v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(d)}%`;
const num = (v, d = 2) => v == null ? '—' : Number(v).toLocaleString('en-US', {minimumFractionDigits: d, maximumFractionDigits: d});
const px = v => money(v);
const cls = v => v == null ? '' : v >= 0 ? 'up' : 'dn';
const INTERVALS = {'1m': 60, '5m': 300, '15m': 900, '30m': 1800, '1h': 3600, '4h': 14400, '1d': 86400, '1w': 604800};
const intraday = () => (INTERVALS[state.interval] || 86400) < 86400;
// Short bar label (transcript/tables) and full label (headers); intraday shows the time too.
// Time zone: IST = UTC+05:30 (no daylight saving). All labels and chart times shift by this offset.
const tzOff = () => state.tz === 'IST' ? 19800 : 0;
const tzTag = () => state.tz === 'IST' ? 'IST' : 'UTC';
const iso = t => new Date((t + tzOff()) * 1000).toISOString();
const day = t => { const s = iso(t); return intraday() ? `${s.slice(5, 10)} ${s.slice(11, 16)}` : s.slice(5, 10); };
const date = t => { const s = iso(t); return intraday() ? `${s.slice(0, 10)} ${s.slice(11, 16)} ${tzTag()}` : s.slice(0, 10); };
const ct = t => Math.round(t + tzOff());  // chart time (the chart library labels everything as UTC)
// Currency: Binance quotes in USDT; INR = USDT price x live USD/INR rate from /api/fx/rate.
const fxk = () => state.ccy === 'INR' && state.fx ? state.fx.rate : 1;
const money = v => v == null ? '—' : (state.ccy === 'INR' && state.fx ? '₹' : '') +
  (v * fxk()).toLocaleString(state.ccy === 'INR' ? 'en-IN' : 'en-US', {minimumFractionDigits: 2, maximumFractionDigits: Math.abs(v * fxk()) >= 1000 ? 2 : Math.abs(v * fxk()) >= 1 ? 4 : 6});
const voteTxt = v => v > 0 ? '+1' : v < 0 ? '-1' : '0';
const voteCls = v => v > 0 ? 'p' : v < 0 ? 'n' : 'z';
const big = v => v == null ? '—' : v >= 1e9 ? (v / 1e9).toFixed(1) + 'B' : v >= 1e6 ? (v / 1e6).toFixed(1) + 'M' : v >= 1e3 ? (v / 1e3).toFixed(1) + 'K' : v.toFixed(0);

const store = (k, d) => { try { return localStorage.getItem(k) || d; } catch { return d; } };
const state = {symbol: store('desk.symbol', 'BTCUSDT'), interval: store('desk.interval', '1d'), tz: store('desk.tz', 'IST'),
  ccy: store('desk.ccy', 'INR'), fx: null, last: null, user: null, charts: null, timer: null};
if (!INTERVALS[state.interval]) state.interval = '1d';

// ------------------------------------------------------------------ charts
function makeCharts() {
  const LC = window.LightweightCharts;
  const base = {
    layout: {background: {color: 'transparent'}, textColor: MUTED, fontFamily: 'Consolas, monospace', fontSize: 10, attributionLogo: false},
    grid: {vertLines: {color: '#0f1822'}, horzLines: {color: '#0f1822'}},
    rightPriceScale: {borderColor: '#18222f'}, timeScale: {borderColor: '#18222f', timeVisible: false},
    crosshair: {mode: 0}, handleScroll: true, handleScale: true,
  };
  const mk = (el, extra = {}) => LC.createChart(el, {...base, ...extra, width: el.clientWidth, height: el.clientHeight});
  const price = mk($('lwc-chart'));
  const vol = mk($('vol-chart'), {timeScale: {visible: false}});
  const rsi = mk($('rsi-chart'), {timeScale: {visible: false}});
  const macd = mk($('macd-chart'), {timeScale: {visible: false}});
  const eq = mk($('eq-chart'));
  const s = {
    candles: price.addCandlestickSeries({upColor: GREEN, downColor: RED, borderVisible: false, wickUpColor: GREEN, wickDownColor: RED}),
    sma10: price.addLineSeries({color: COLORS.trend, lineWidth: 1.5, priceLineVisible: false, lastValueVisible: false}),
    sma30: price.addLineSeries({color: COLORS.momentum, lineWidth: 1.5, priceLineVisible: false, lastValueVisible: false}),
    vol: vol.addHistogramSeries({priceFormat: {type: 'volume'}, priceLineVisible: false, lastValueVisible: false}),
    rsi: rsi.addLineSeries({color: '#c9d4e0', lineWidth: 1, priceLineVisible: false}),
    macdHist: macd.addHistogramSeries({priceLineVisible: false, lastValueVisible: false}),
    macd: macd.addLineSeries({color: COLORS.volume, lineWidth: 1, priceLineVisible: false, lastValueVisible: false}),
    macdSig: macd.addLineSeries({color: COLORS.trend, lineWidth: 1, priceLineVisible: false, lastValueVisible: false}),
    agents: eq.addLineSeries({color: GREEN, lineWidth: 2, priceLineVisible: false}),
    bh: eq.addLineSeries({color: MUTED, lineWidth: 1, lineStyle: 2, priceLineVisible: false}),
  };
  s.rsi.createPriceLine({price: 70, color: '#3d1220', lineWidth: 1, lineStyle: 2, axisLabelVisible: false});
  s.rsi.createPriceLine({price: 30, color: '#0d3b2a', lineWidth: 1, lineStyle: 2, axisLabelVisible: false});
  const subs = [vol, rsi, macd];
  price.timeScale().subscribeVisibleLogicalRangeChange(r => { if (r) subs.forEach(c => c.timeScale().setVisibleLogicalRange(r)); });
  const all = [[price, 'lwc-chart'], [vol, 'vol-chart'], [rsi, 'rsi-chart'], [macd, 'macd-chart'], [eq, 'eq-chart']];
  new ResizeObserver(() => all.forEach(([c, id]) => c.applyOptions({width: $(id).clientWidth, height: $(id).clientHeight})))
    .observe(document.body);
  return {price, eq, s, peakLine: null};
}

function renderCharts(d) {
  if (!state.charts) state.charts = makeCharts();
  const {s, price, eq} = state.charts;
  price.applyOptions({timeScale: {timeVisible: intraday(), secondsVisible: false}});
  eq.applyOptions({timeScale: {timeVisible: intraday(), secondsVisible: false}});
  const c = d.chart, times = c.candles.map(k => ct(k.time)), k = fxk();
  const line = (arr, scale = k) => arr.map((v, i) => v == null ? {time: times[i]} : {time: times[i], value: v * scale});
  s.candles.setData(c.candles.map((b, i) => ({time: times[i], open: b.open * k, high: b.high * k, low: b.low * k, close: b.close * k})));
  s.sma10.setData(line(c.sma10));
  s.sma30.setData(line(c.sma30));
  s.vol.setData(c.candles.map((b, i) => ({time: times[i], value: b.volume, color: b.close >= b.open ? 'rgba(34,227,155,.55)' : 'rgba(255,77,106,.55)'})));
  s.rsi.setData(line(c.rsi14, 1));
  s.macd.setData(line(c.macd));
  s.macdSig.setData(line(c.macd_signal));
  s.macdHist.setData(c.macd_hist.map((v, i) => ({time: times[i], value: v * k, color: v >= 0 ? 'rgba(34,227,155,.5)' : 'rgba(255,77,106,.5)'})));
  // paper fills as markers
  const first = c.candles[0].time, markers = [];
  for (const t of d.trades) {
    if (t.entry_time >= first) markers.push({time: ct(t.entry_time), position: 'belowBar', color: GREEN, shape: 'arrowUp', text: `BUY ${px(t.entry)}`});
    if (t.exit_time >= first) markers.push({time: ct(t.exit_time), position: 'aboveBar', color: RED, shape: 'arrowDown', text: `SELL ${px(t.exit)}`});
  }
  if (d.position && d.position.entry_time >= first)
    markers.push({time: ct(d.position.entry_time), position: 'belowBar', color: GREEN, shape: 'arrowUp', text: `LONG 1.00x @ ${px(d.position.entry)}`});
  markers.sort((a, b) => a.time - b.time);
  s.candles.setMarkers(markers);
  // Peak line only when it sits inside the displayed window, so it never squashes the candles.
  if (state.charts.peakLine) { s.candles.removePriceLine(state.charts.peakLine); state.charts.peakLine = null; }
  const shownHigh = Math.max(...c.candles.slice(-140).map(k => k.high));
  if (d.ticker.peak <= shownHigh * 1.0001)
    state.charts.peakLine = s.candles.createPriceLine({price: d.ticker.peak * k, color: RED, lineWidth: 1, lineStyle: 2, axisLabelVisible: true,
      title: `PEAK · dd ${pct(d.ticker.dd)}`});
  const eqt = d.equity.times;
  s.agents.setData(d.equity.agents.map((v, i) => ({time: ct(eqt[i]), value: (v - 1) * 100})));
  s.bh.setData(d.equity.buy_hold.map((v, i) => ({time: ct(eqt[i]), value: (v - 1) * 100})));
  if (!state.charts.fitted || state.charts.fitted !== `${d.symbol}:${d.interval}:${state.tz}`) {
    // Show the last ~6 months; re-applied after layout settles so a late resize cannot skew it.
    const show = () => price.timeScale().setVisibleLogicalRange({from: Math.max(0, times.length - 180), to: times.length + 2});
    show(); requestAnimationFrame(show); setTimeout(show, 300);
    eq.timeScale().fitContent();
    state.charts.fitted = `${d.symbol}:${d.interval}:${state.tz}`;
  }
}

// ------------------------------------------------------------------ panels
function renderHeader(d) {
  const t = d.ticker;
  $('sym-title').textContent = d.symbol;
  $('sym-meta').textContent = `${d.interval.toUpperCase()} · BINANCE SPOT · ${state.ccy === 'INR' && state.fx ? 'INR' : 'USDT'} · ${tzTag()} · paper fills`;
  $('src').textContent = `${d.source || ''} · ${d.bar_forming ? 'bar forming' : 'bar closed'}`;
  $('ohlc').innerHTML = `<span>O <b>${px(t.open)}</b></span><span>H <b>${px(t.high)}</b></span><span>L <b>${px(t.low)}</b></span>` +
    `<span>C <b>${px(t.close)}</b></span><span class="${cls(t.chg)}">${t.abs_chg >= 0 ? '+' : ''}${px(t.abs_chg)} (${pct(t.chg)})</span>`;
  $('ind').innerHTML = `<span class="t10">SMA10 ${px(t.sma10)}</span><span class="t30">SMA30 ${px(t.sma30)}</span>` +
    `<span>BB %b ${t.bb_pct == null ? '—' : t.bb_pct.toFixed(2)}</span><span>r20 ${pct(t.r20, 1)}</span>` +
    `<span>VOL ${t.vol_ratio == null ? '—' : t.vol_ratio.toFixed(2) + 'x'}</span><span class="dn">PEAK ${px(t.peak)} dd ${pct(t.dd)}</span>`;
  $('vol-label').textContent = t.vol_ratio == null ? '' : `${t.vol_ratio.toFixed(2)}x avg20`;
  $('rsi-label').textContent = t.rsi14 == null ? '' : t.rsi14.toFixed(1);
  $('macd-label').innerHTML = `<span class="${cls(t.macd)}">${num(t.macd * fxk())}</span> <span>${num(t.macd_signal * fxk())}</span> <span class="${cls(t.macd_hist)}">${num(t.macd_hist * fxk())}</span>`;
  $('chips').innerHTML = d.scoreboard.map(m => `<span class="chip" style="color:${COLORS[m.key]}"><b>${esc(m.label)}</b> ` +
    `${m.hit_rate == null ? '—' : Math.round(m.hit_rate * 100) + '% hit'} · n${m.n}</span>`).join('') +
    `<span class="chip">${d.bars} bars · fee ${d.fee_bps}bp/side</span>`;
}

function renderMesh(d) {
  const dec = d.decision;
  $('mesh-source').textContent = `● Binance ${d.symbol} ${d.interval.toUpperCase()} bars`;
  $('mesh-ind').textContent = `● ${d.models.length} models · SMA RSI MACD BB ATR`;
  $('models').innerHTML = d.models.map(m => {
    const v = dec.votes[m.key];
    const label = v > 0 ? 'BULL' : v < 0 ? 'BEAR' : 'ABSTAIN';
    return `<div class="model" style="border-color:${COLORS[m.key]}55"><div class="name" style="color:${COLORS[m.key]}">${esc(m.label)}</div>` +
      `<div class="rule">${esc(m.rule)} <span class="muted">w${m.weight}</span></div><div class="note">${esc(dec.notes[m.key])}</div>` +
      `<span class="vote ${voteCls(v)}">${label} ${voteTxt(v)}</span></div>`;
  }).join('');
  $('bull-node').textContent = `BULL +${dec.bull.toFixed(2)}`;
  $('bear-node').textContent = `BEAR ${dec.bear ? '-' : ''}${dec.bear.toFixed(2)}`;
  const r = d.risk;
  $('risk-node').textContent = `● RISK  ATR14 ${px(r.atr14)} · vol20 ${pct(r.vol20, 1)} · VaR95 ${pct(r.var95_1d)}`;
  const markPos = Math.max(0, Math.min(100, (dec.score + d.thresholds.max_score) / (2 * d.thresholds.max_score) * 100));
  const lean = dec.bull_pct >= 50 ? `${Math.round(dec.bull_pct)}% <small>bull</small>` : `${Math.round(100 - dec.bull_pct)}% <small>bear</small>`;
  const pos = d.position;
  $('pm').className = `pm ${dec.action.toLowerCase()}`;
  $('pm').innerHTML = `<div class="pm-head"><span><span class="pm-tag">PM</span>DECISION</span><span>${date(d.decision_time)} close</span></div>` +
    `<div class="pm-main"><span class="pm-action ${dec.action}">${dec.action}</span>` +
    `<span><span class="pm-pct">${lean}</span><br><span class="muted">score ${dec.score >= 0 ? '+' : ''}${dec.score.toFixed(2)}</span></span>` +
    `<span class="scale"><span class="scale-labels"><span>SELL</span><span>HOLD</span><span>BUY</span></span>` +
    `<span class="scale-bar" style="display:block"><span class="scale-mark" style="left:${markPos}%"></span></span>` +
    `<span class="scale-labels"><span>${d.thresholds.sell.toFixed(2)}</span><span>0</span><span>+${d.thresholds.buy.toFixed(2)}</span></span></span></div>` +
    `<div class="pm-foot"><span class="exec">PAPER EXEC</span><span>${esc(dec.execution)}</span>` +
    (pos ? `<span>long 1.00x since ${day(pos.entry_time)}</span><span class="${cls(pos.upnl)}">uPnL ${pct(pos.upnl)}</span>` : '<span>flat</span>') +
    `<span>next-open fills · ${d.fee_bps}bp per side</span></div>`;
}

function renderAI(d) {
  const ai = d.ai;
  if (!ai) { $('ai').innerHTML = ''; return; }
  if (ai.halted) { $('ai').innerHTML = `<div class="halted-banner">■ KILL SWITCH ENGAGED — AI layer, LLMs and fleet stopped. ${esc(ai.policy)}</div>`; return; }
  const card = s => {
    let detail = '';
    if (s.status !== 'OK') detail = `unavailable (${esc(s.error || s.status)})`;
    else if (s.key === 'strategies') detail = s.signals.map(g => `<span class="sig">${esc(g.name.replace(/\s*\(.*\)$/, ''))}: <b class="act ${g.action === 'BUY' ? 'BUY' : g.action === 'SELL' ? 'SELL' : 'HOLD'}">${g.action === 'NONE' ? 'no setup' : esc(g.action)}</b></span>`).join('') +
      (s.not_run?.length ? `<span class="sig">${s.not_run.map(esc).join(' · ')}</span>` : '');
    else if (s.key === 'llm_panel') detail = esc(s.detail || '');
    else if (s.key === 'smc_laya') detail = `Tier 1 ${esc(s.tier1.setup)} · score ${s.tier1.score} · Laya ${esc(s.tier2.status || '')} ${s.tier2.agreed ? 'agreed' : ''}`;
    else if (s.key === 'committee') detail = `conviction ${(+s.conviction).toFixed(2)}${s.risk_veto ? ' · <span class="veto">risk veto</span>' : ''}` +
      (s.thx02 ? `<br>THX-02 <span class="act ${s.thx02.action === 'BUY' || s.thx02.action === 'LONG' ? 'BUY' : s.thx02.action === 'SELL' || s.thx02.action === 'SHORT' ? 'SELL' : 'HOLD'}">${esc(s.thx02.action)}</span> · regime ${esc(s.thx02.regime)}` : '') +
      `<br>${s.personas.map(p => `${esc(p.persona)} ${esc(p.action)}`).join(' · ')}`;
    return `<div class="ai-card"><div class="t"><span>${esc(s.label)}</span><span class="act ${s.action}">${s.action}</span></div>` +
      `<div class="d">${detail}${s.latency_ms != null ? ` · ${s.latency_ms}ms` : ''}</div></div>`;
  };
  const o = ai.ollama || {};
  const ollama = `<div class="ai-card"><div class="t"><span>Ollama ${esc(o.model || '')}</span><span class="${o.status === 'available' ? 'up' : 'dn'}">${esc(o.status || '?')}</span></div>` +
    `<div class="d">${esc(o.role || '')}${o.laya ? ` · Laya ${esc(o.laya.status)}` : ''}</div></div>`;
  const L = ai.llm;
  const llm = !L ? '' : `<div class="llm"><div class="ai-head"><span><b>LOCAL LLMs</b> <em>Ollama · one answer per model per closed bar · ${L.ready}/${L.total} ready</em></span>` +
    `<span>${L.panel_action ? `panel <span class="act ${L.panel_action}">${L.panel_action}</span>` : ''}</span></div>` +
    (L.models.length ? L.models.map(m => `<div class="llm-row"><span>${esc(m.model)}</span>` +
      (m.status === 'ready' ? `<span class="act ${m.action}">${m.action} ${Math.round((m.confidence || 0) * 100)}%</span><span class="r" title="${esc(m.reason)}">${esc(m.reason)} · ${(m.latency_ms / 1000).toFixed(1)}s</span>`
        : m.status === 'error' ? `<span class="dn">error</span><span class="r">${esc(m.error)}</span>`
        : `<span class="muted">${esc(m.status)}</span><span class="r">waiting for the local model…</span>`) + '</div>').join('')
      : `<div class="muted">${L.halted ? esc(L.note || 'paused') : 'No Ollama chat models found.'}</div>`) + '</div>';
  $('ai').innerHTML = `<div class="ai-head"><span><b>AI LAYER</b> <em>your systems on the last closed bar</em></span><span>veto-only</span></div>` +
    `<div class="ai-grid">${ai.systems.map(card).join('')}${ollama}</div>` + llm +
    `<div class="final"><span class="muted">rule PM</span><span class="act ${ai.rule_pm}">${ai.rule_pm}</span><span class="muted">→ final</span>` +
    `<span class="act ${ai.final_action}">${ai.final_action}</span>${ai.vetoes.map(v => `<span class="veto">⚠ ${esc(v)}</span>`).join('')}</div>`;
}

function renderVotes(d) {
  const rows = d.models.map(m => ({key: m.key, label: m.label, cells: d.votes.map(v => v[m.key])}));
  const cur = d.decision.votes;
  let html = rows.map(r => `<span class="lbl" style="color:${COLORS[r.key]}">${esc(r.label)}</span>` +
    `<span class="cells">${r.cells.map(v => `<i class="${voteCls(v)}"></i>`).join('')}</span>` +
    `<span class="cur vote ${voteCls(cur[r.key])}">${voteTxt(cur[r.key])}</span>`).join('');
  html += `<span class="lbl">PM bull %</span><span class="cells">${d.votes.map(v =>
    `<i style="background:${v.action === 'BUY' ? GREEN : v.action === 'SELL' ? RED : '#2a3647'};opacity:${(0.35 + Math.abs(v.bull_pct - 50) / 77).toFixed(2)}" title="${date(v.time)} ${v.action} ${v.bull_pct}%"></i>`).join('')}</span>` +
    `<span class="cur">${Math.round(d.decision.bull_pct)}%</span>`;
  if (d.votes.length) html += `<span></span><span class="axis"><span>${date(d.votes[0].time)}</span><span>${date(d.votes[d.votes.length - 1].time)}</span></span><span></span>`;
  $('heat').innerHTML = html;
}

function renderEquity(d) {
  const e = d.equity, beat = e.edge_pts >= 0;
  $('eq-meta').textContent = `maxDD ${pct(e.max_dd, 1)} · sharpe ${e.sharpe.toFixed(2)}`;
  $('eq-stats').innerHTML = `<div class="k">AGENTS —</div><div class="big ${cls(e.agents_return)}">${pct(e.agents_return, 1)}</div>` +
    `<div class="k">BUY &amp; HOLD ----</div><div class="${cls(e.buy_hold_return)}">${pct(e.buy_hold_return, 1)}</div>` +
    `<span class="beat ${beat ? '' : 'lose'}">${beat ? 'beat' : 'trail'} hold by ${Math.abs(e.edge_pts).toFixed(1)} pts</span>` +
    `<div class="k">since ${date(e.since)}</div>`;
}

function renderTranscript(d) {
  const rows = [`<div class="cmd">$ <b>desk</b> --symbol ${esc(d.symbol)} --data binance-1d --paper --fee ${d.fee_bps}bp</div>`,
    `<div class="cmd">$ indicators SMA RSI MACD BB ATR · models ${d.models.map(m => m.label.toLowerCase()).join(' ')}</div>`];
  for (const s of d.transcript) {
    const minis = d.models.map(m => `<i style="background:${s.votes[m.key] > 0 ? GREEN : s.votes[m.key] < 0 ? RED : '#1f2a38'}"></i>`).join('');
    rows.push(`<div class="trow"><span class="date">${day(s.time)}</span><span class="tag data">binance</span>` +
      `<span class="msg"><b>${esc(d.symbol)} ${px(s.close)}</b> <span class="${cls(s.chg)}">${pct(s.chg)}</span> · vol ${s.vol_ratio == null ? '—' : s.vol_ratio.toFixed(2) + 'x'} · V ${big(s.volume)}</span>` +
      `<span class="minis">${minis}</span></div>`);
    for (const m of d.models) {
      rows.push(`<div class="trow"><span></span><span class="tag ${m.key}">${esc(m.label)}</span><span class="msg">${esc(s.notes[m.key])}</span>` +
        `<span class="side">vote <span class="${voteCls(s.votes[m.key]) === 'p' ? 'up' : voteCls(s.votes[m.key]) === 'n' ? 'dn' : ''}">${voteTxt(s.votes[m.key])}</span></span></div>`);
    }
    const flip = s.prev_action && s.prev_action !== s.pm.action ? `${s.prev_action} → ` : '';
    rows.push(`<div class="trow"><span></span><span class="tag pm">PM</span><span class="msg"><b>${flip}${s.pm.action}</b> bull ${Math.round(s.pm.bull_pct)}% · score ${s.pm.score >= 0 ? '+' : ''}${s.pm.score.toFixed(2)}</span>` +
      `<span class="side"><span class="tag exec">paper</span> ${esc(s.execution)}${s.upnl == null ? '' : ` · uPnL <span class="${cls(s.upnl)}">${pct(s.upnl)}</span>`}</span></div>`);
  }
  $('transcript').innerHTML = rows.join('');
  $('transcript').scrollTop = $('transcript').scrollHeight;
  $('term-count').textContent = `${d.transcript.length} sessions · tail`;
}

function renderBook(d) {
  const p = d.position;
  $('book-meta').textContent = `paper exec · ${d.fee_bps}bp`;
  $('position').innerHTML = `<span class="sym">${esc(d.symbol)}</span>` +
    (p ? `<span class="badge">LONG 1.00x</span><span class="muted">entry ${px(p.entry)} · ${day(p.entry_time)} · ${p.sessions} sessions</span>`
       : '<span class="badge flat">FLAT</span>') +
    `<span class="mark"><span class="muted">MARK</span><br><b>${px(d.ticker.close)}</b> <span class="${cls(d.ticker.chg)}">${pct(d.ticker.chg)} today</span></span>` +
    `<span class="mark"><span class="muted">UNREALIZED</span><br><span class="upnl ${p ? cls(p.upnl) : ''}">${p ? pct(p.upnl) : '—'}</span></span>`;
  const rows = [...d.trades].reverse();
  if (p) rows.unshift({open: true, entry_time: p.entry_time, entry: p.entry, sessions: p.sessions, gross_pct: p.upnl, net_pct: null});
  const maxAbs = Math.max(0.01, ...rows.map(r => Math.abs(r.gross_pct || 0)));
  $('trades').innerHTML = '<tr><th>#</th><th>SIDE</th><th>ENTRY</th><th>EXIT</th><th class="num">SESS</th><th class="num">GROSS</th><th class="num">NET</th><th></th></tr>' +
    rows.map((t, i) => `<tr><td>${i + 1}</td><td class="up">LONG</td><td>${day(t.entry_time)} ${px(t.entry)}</td>` +
      `<td>${t.open ? '<span class="up">open</span>' : `${day(t.exit_time)} ${px(t.exit)}`}</td><td class="num">${t.sessions}</td>` +
      `<td class="num ${cls(t.gross_pct)}">${pct(t.gross_pct)}</td><td class="num ${cls(t.net_pct)}">${t.net_pct == null ? '—' : pct(t.net_pct)}</td>` +
      `<td><span class="bar" style="width:${Math.round(Math.abs(t.gross_pct || 0) / maxAbs * 50)}px;background:${(t.gross_pct || 0) >= 0 ? GREEN : RED}"></span></td></tr>`).join('');
  const b = d.book;
  $('book-stats').textContent = `closed ${b.closed} · won ${b.won}/${b.closed} · avg net ${b.avg_net == null ? '—' : pct(b.avg_net)} · exposure ${Math.round(b.exposure * 100)}% · fills ${b.fills}`;
  $('score').innerHTML = '<tr><th>MODEL</th><th>RULE</th><th class="num">INPUT</th><th>VOTE</th><th class="num">N</th><th class="num">HIT</th><th class="num">EDGE 5D</th></tr>' +
    d.scoreboard.map(m => {
      const input = m.input == null ? '—' : m.key === 'pm' ? (m.input >= 0 ? '+' : '') + m.input.toFixed(2) : m.key === 'volume' ? m.input.toFixed(2) + 'x' : pct(m.input);
      return `<tr><td style="color:${COLORS[m.key]};font-weight:700">${esc(m.label)}</td><td class="muted">${esc(m.rule)}</td><td class="num">${input}</td>` +
        `<td><span class="vote ${voteCls(m.vote)}">${voteTxt(m.vote)}</span></td><td class="num">${m.n}</td>` +
        `<td class="num">${m.hit_rate == null ? '—' : Math.round(m.hit_rate * 100) + '%'}</td>` +
        `<td class="num ${cls(m.edge)}">${m.edge == null ? '—' : pct(m.edge)}</td></tr>`;
    }).join('');
  const r = d.risk, e = d.equity;
  $('risk-line').innerHTML = `<b>RISK</b> ATR14 ${px(r.atr14)} · vol20 ${pct(r.vol20, 1)} · VaR95 1d ${pct(r.var95_1d)} · worst day ${pct(r.worst_day)}` +
    `<br><b style="color:var(--green)">PAPER</b> agents ${pct(e.agents_return, 1)} · hold ${pct(e.buy_hold_return, 1)} · maxDD ${pct(e.max_dd, 1)} · sharpe ${e.sharpe.toFixed(2)}`;
  $('foot-left').textContent = `${d.symbol} · ${d.bars} × ${d.interval} bars · decision on ${date(d.decision_time)} close · updated ${iso(d.generated_at).slice(0, 10)} ${iso(d.generated_at).slice(11, 19)} ${tzTag()}`;
}

// ------------------------------------------------------------------ data
async function load() {
  try {
    const res = await fetch(`/api/desk?symbol=${encodeURIComponent(state.symbol)}&interval=${state.interval}&fee_bps=10`);
    const d = await res.json();
    if (d.status === 'INSUFFICIENT_DATA') throw new Error(`${d.symbol} has only ${d.bars} ${state.interval} bars (needs ${d.required})`);
    if (d.status !== 'OK') throw new Error(d.error || d.status);
    $('live-dot').className = 'dot'; $('live-label').textContent = 'LIVE';
    state.last = d;
    renderAll(d);
  } catch (err) {
    $('live-dot').className = 'dot off'; $('live-label').textContent = 'OFFLINE';
    $('foot-left').textContent = `Desk data unavailable: ${err.message}. No cached or synthetic data is shown.`;
  }
}

async function loadGovernor() {
  try {
    const g = await (await fetch('/api/governor/status')).json();
    const halted = g.kill_switch_engaged || g.emergency_halted;
    $('gov').className = `gov ${halted ? 'halt' : 'ok'}`;
    $('gov').textContent = halted ? `HALTED · ${g.action || 'HALT'} · AI stopped` : `GOVERNOR OK · ${g.mode}`;
    $('kill').classList.toggle('engaged', !!halted);
    $('kill').textContent = halted ? '■ KILLED' : '■ KILL SWITCH';
  } catch { $('gov').textContent = 'GOVERNOR ?'; }
}

async function loadUser() {
  const res = await fetch('/api/auth/me');
  state.user = res.ok ? await res.json() : null;
  $('signin').textContent = state.user ? 'SIGN OUT' : 'SIGN IN';
}

async function post(path, body) {
  const headers = {'Content-Type': 'application/json'};
  if (state.user?.csrf_token) headers['X-CSRF-Token'] = state.user.csrf_token;
  const res = await fetch(path, {method: 'POST', headers, body: JSON.stringify(body || {})});
  const out = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(out.error || `Request failed (${res.status})`);
  return out;
}

// ------------------------------------------------------------------ wiring
$('symbol').value = state.symbol;
state.known = new Set();
$('symbol').addEventListener('change', e => {
  const v = e.target.value.trim().toUpperCase();
  if (!/^[A-Z0-9]{5,20}$/.test(v) || (state.known.size && !state.known.has(v))) { e.target.value = state.symbol; return; }
  state.symbol = v; localStorage.setItem('desk.symbol', v); if (state.charts) state.charts.fitted = null; load();
});
async function loadSymbols() {
  try {
    const r = await (await fetch('/api/desk/symbols')).json();
    state.known = new Set(r.symbols.map(x => x.symbol));
    $('symbol-list').innerHTML = r.symbols.map(x => `<option value="${esc(x.symbol)}">${esc(x.base)}</option>`).join('');
    $('sym-count').textContent = `${r.symbols.length} pairs`;
  } catch { $('sym-count').textContent = 'pairs unavailable'; }
}
async function loadFleet() {
  try {
    const f = await (await fetch('/api/fleet/status')).json();
    $('fleet-pill').textContent = f.running ? `AUTOTRADER ${f.mode} · ${f.symbols.length} pairs` : 'AUTOTRADER OFF';
    $('fleet-pill').className = `fleet-pill ${f.running ? 'run' : ''}`;
  } catch {}
}
$('signin').addEventListener('click', async () => {
  if (state.user) { try { await post('/api/auth/logout'); } catch {} return loadUser(); }
  $('login-err').textContent = ''; $('login').showModal();
});
$('login-cancel').addEventListener('click', () => $('login').close());
$('login-form').addEventListener('submit', async e => {
  e.preventDefault();
  try {
    await post('/api/auth/login', {email: $('email').value, password: $('password').value});
    $('password').value = ''; $('login').close(); await loadUser();
  } catch (err) { $('login-err').textContent = err.message; }
});

// ---- master kill switch (shared by desk and system pages) --------------------------
async function masterKill() {
  if (!state.user) { $('login-err').textContent = 'Sign in to use the kill switch.'; $('login').showModal(); return; }
  const flatten = confirm('MASTER KILL SWITCH\n\nThis immediately:\n' +
    ' • latches the emergency halt (no new entries anywhere)\n • stops the autotrader fleet\n' +
    ' • stops every AI system (SMC/Laya, committee, THX-02, strategies, all Ollama models) and unloads models from memory\n\n' +
    'OK = HALT + FLATTEN open positions (market close)\nCancel = choose plain HALT instead');
  const action = flatten ? 'HALT_FLATTEN' : (confirm('Engage plain HALT (keep open positions and their exchange stops)?') ? 'HALT' : null);
  if (!action) return;
  try {
    const r = await post('/api/governor/kill_switch', {action});
    const b = r.background || {};
    alert(`Kill switch engaged (${action}).\nFleet running: ${b.fleet?.running ? 'YES — check logs' : 'no'}\n` +
      `LLM jobs dropped: ${b.llm?.queued_jobs_dropped ?? 0}; models unloaded: ${(b.llm?.models_unloaded || []).join(', ') || 'none loaded'}\n` +
      'Resuming needs an admin with password re-entry.');
  } catch (err) { alert(err.message); }
  loadGovernor(); if (typeof load === 'function') load();
}
$('kill').addEventListener('click', masterKill);

function renderAll(d) { renderHeader(d); renderCharts(d); renderMesh(d); renderAI(d); renderVotes(d); renderEquity(d); renderTranscript(d); renderBook(d); }
function renderToggles() {
  document.querySelectorAll('#tz-seg button').forEach(b => b.classList.toggle('on', b.dataset.tz === state.tz));
  document.querySelectorAll('#ccy-seg button').forEach(b => {
    b.classList.toggle('on', b.dataset.ccy === (state.ccy === 'INR' && !state.fx ? 'USD' : state.ccy));
    if (b.dataset.ccy === 'INR') b.disabled = !state.fx;
  });
  $('fx').textContent = state.fx ? `₹${state.fx.rate.toFixed(2)}/USD${state.fx.status === 'stale' ? ' (stale)' : ''}` : 'INR rate unavailable';
}
async function loadFx() {
  try {
    const r = await (await fetch('/api/fx/rate')).json();
    state.fx = (r.status === 'available' || r.status === 'stale') && r.rate > 0 ? r : null;
  } catch { state.fx = null; }
  renderToggles(); if (state.last) renderAll(state.last);
}
$('tz-seg').addEventListener('click', e => { const v = e.target.dataset?.tz; if (!v || v === state.tz) return;
  state.tz = v; try { localStorage.setItem('desk.tz', v); } catch {} renderToggles(); if (state.last) renderAll(state.last); });
$('ccy-seg').addEventListener('click', e => { const v = e.target.dataset?.ccy; if (!v || e.target.disabled) return;
  state.ccy = v; try { localStorage.setItem('desk.ccy', v); } catch {} renderToggles(); if (state.last) renderAll(state.last); });
function renderIntervals() {
  $('intervals').innerHTML = Object.keys(INTERVALS).map(k => `<button type="button" data-iv="${k}" class="${k === state.interval ? 'on' : ''}">${k.toUpperCase()}</button>`).join('');
}
// Poll faster on short intervals (5-30 s); the server caches each symbol/interval accordingly.
function schedule() {
  clearInterval(state.timer);
  const ms = Math.min(30000, Math.max(5000, (INTERVALS[state.interval] * 1000) / 6));
  state.timer = setInterval(() => { load(); loadGovernor(); loadFleet(); }, ms);
}
$('intervals').addEventListener('click', e => {
  const iv = e.target.closest('button')?.dataset.iv;
  if (!iv || iv === state.interval) return;
  state.interval = iv; localStorage.setItem('desk.interval', iv);
  renderIntervals(); schedule(); load();
});
renderIntervals(); renderToggles();
loadFx(); setInterval(loadFx, 600000);
load(); loadGovernor(); loadUser(); loadSymbols(); loadFleet();
schedule();
})();
