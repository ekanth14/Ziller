/* ZILLERS Scanner: every Binance USDT pair, factor ranking, top picks, autopilot control. */
(() => {
'use strict';
const $ = id => document.getElementById(id);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const store = (k, d) => { try { return localStorage.getItem(k) || d; } catch { return d; } };
const state = {user: null, data: null, fx: null, ccy: store('desk.ccy', 'INR'), sort: 'quote_volume', dir: -1};
const pct = (v, d = 1) => v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(d)}%`;
const cls = v => v == null ? '' : v >= 0 ? 'up' : 'dn';
const k = () => state.ccy === 'INR' && state.fx ? state.fx.rate : 1;
const money = v => v == null ? '—' : (state.ccy === 'INR' && state.fx ? '₹' : '$') +
  (v * k()).toLocaleString(state.ccy === 'INR' ? 'en-IN' : 'en-US', {maximumFractionDigits: Math.abs(v * k()) >= 100 ? 2 : Math.abs(v * k()) >= 1 ? 4 : 8});
const big = v => { v *= k(); const s = state.ccy === 'INR' && state.fx ? '₹' : '$';
  return v >= 1e7 && s === '₹' ? `${s}${(v / 1e7).toFixed(1)} Cr` : v >= 1e9 ? `${s}${(v / 1e9).toFixed(2)}B` : v >= 1e6 ? `${s}${(v / 1e6).toFixed(1)}M` : `${s}${(v / 1e3).toFixed(0)}K`; };
const REASONS = {operator_excluded: 'excluded (BTC/ETH/SOL)', stable_or_leveraged: 'stable / leveraged', illiquid: 'low volume', spike_24h: '24h spike', not_on_testnet: 'not on testnet'};

function renderTop(d) {
  const picks = d.top.map(s => d.ranked.find(r => r.symbol === s)).filter(Boolean);
  const t = d.tiers || {};
  $('top-meta').textContent = `${d.mode} · ${d.counts.universe} pairs scanned · ${d.counts.scored} scored · ${picks.length} picks ` +
    `(${(t.TREND || []).length} trend · ${(t.SHORT_TERM || []).length} short-term · ${(t.POTENTIAL || []).length} potential) · targets 0.5–1%`;
  $('scan-meta').textContent = `scanned ${new Date(d.generated_at * 1000).toLocaleTimeString('en-IN', {timeZone: 'Asia/Kolkata'})} IST · ${d.took_s}s`;
  const TIER = {TREND: ['TREND', 'daily uptrend'], SHORT_TERM: ['SHORT-TERM', '1h uptrend'], POTENTIAL: ['POTENTIAL', 'best mover, no trend']};
  $('top5').innerHTML = picks.length ? picks.map((r, i) => {
    const tier = TIER[r.tier] || ['', ''], f = r.intraday;
    const line = r.tier === 'TREND' ? `score ${r.score.toFixed(2)} · 7d ${pct(r.factors.r7)} · 30d ${pct(r.factors.r30)}`
      : f ? `4h ${pct(f.r4h)} · 24h ${pct(f.r24h)} · moves ${pct(f.atr1h_pct)}/h · RSI1h ${f.rsi1h?.toFixed(0)}` : '';
    return `<div class="pick"><div class="s">#${i + 1} ${esc(r.symbol)} <span class="tag2 ${r.tier === 'TREND' ? 'ok' : ''}" title="${tier[1]}">${tier[0]}</span></div>` +
      `<div>${money(r.price)} <span class="${cls(r.chg_24h)}">${pct(r.chg_24h)}</span></div><div class="k">${line}</div>` +
      `<div class="k">${big(r.quote_volume)}/24h · daily RSI ${r.factors.rsi14?.toFixed(0)}</div></div>`;
  }).join('')
    : `<div class="empty" style="grid-column:1/-1">No liquid coin can move 0.5–1% without being in free fall right now. Rescans every 4 h.</div>`;
  $('method').textContent = d.method;
}

