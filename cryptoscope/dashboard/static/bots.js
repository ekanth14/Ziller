/* ZILLERS paper Grid / DCA bots. */
(() => {
'use strict';
const $ = id => document.getElementById(id);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state = {user: null};
const num = (v, d = 2) => v == null ? '—' : Number(v).toLocaleString('en-US', {maximumFractionDigits: d});
const pct = v => v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(2)}%`;
const cls = v => v == null ? '' : v >= 0 ? 'up' : 'dn';
const ist = t => new Date(t * 1000).toLocaleString('en-IN', {timeZone: 'Asia/Kolkata'});

async function post(path, body) {
  const headers = {'Content-Type': 'application/json'};
  if (state.user?.csrf_token) headers['X-CSRF-Token'] = state.user.csrf_token;
  const res = await fetch(path, {method: 'POST', headers, body: JSON.stringify(body || {})});
  const out = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(out.error || `Request failed (${res.status})`);
  return out;
}
async function loadUser() {
  const res = await fetch('/api/auth/me');
  state.user = res.ok ? await res.json() : null;
  $('signin').textContent = state.user ? 'SIGN OUT' : 'SIGN IN';
}
const needLogin = msg => { $('login-err').textContent = msg; $('login').showModal(); };

async function quote() {
  const s = $('symbol').value.trim().toUpperCase();
  try {
    const d = await (await fetch(`/api/market/ticker?symbol=${encodeURIComponent(s)}`)).json();
    const p = d.price || d.last || null;
    $('px').textContent = p ? `Current ${s}: ${num(p, 6)} USDT` : '';
    if (p && !$('lower').value) { $('lower').value = (p * 0.93).toPrecision(6); $('upper').value = (p * 1.07).toPrecision(6); }
  } catch { $('px').textContent = ''; }
}

function render(list, halted) {
  $('meta').textContent = `${list.length} bot${list.length === 1 ? '' : 's'}${halted ? ' · PAUSED by kill switch' : ''}`;
  $('bots').innerHTML = list.length ? list.map(b => {
    const extra = b.kind === 'GRID'
      ? `<div><span>Range</span>${num(b.config.lower, 6)} – ${num(b.config.upper, 6)} ${b.in_range ? '' : '<b class="dn">out of range</b>'}</div><div><span>Round trips</span>${b.round_trips}</div><div><span>Open orders</span>${b.open_orders}</div>`
      : `<div><span>Cycles</span>${b.cycles}</div><div><span>Avg entry</span>${num(b.avg_entry, 6)}</div><div><span>Take profit at</span>${num(b.take_profit_price, 6)} · ${b.safety_left} SO left</div>`;
    return `<div class="bot"><div class="h"><span><span class="t">${esc(b.kind)} · ${esc(b.symbol)}</span> <span class="tag3 ${b.status === 'RUNNING' ? 'run' : 'stop'}">${esc(b.status)}</span> <span class="muted">since ${ist(b.created_at)} IST</span></span>` +
      `<span>${b.status === 'RUNNING' ? `<button class="btn" data-act="stop" data-id="${b.id}">STOP</button>` : `<button class="btn" data-act="resume" data-id="${b.id}">RESUME</button>`} <button class="btn danger" data-act="delete" data-id="${b.id}">DELETE</button></span></div>` +
      `<div class="kv"><div><span>Equity</span>${num(b.equity)} USDT</div><div><span>P&amp;L</span><b class="${cls(b.pnl)}">${num(b.pnl)} (${pct(b.pnl_pct)})</b></div>` +
      `<div><span>Buy &amp; hold</span><span class="${cls(b.hold_pnl_pct)}" style="display:inline">${pct(b.hold_pnl_pct)}</span></div><div><span>Realised</span>${num(b.realized)}</div>` +
      `<div><span>Fees</span>${num(b.fees)}</div><div><span>Fills</span>${b.fills}</div>${extra}<div><span>Mark</span>${num(b.mark, 6)}</div></div>` +
      `<div class="fills" id="f-${b.id}"></div></div>`;
  }).join('') : '<p class="muted">No bots yet. Start one on the left.</p>';
  list.slice(0, 6).forEach(async b => {
    try {
      const d = await (await fetch(`/api/bots/${b.id}`)).json();
      const el = $(`f-${b.id}`);
      if (el) el.innerHTML = d.recent_fills.map(f => `${ist(f.ts)} · <b class="${f.side === 'BUY' ? 'up' : 'dn'}">${f.side}</b> ${num(f.qty, 6)} @ ${num(f.price, 6)} · ${esc(f.note)}`).join('<br>') || 'no fills yet';
    } catch {}
  });
}

async function load() {
  try {
    const d = await (await fetch('/api/bots')).json();
    render(d.bots, d.halted);
    $('gov').className = `gov ${d.halted ? 'halt' : 'ok'}`; $('gov').textContent = d.halted ? 'HALTED · bots paused' : 'GOVERNOR OK';
    $('live-dot').className = 'dot'; $('live-label').textContent = 'LIVE';
  } catch { $('live-dot').className = 'dot off'; $('live-label').textContent = 'OFFLINE'; }
}

$('kind').addEventListener('change', () => { const g = $('kind').value === 'GRID'; $('grid-f').hidden = !g; $('dca-f').hidden = g; });
$('symbol').addEventListener('change', () => { $('lower').value = ''; $('upper').value = ''; quote(); });
$('create').addEventListener('click', async () => {
  if (!state.user) return needLogin('Sign in as admin to start a paper bot.');
  $('err').textContent = '';
  const kind = $('kind').value, v = id => parseFloat($(id).value);
  const config = kind === 'GRID'
    ? {investment: v('investment'), lower: v('lower'), upper: v('upper'), levels: parseInt($('levels').value, 10)}
    : {investment: v('investment'), base_order: v('base_order'), safety_orders: parseInt($('safety_orders').value, 10),
       step: v('step') / 100, step_scale: v('step_scale'), volume_scale: v('volume_scale'), take_profit: v('take_profit') / 100, stop_loss: v('stop_loss') / 100};
  try { await post('/api/bots/create', {kind, symbol: $('symbol').value.trim().toUpperCase(), config}); load(); }
  catch (err) { $('err').textContent = err.message; }
});
$('bots').addEventListener('click', async e => {
  const b = e.target.closest('button[data-act]'); if (!b) return;
  if (!state.user) return needLogin('Sign in as admin.');
  if (b.dataset.act === 'delete' && !confirm('Delete this paper bot and its fill history?')) return;
  try { await post(`/api/bots/${b.dataset.id}/${b.dataset.act}`); } catch (err) { alert(err.message); }
  load();
});
$('signin').addEventListener('click', async () => { if (state.user) { try { await post('/api/auth/logout'); } catch {} return loadUser(); } needLogin(''); });
$('login-cancel').addEventListener('click', () => $('login').close());
$('login-form').addEventListener('submit', async e => {
  e.preventDefault();
  try { await post('/api/auth/login', {email: $('email').value, password: $('password').value}); $('password').value = ''; $('login').close(); await loadUser(); }
  catch (err) { $('login-err').textContent = err.message; }
});
loadUser(); quote(); load(); setInterval(load, 20000);
})();
