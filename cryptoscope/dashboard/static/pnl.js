/* ZILLERS P&L dashboard: renders /api/pnl (fleet realised + unrealised, paper bots, funnel). */
(() => {
'use strict';
const $ = id => document.getElementById(id);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const store = (k, d) => { try { return localStorage.getItem(k) || d; } catch { return d; } };
const save = (k, v) => { try { localStorage.setItem(k, v); } catch {} };
const state = {tz: store('desk.tz', 'IST'), ccy: store('desk.ccy', 'INR'), fx: null, data: null, charts: null};

const inr = () => state.ccy === 'INR' && state.fx;
const k = () => inr() ? state.fx.rate : 1;
const money = (v, sign = false) => {
  if (v == null) return '—';
  const x = v * k(), a = Math.abs(x);
  const s = a.toLocaleString(inr() ? 'en-IN' : 'en-US', {minimumFractionDigits: 2, maximumFractionDigits: a >= 1 ? 2 : 6});
  return (x < 0 ? '-' : sign && x > 0 ? '+' : '') + (inr() ? '₹' : '$') + s;
};
const price = v => v == null ? '—' : (inr() ? '₹' : '$') + (v * k()).toLocaleString(inr() ? 'en-IN' : 'en-US', {maximumFractionDigits: v * k() >= 1 ? 4 : 8});
const pct = (v, d = 2) => v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(d)}%`;
const cls = v => v == null || v === 0 ? '' : v > 0 ? 'up' : 'dn';
const off = () => state.tz === 'IST' ? 19800 : 0;
const when = t => t ? new Date((t + off()) * 1000).toISOString().replace('T', ' ').slice(0, 16) + ' ' + state.tz : '—';
const dur = s => s == null ? '—' : s < 3600 ? `${Math.round(s / 60)}m` : s < 86400 ? `${(s / 3600).toFixed(1)}h` : `${(s / 86400).toFixed(1)}d`;
const table = (id, head, rows, empty) => {
  $(id).innerHTML = rows.length ? `<tr>${head.map(h => `<th class="${h[1] || ''}">${h[0]}</th>`).join('')}</tr>` + rows.join('')
    : `<tr><td class="empty">${empty}</td></tr>`;
};

function charts() {
  if (state.charts) return state.charts;
  const LC = window.LightweightCharts;
  const base = {layout: {background: {color: 'transparent'}, textColor: '#8b919e', fontFamily: 'Consolas, monospace', fontSize: 10, attributionLogo: false},
    grid: {vertLines: {color: 'rgba(220,225,235,0.06)'}, horzLines: {color: 'rgba(220,225,235,0.06)'}},
    rightPriceScale: {borderColor: 'rgba(220,225,235,0.16)'}, timeScale: {borderColor: 'rgba(220,225,235,0.16)', timeVisible: true}};
  const mk = id => { const el = $(id), c = LC.createChart(el, {...base, width: el.clientWidth, height: el.clientHeight});
    new ResizeObserver(() => c.applyOptions({width: el.clientWidth})).observe(el); return c; };
  const eq = mk('eq'), daily = mk('daily');
  state.charts = {
    eq: eq.addAreaSeries({lineColor: '#e4e7ee', topColor: 'rgba(228,231,238,.28)', bottomColor: 'rgba(228,231,238,0)', lineWidth: 2, priceLineVisible: false}),
    start: null, eqChart: eq,
    daily: daily.addHistogramSeries({priceLineVisible: false}), dailyChart: daily,
  };
  return state.charts;
}

function render() {
  const d = state.data; if (!d) return;
  const t = d.totals, s = d.stats;
  $('kpis').innerHTML = [
    ['NET P&L', money(t.net, true), 'fleet + paper bots', cls(t.net), 'hero'],
    ['FLEET EQUITY', money(t.fleet_equity), `${pct(t.fleet_return)} on ${money(d.start_nav)} start`, cls(t.fleet_return)],
    ['REALISED', money(t.fleet_realized, true), `${s.trades} closed trades`, cls(t.fleet_realized)],
    ['UNREALISED', money(t.fleet_unrealized, true), `${d.open_positions.length} open · exposure ${money(t.exposure)}`, cls(t.fleet_unrealized)],
    ['PAPER BOTS', money(t.paper_bots, true), t.bots_invested ? `${pct(t.bots_return)} on ${money(t.bots_invested)}` : 'no bots', cls(t.paper_bots)],
    ['FEES PAID', money(t.fees), 'fleet fills', ''],
    ['WIN RATE', s.win_rate == null ? '—' : Math.round(s.win_rate * 100) + '%', `${s.wins} W · ${s.losses} L · break-even ${s.breakeven_win_rate == null ? '—' : Math.round(s.breakeven_win_rate * 100) + '%'}`,
     s.win_rate != null && s.breakeven_win_rate != null ? (s.win_rate >= s.breakeven_win_rate ? 'up' : 'dn') : ''],
    ['MAX DRAWDOWN', pct(s.max_drawdown), 'realised equity curve', s.max_drawdown < 0 ? 'dn' : ''],
  ].map(([k1, v, sub, c, extra]) => `<div class="kpi ${extra || ''}"><div class="k">${k1}</div><div class="v ${c}">${v}</div><div class="s">${sub}</div></div>`).join('');

  $('periods').innerHTML = [['TODAY', 'today'], ['7 DAYS', '7d'], ['30 DAYS', '30d'], ['ALL TIME', 'all']].map(([l, key]) =>
    `<div><span>${l}</span><b class="${cls(d.periods[key].pnl)}">${money(d.periods[key].pnl, true)}</b> <em>${d.periods[key].trades} trades</em></div>`).join('');

  $('stats').innerHTML = [
    ['Profit factor', s.profit_factor == null ? (s.wins && !s.losses ? 'no losses' : '—') : s.profit_factor.toFixed(2)],
    ['Expectancy / trade', money(s.expectancy, true)], ['Avg win', money(s.avg_win, true)], ['Avg loss', money(s.avg_loss, true)],
    ['Best trade', money(s.best, true)], ['Worst trade', money(s.worst, true)], ['Avg hold', dur(s.avg_hold_s)],
    ['Streak', s.streak ? `${s.streak.count} ${s.streak.kind}${s.streak.count > 1 ? (s.streak.kind === 'loss' ? 'es' : 's') : ''}` : '—'],
  ].map(([a, b]) => `<div><span>${a}</span><b>${b}</b></div>`).join('');

  const c = charts();
  const ct = x => Math.round(x + off());
  $('eq-empty').hidden = d.equity_curve.length > 0;
  $('eq').style.display = d.equity_curve.length ? '' : 'none';
  const pts = d.equity_curve.length ? [{time: ct(d.equity_curve[0].time) - 60, value: d.start_nav * k()},
    ...d.equity_curve.map(p => ({time: ct(p.time), value: p.equity * k()}))] : [];
  const uniq = []; pts.forEach(p => { if (uniq.length && uniq[uniq.length - 1].time >= p.time) p.time = uniq[uniq.length - 1].time + 1; uniq.push(p); });
  c.eq.setData(uniq);
  c.eqChart.timeScale().fitContent();
  $('daily-empty').hidden = d.daily.length > 0;
  $('daily').style.display = d.daily.length ? '' : 'none';
  c.daily.setData(d.daily.map(p => ({time: ct(p.time), value: p.pnl * k(), color: p.pnl >= 0 ? '#2ee6a6' : '#ff5d7d'})));
  c.dailyChart.timeScale().fitContent();

  table('open', [['COIN'], ['MODE'], ['QTY', 'num'], ['ENTRY', 'num'], ['MARK', 'num'], ['VALUE', 'num'], ['P&L', 'num'], ['P&L %', 'num'], ['TO STOP', 'num'], ['TO TARGET', 'num'], ['OPENED']],
    d.open_positions.map(p => `<tr><td><a href="/?symbol=${esc(p.symbol)}"><b>${esc(p.symbol)}</b></a></td><td class="muted">${esc(p.mode || '')}</td>` +
      `<td class="num">${(+p.quantity).toPrecision(6)}</td><td class="num">${price(p.entry_price)}</td><td class="num">${price(p.mark)}</td>` +
      `<td class="num">${money(p.value)}</td><td class="num ${cls(p.upnl)}">${money(p.upnl, true)}</td><td class="num ${cls(p.upnl_pct)}">${pct(p.upnl_pct)}</td>` +
      `<td class="num dn">${pct(p.to_stop_pct)}</td><td class="num up">${pct(p.to_target_pct)}</td><td class="muted">${when(p.created_at)}</td></tr>`),
    'No open positions.');

  table('bysym', [['COIN'], ['TRADES', 'num'], ['WIN', 'num'], ['P&L', 'num']],
    [...d.by_symbol].reverse().map(r => `<tr><td><b>${esc(r.symbol)}</b></td><td class="num">${r.trades}</td><td class="num">${Math.round(r.wins / r.trades * 100)}%</td><td class="num ${cls(r.pnl)}">${money(r.pnl, true)}</td></tr>`),
    'No closed trades yet.');
  table('byreason', [['EXIT'], ['TRADES', 'num'], ['P&L', 'num']],
    d.by_exit_reason.map(r => `<tr><td>${esc(r.reason)}</td><td class="num">${r.trades}</td><td class="num ${cls(r.pnl)}">${money(r.pnl, true)}</td></tr>`), '—');

  table('bots', [['BOT'], ['STATUS'], ['INVESTED', 'num'], ['EQUITY', 'num'], ['P&L', 'num'], ['VS HOLD', 'num'], ['FILLS', 'num']],
    d.paper_bots.map(b => `<tr><td><b>${esc(b.kind)}</b> ${esc(b.symbol)}</td><td class="muted">${esc(b.status)}</td><td class="num">${money(b.investment)}</td>` +
      `<td class="num">${money(b.equity)}</td><td class="num ${cls(b.pnl)}">${money(b.pnl, true)} <span class="muted">${pct(b.pnl_pct)}</span></td>` +
      `<td class="num ${cls(b.hold_pnl_pct)}">${pct(b.hold_pnl_pct)}</td><td class="num">${b.fills ?? 0}</td></tr>`),
    'No paper bots. Start one on the BOTS page.');

  table('trades', [['CLOSED'], ['COIN'], ['ENTRY', 'num'], ['EXIT', 'num'], ['QTY', 'num'], ['P&L', 'num'], ['P&L %', 'num'], ['HELD', 'num'], ['EXIT REASON']],
    d.recent_trades.map(x => `<tr><td class="muted">${when(x.timestamp)}</td><td><b>${esc(x.symbol)}</b></td><td class="num">${price(x.entry_price)}</td>` +
      `<td class="num">${price(x.exit_price)}</td><td class="num">${(+x.quantity).toPrecision(6)}</td><td class="num ${cls(x.pnl_usd)}">${money(x.pnl_usd, true)}</td>` +
      `<td class="num ${cls(x.pnl_pct)}">${pct(x.pnl_pct / 100)}</td><td class="num">${dur(x.duration_seconds)}</td><td class="muted">${esc(x.exit_reason)}</td></tr>`),
    'No closed fleet trades yet.');

  const f = d.funnel, top = Math.max(1, f.signals);
  $('funnel').innerHTML = [['Signals', f.signals], ['Trade ideas', f.intents], ['Debated', f.debates], ['Debate approved', f.debate_approved],
    ['Risk approved', f.risk_approved], ['Orders', f.orders], ['Fills', f.fills], ['Closed trades', f.closed]].map(([l, n]) =>
    `<div class="frow"><span>${l}</span><span class="track"><span class="fill" style="display:block;width:${Math.max(n ? 1.5 : 0, n / top * 100)}%"></span></span><span class="n">${n.toLocaleString()}</span></div>`).join('') +
    `<p class="note">${f.risk_vetoed.toLocaleString()} ideas vetoed by risk. Only approved, filled trades can make or lose money.</p>`;
  $('last-sig').textContent = d.last_signal_at ? 'last signal ' + when(d.last_signal_at) : '';

  table('vetoes', [['REASON'], ['COUNT', 'num']], d.top_vetoes.map(v => `<tr><td>${esc(v.reason)}</td><td class="num">${v.count}</td></tr>`), 'No vetoes.');
  table('fills', [['TIME'], ['COIN'], ['SIDE'], ['PRICE', 'num'], ['QTY', 'num'], ['FEE', 'num'], ['SLIP', 'num']],
    d.recent_fills.map(x => `<tr><td class="muted">${when(x.timestamp)}</td><td>${esc(x.symbol)}</td><td class="${x.side === 'BUY' ? 'up' : 'dn'}">${esc(x.side)}</td>` +
      `<td class="num">${price(x.fill_price)}</td><td class="num">${(+x.quantity).toPrecision(6)}</td><td class="num">${money(x.fee_usd)}</td><td class="num">${pct(x.slippage_pct / 100, 3)}</td></tr>`),
    'No fills yet.');

  const fl = d.fleet || {};
  $('fleet').textContent = fl.running ? `FLEET ${fl.mode} · ${(fl.symbols || []).join(' ')}` : 'FLEET OFF';
  $('fleet').className = 'gov ' + (fl.running ? 'ok' : '');
  $('halt').innerHTML = d.halted ? '<span class="dn">KILL SWITCH ENGAGED — no new trades</span>' : '';
  $('updated').textContent = 'updated ' + when(d.generated_at).slice(11);
}

function toggles() {
  document.querySelectorAll('#tz-seg button').forEach(b => b.classList.toggle('on', b.dataset.tz === state.tz));
  document.querySelectorAll('#ccy-seg button').forEach(b => {
    b.classList.toggle('on', b.dataset.ccy === (inr() ? 'INR' : 'USD'));
    if (b.dataset.ccy === 'INR') b.disabled = !state.fx;
  });
  $('fx').textContent = state.fx ? `₹${state.fx.rate.toFixed(2)}/USD` : '';
}

async function load() {
  try {
    const r = await fetch('/api/pnl');
    if (!r.ok) throw new Error(r.status);
    state.data = await r.json();
    render();
    $('live-dot').className = 'dot'; $('live-label').textContent = 'LIVE';
  } catch (e) {
    $('live-dot').className = 'dot off'; $('live-label').textContent = 'OFFLINE';
  }
}

document.querySelectorAll('#tz-seg button').forEach(b => b.addEventListener('click', () => { state.tz = b.dataset.tz; save('desk.tz', state.tz); toggles(); render(); }));
document.querySelectorAll('#ccy-seg button').forEach(b => b.addEventListener('click', () => { state.ccy = b.dataset.ccy; save('desk.ccy', state.ccy); toggles(); render(); }));
fetch('/api/fx/rate').then(r => r.json()).then(r => { state.fx = (r.status === 'available' || r.status === 'stale') && r.rate > 0 ? r : null; toggles(); render(); }).catch(toggles);
toggles();
load();
setInterval(load, 15000);
})();