function renderTable() {
  const d = state.data; if (!d) return;
  const q = $('q').value.trim().toUpperCase(), f = $('filter').value;
  const scored = new Map(d.ranked.map(r => [r.symbol, r]));
  let rows = d.all.map(r => scored.get(r.symbol) || r);
  if (q) rows = rows.filter(r => r.symbol.includes(q));
  if (f === 'scored') rows = rows.filter(r => r.factors);
  if (f === 'eligible') rows = rows.filter(r => r.eligible);
  const val = r => state.sort === 'score' ? (r.score ?? -99) : state.sort === 'r7' ? (r.factors?.r7 ?? -99) : (r[state.sort] ?? -99);
  rows.sort((a, b) => (val(a) > val(b) ? 1 : val(a) < val(b) ? -1 : 0) * state.dir);
  $('all-meta').textContent = `${rows.length} shown`;
  const th = (key, label, num) => `<th data-k="${key}" class="${num ? 'num' : ''}">${label}${state.sort === key ? (state.dir < 0 ? ' ▼' : ' ▲') : ''}</th>`;
  $('tbl').innerHTML = `<tr>${th('symbol', 'PAIR')}${th('price', 'PRICE', 1)}${th('chg_24h', '24H', 1)}${th('quote_volume', '24H VOLUME', 1)}` +
    `${th('r7', '7D', 1)}<th class="num">30D</th><th class="num">RSI</th>${th('score', 'SCORE', 1)}` +
    `${th('mom_rank', '<span title="Liu-Tsyvinski-Wu 3-week momentum rank (1 = strongest). Weight 0 until the Lab validates it.">MOM RK</span>', 1)}` +
    `${th('size_rank', '<span title="Liu-Tsyvinski-Wu size rank by 24h traded value (1 = smallest). Weight 0 until the Lab validates it.">SIZE RK</span>', 1)}<th>STATUS</th></tr>` +
    rows.slice(0, 600).map(r => {
      const fct = r.factors;
      const status = d.top.includes(r.symbol) ? `<span class="tag2 ok">PICK · ${esc((r.tier || '').replace('_', '-'))}</span>`
        : r.excluded ? `<span class="tag2">${esc(REASONS[r.excluded] || r.excluded)}</span>`
        : fct ? (r.eligible ? '<span class="tag2 ok">eligible</span>' : `<span class="tag2 no">${esc(r.why_not.join(', '))}</span>`)
        : `<span class="tag2">${r.error ? 'no candles' : 'not shortlisted'}</span>`;
      return `<tr class="${d.top.includes(r.symbol) ? 'top' : ''}"><td>${esc(r.symbol)}</td><td class="num">${money(r.price)}</td>` +
        `<td class="num ${cls(r.chg_24h)}">${pct(r.chg_24h)}</td><td class="num">${big(r.quote_volume)}</td>` +
        `<td class="num ${cls(fct?.r7)}">${fct ? pct(fct.r7) : '—'}</td><td class="num ${cls(fct?.r30)}">${fct ? pct(fct.r30) : '—'}</td>` +
        `<td class="num">${fct?.rsi14 != null ? fct.rsi14.toFixed(0) : '—'}</td><td class="num">${r.score != null ? r.score.toFixed(2) : '—'}</td>` +
        `<td class="num muted">${r.mom_rank != null ? r.mom_rank.toFixed(2) : '—'}</td><td class="num muted">${r.size_rank != null ? r.size_rank.toFixed(2) : '—'}</td><td>${status}</td></tr>`;
    }).join('');
}

async function scan(force) {
  $('rescan').disabled = true;
  try {
    const mode = $('ap-mode').value;
    const r = await fetch(`/api/scanner?mode=${mode}${force ? '&force=1' : ''}`);
    const d = await r.json();
    if (d.status !== 'OK') throw new Error(d.error || d.status);
    state.data = d; renderTop(d); renderTable();
    $('live-dot').className = 'dot'; $('live-label').textContent = 'LIVE';
  } catch (e) { $('live-dot').className = 'dot off'; $('live-label').textContent = 'OFFLINE'; $('scan-meta').textContent = `scan failed: ${e.message}`; }
  $('rescan').disabled = false;
}

async function loadAutopilot() {
  try {
    const a = await (await fetch('/api/scanner/autopilot')).json();
    $('ap-state').innerHTML = a.enabled ? `<span class="ok">ON</span> · ${esc(a.mode)} · every ${a.period_hours}h` : 'off';
    const l = a.last || {};
    $('ap-last').textContent = l.at ? `last run ${new Date(l.at * 1000).toLocaleString('en-IN', {timeZone: 'Asia/Kolkata'})} IST · ${l.action} · top: ${(l.top || []).join(', ') || 'none'}` : '';
    const f = await (await fetch('/api/fleet/status')).json();
    $('fleet-pill').textContent = f.running ? `AUTOTRADER ${f.mode} · ${f.symbols.join(' ')}` : 'AUTOTRADER OFF';
    $('fleet-pill').className = `fleet-pill ${f.running ? 'run' : ''}`;
    const g = await (await fetch('/api/governor/status')).json();
    const halted = g.kill_switch_engaged || g.emergency_halted;
    $('gov').className = `gov ${halted ? 'halt' : 'ok'}`; $('gov').textContent = halted ? 'HALTED · AI stopped' : `GOVERNOR OK · ${g.mode}`;
    $('kill').classList.toggle('engaged', !!halted); $('kill').textContent = halted ? '■ KILLED' : '■ KILL SWITCH';
  } catch {}
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
const needLogin = msg => { $('login-err').textContent = msg; $('login').showModal(); };

$('signin').addEventListener('click', async () => {
  if (state.user) { try { await post('/api/auth/logout'); } catch {} return loadUser(); }
  needLogin('');
});
$('login-cancel').addEventListener('click', () => $('login').close());
$('login-form').addEventListener('submit', async e => {
  e.preventDefault();
  try { await post('/api/auth/login', {email: $('email').value, password: $('password').value}); $('password').value = ''; $('login').close(); await loadUser(); }
  catch (err) { $('login-err').textContent = err.message; }
});
$('ap-start').addEventListener('click', async () => {
  if (!state.user) return needLogin('Sign in as admin to start the autopilot.');
  const mode = $('ap-mode').value;
  if (!confirm(`Start the autopilot in ${mode}?\nIt scans all Binance USDT pairs, starts the fleet on the 10 best picks (trend first, then short-term movers; BTC, ETH and SOL excluded), targets 0.5–1% per trade and rescans every 4 hours.`)) return;
  $('ap-err').textContent = 'scanning…';
  try { const r = await post('/api/scanner/autopilot', {enable: true, mode}); $('ap-err').textContent = r.top.length ? `trading ${r.top.join(', ')}` : 'no eligible pairs right now — fleet not started'; }
  catch (err) { $('ap-err').textContent = err.message; }
  loadAutopilot(); scan(false);
});
$('ap-stop').addEventListener('click', async () => {
  if (!state.user) return needLogin('Sign in as admin.');
  try { await post('/api/scanner/autopilot', {enable: false}); $('ap-err').textContent = 'autopilot off (the fleet keeps running until you stop it on the System page)'; }
  catch (err) { $('ap-err').textContent = err.message; }
  loadAutopilot();
});
$('kill').addEventListener('click', async () => {
  if (!state.user) return needLogin('Sign in to use the kill switch.');
  if (!confirm('MASTER KILL SWITCH: halt trading, stop the autopilot, the fleet and every AI model?')) return;
  try { await post('/api/governor/kill_switch', {action: 'HALT'}); } catch (err) { alert(err.message); }
  loadAutopilot();
});
$('rescan').addEventListener('click', () => scan(true));
$('ap-mode').addEventListener('change', () => scan(false));
$('q').addEventListener('input', renderTable);
$('filter').addEventListener('change', renderTable);
$('tbl').addEventListener('click', e => {
  const key = e.target.closest('th')?.dataset.k; if (!key) return;
  state.dir = state.sort === key ? -state.dir : -1; state.sort = key; renderTable();
});
document.querySelectorAll('#ccy-seg button').forEach(b => b.addEventListener('click', () => {
  if (b.dataset.ccy === 'INR' && !state.fx) return;
  state.ccy = b.dataset.ccy; try { localStorage.setItem('desk.ccy', state.ccy); } catch {}
  renderCcy(); if (state.data) { renderTop(state.data); renderTable(); }
}));
function renderCcy() { document.querySelectorAll('#ccy-seg button').forEach(b => { b.classList.toggle('on', b.dataset.ccy === (state.fx ? state.ccy : 'USD')); if (b.dataset.ccy === 'INR') b.disabled = !state.fx; }); }
(async () => {
  try { const r = await (await fetch('/api/fx/rate')).json(); state.fx = (r.status === 'available' || r.status === 'stale') && r.rate > 0 ? r : null; } catch {}
  renderCcy(); loadUser(); loadAutopilot(); scan(false);
  setInterval(loadAutopilot, 15000);
  setInterval(() => scan(false), 300000);
})();
})();
