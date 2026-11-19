/* ZILLERS System page: device hardware, network latency, market-data delay, AI systems, autotrader fleet. */
(() => {
'use strict';
const $ = id => document.getElementById(id);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const dur = s => s == null ? '—' : s >= 86400 ? `${Math.floor(s / 86400)}d ${Math.floor(s % 86400 / 3600)}h` : s >= 3600 ? `${Math.floor(s / 3600)}h ${Math.floor(s % 3600 / 60)}m` : `${Math.floor(s / 60)}m ${s % 60}s`;
const lvl = p => p >= 90 ? 'hot' : p >= 70 ? 'warn' : '';
const kv = rows => rows.map(([k, v]) => `<span>${esc(k)}</span><span>${v}</span>`).join('');
const gauge = (label, p, right) => `<div class="gauge"><div class="lab"><span>${label}</span><span>${right ?? (p == null ? '—' : p.toFixed(1) + '%')}</span></div>` +
  `<div class="track"><div class="fill ${lvl(p || 0)}" style="width:${Math.min(100, p || 0)}%"></div></div></div>`;
const msCls = ms => ms == null ? 'bad' : ms > 800 ? 'warn' : 'ok';
const state = {user: null};

function spark(values) {
  const v = values.filter(x => x != null);
  if (v.length < 2) return '';
  const max = Math.max(...v), min = Math.min(...v), w = 110, h = 22;
  const pts = values.map((x, i) => x == null ? null : `${(i / (values.length - 1) * w).toFixed(1)},${(h - 2 - ((x - min) / ((max - min) || 1)) * (h - 4)).toFixed(1)}`).filter(Boolean);
  return `<svg class="spark" viewBox="0 0 ${w} ${h}"><polyline fill="none" stroke="#4aa8ff" stroke-width="1.5" points="${pts.join(' ')}"/></svg>`;
}

function render(m) {
  const h = m.hardware;
  $('host').textContent = h.host;
  $('device').innerHTML = kv([['OS', esc(h.os)], ['Machine', esc(h.machine)], ['CPU', esc(h.cpu_model || '—')],
    ['Python', esc(h.python)], ['Uptime', dur(h.uptime_s)], ['Boot', new Date(h.boot_time * 1000).toLocaleString()]]);
  $('cpu-meta').textContent = `${h.cpu.cores_physical}C / ${h.cpu.cores_logical}T · ${h.cpu.freq_mhz ?? '—'} MHz`;
  $('cpu').innerHTML = gauge('Total load', h.cpu.percent);
  $('cores').innerHTML = h.cpu.per_core.map((p, i) => `<i title="core ${i}: ${p}%"><b style="height:${p}%"></b></i>`).join('');
  const b = h.battery;
  $('mem').innerHTML = gauge(`RAM ${h.memory.used_gb} / ${h.memory.total_gb} GB`, h.memory.percent) + gauge('Swap', h.memory.swap_percent) +
    h.disks.map(d => gauge(`Disk ${esc(d.mount)} ${d.used_gb} / ${d.total_gb} GB`, d.percent)).join('') +
    (b ? gauge(`Battery ${b.plugged ? '· charging' : '· on battery'}${b.secs_left ? ' · ' + dur(b.secs_left) + ' left' : ''}`, b.percent) : '');
  const p = h.process, n = h.network;
  $('net').innerHTML = kv([['Upload', `${n.sent_kbps ?? '—'} KB/s`], ['Download', `${n.recv_kbps ?? '—'} KB/s`],
    ['Sent / recv', `${n.sent_mb} / ${n.recv_mb} MB`], ['Errors / drops', `${n.errors} / ${n.drops}`],
    ['Server PID', p.pid], ['Server CPU', `${p.cpu_percent.toFixed(1)}%`], ['Server RAM', `${p.rss_mb} MB`],
    ['Threads', p.threads], ['Sockets', p.connections ?? '—'], ['Server up', dur(p.uptime_s)]]);
  const L = m.latency;
  const off = L.clock_offset_ms;
  $('clock').innerHTML = `clock vs Binance <span class="${off == null ? 'bad' : Math.abs(off) > 1000 ? 'warn' : 'ok'}">${off == null ? 'unknown' : (off > 0 ? '+' : '') + off + ' ms'}</span>`;
  $('ping').innerHTML = '<tr><th>TARGET</th><th class="num">RTT</th><th>STATUS</th><th>HISTORY</th></tr>' +
    L.targets.map(t => `<tr><td>${esc(t.name)}</td><td class="num ${msCls(t.ms)}">${t.ms == null ? '—' : t.ms + ' ms'}</td>` +
      `<td class="${t.ok ? 'ok' : 'bad'}">${t.ok ? 'UP' : 'DOWN ' + esc(t.error || t.status || '')}</td><td>${spark(m.latency_history[t.name] || [])}</td></tr>`).join('');
  const ex = (m.feeds && m.feeds.exchanges) || {};
  $('feeds').innerHTML = '<tr><th>FEED</th><th>STATE</th><th>TYPE</th><th class="num">LAST MSG AGE</th><th class="num">LATENCY</th><th class="num">ERRORS</th></tr>' +
    Object.entries(ex).map(([k, f]) => `<tr><td>${esc(k)}</td><td class="${f.state === 'connected' ? 'ok' : 'bad'}">${esc(f.state)}</td><td>${esc(f.feed || '—')}</td>` +
      `<td class="num ${f.heartbeat_age_s == null ? 'bad' : f.heartbeat_age_s > 5 ? 'warn' : 'ok'}">${f.heartbeat_age_s == null ? '—' : f.heartbeat_age_s.toFixed(1) + ' s'}</td>` +
      `<td class="num">${f.latency_ms == null ? '—' : f.latency_ms + ' ms'}</td><td class="num">${f.errors ?? 0}</td></tr>`).join('');
  const tk = (m.feeds && m.feeds.tickers) || {};
  $('ticks').innerHTML = '<tr><th>TICKER</th><th>STATUS</th><th class="num">DATA AGE</th><th class="num">SOURCES</th><th>PER-SOURCE LATENCY</th></tr>' +
    Object.entries(tk).map(([k, t]) => `<tr><td>${esc(k)}</td><td class="${t.status === 'verified' ? 'ok' : 'warn'}">${esc(t.status)}</td>` +
      `<td class="num">${t.age_s == null ? '—' : (+t.age_s).toFixed(2) + ' s'}</td><td class="num">${t.sources ?? '—'}</td>` +
      `<td class="muted">${t.source_latencies ? Object.entries(t.source_latencies).map(([s, v]) => `${esc(s)} ${v == null ? '—' : Math.round(v) + 'ms'}`).join(' · ') : '—'}</td></tr>`).join('');
  const a = m.ai || {};
  $('ai').innerHTML = kv([['Ollama', `<span class="${a.status === 'available' ? 'ok' : 'bad'}">${esc(a.status)}</span> ${esc(a.model || '')}`],
    ['Ollama role', esc(a.role || '')], ['Laya classifier', `${esc(a.laya?.status)} · checkpoint ${a.laya?.checkpoint_loaded ? 'loaded' : 'missing'}`],
    ['Laya evaluations', a.laya?.evaluations ?? 0], ['SMC Tier 1', '<span class="ok">in-process</span>'],
    ['Committee + THX-02', '<span class="ok">in-process</span>'], ['C++ kernels', 'Python fallback if blocked']]);
  renderFleet(m.fleet);
  $('live-dot').className = 'dot'; $('live-label').textContent = 'LIVE';
}

function renderFleet(f) {
  if (!f) return;
  $('fleet-pill').textContent = f.running ? `AUTOTRADER ${f.mode}` : 'AUTOTRADER OFF';
  $('fleet-pill').className = `fleet-pill ${f.running ? 'run' : ''}`;
  $('fleet-state').innerHTML = f.running
    ? `<span class="ok">RUNNING</span> ${esc(f.mode)} · ${esc(f.symbols.join(' '))} · pid ${f.pid} · up ${dur(f.uptime_s)}`
    : (f.exit_code != null ? `<span class="warn">STOPPED</span> exit ${f.exit_code}` : 'not running');
  $('fleet-start').disabled = f.running; $('fleet-stop').disabled = !f.running;
  const box = $('fleet-log'), atEnd = box.scrollTop + box.clientHeight >= box.scrollHeight - 10;
  box.textContent = (f.log_tail || []).join('\n') || 'No fleet output yet.';
  if (atEnd) box.scrollTop = box.scrollHeight;
}

async function tick() {
  try {
    const r = await fetch('/api/system/metrics');
    render(await r.json());
  } catch (e) { $('live-dot').className = 'dot off'; $('live-label').textContent = 'OFFLINE'; }
  try {
    const g = await (await fetch('/api/governor/status')).json();
    const halted = g.kill_switch_engaged || g.emergency_halted;
    $('gov').className = `gov ${halted ? 'halt' : 'ok'}`;
    $('gov').textContent = halted ? `HALTED · ${g.action || 'HALT'} · AI stopped` : `GOVERNOR OK · ${g.mode}`;
    $('kill').classList.toggle('engaged', !!halted);
    $('resume').hidden = !halted;
    $('kill').textContent = halted ? '■ KILLED' : '■ KILL SWITCH';
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

$('signin').addEventListener('click', async () => {
  if (state.user) { try { await post('/api/auth/logout'); } catch {} return loadUser(); }
  $('login-err').textContent = ''; $('login').showModal();
});
$('login-cancel').addEventListener('click', () => $('login').close());
$('login-form').addEventListener('submit', async e => {
  e.preventDefault();
  try { await post('/api/auth/login', {email: $('email').value, password: $('password').value}); $('password').value = ''; $('login').close(); await loadUser(); }
  catch (err) { $('login-err').textContent = err.message; }
});
$('fleet-start').addEventListener('click', async () => {
  $('fleet-err').textContent = '';
  const mode = $('fleet-mode').value, symbols = $('fleet-symbols').value.trim().toUpperCase().split(/[\s,]+/).filter(Boolean);
  if (!confirm(`Start the autotrader fleet in ${mode} mode for ${symbols.length ? symbols.join(', ') : 'the scanner top picks'}?`)) return;
  try { renderFleet(await post('/api/fleet/start', {mode, symbols})); } catch (err) { $('fleet-err').textContent = err.message; }
});
const loadGovernor = tick;
$('resume').addEventListener('click', () => {
  if (!state.user) { $('login-err').textContent = 'Sign in as admin to resume.'; $('login').showModal(); return; }
  $('resume-err').textContent = ''; $('resume-dlg').showModal();
});
$('resume-cancel').addEventListener('click', () => $('resume-dlg').close());
$('resume-form').addEventListener('submit', async e => {
  e.preventDefault();
  try {
    await post('/api/governor/resume', {password: $('resume-password').value});
    $('resume-password').value = ''; $('resume-dlg').close(); tick();
  } catch (err) { $('resume-err').textContent = err.message; }
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

$('fleet-stop').addEventListener('click', async () => {
  $('fleet-err').textContent = '';
  try { renderFleet(await post('/api/fleet/stop')); } catch (err) { $('fleet-err').textContent = err.message; }
});

async function loadTelegram() {
  try {
    const t = await (await fetch('/api/telegram/status')).json();
    $('tg-state').innerHTML = t.configured ? '<span class="ok">CONFIGURED</span>'
      : `<span class="bad">NOT CONFIGURED</span> ${t.token_set ? '' : '· bot token missing '}${t.owner_chat_set ? '' : '· owner chat id missing'}`;
    $('tg-test').disabled = !t.configured;
  } catch { $('tg-state').textContent = 'unknown'; }
}
$('tg-test').addEventListener('click', async () => {
  if (!state.user) { $('login-err').textContent = 'Sign in as admin to send a test message.'; $('login').showModal(); return; }
  $('tg-result').textContent = 'sending…';
  try { const r = await post('/api/telegram/test'); $('tg-result').innerHTML = `<span class="ok">Delivered</span> (message ${r.message_id}) — check your Telegram.`; }
  catch (err) { $('tg-result').innerHTML = `<span class="bad">${esc(err.message)}</span>`; }
});
async function loadProtections() {
  try {
    const p = await (await fetch('/api/protections')).json();
    $('prot-state').innerHTML = p.locks.length ? `<span class="warn">${p.locks.length} active lock${p.locks.length > 1 ? 's' : ''}</span>` : '<span class="ok">no active locks</span>';
    $('prot').innerHTML = p.locks.length ? '<tr><th>PAIR</th><th>GUARD</th><th>REASON</th><th class="num">REMAINING</th></tr>' + p.locks.map(l =>
      `<tr><td>${l.pair === '*' ? '<b>ALL PAIRS</b>' : esc(l.pair)}</td><td>${esc(l.guard)}</td><td>${esc(l.reason)}</td><td class="num">${Math.ceil(l.remaining_s / 60)} min</td></tr>`).join('') : '';
    const c = p.config || {};
    $('prot-cfg').textContent = `Cooldown ${c.cooldown_minutes} min after any exit · ${c.stoploss_limit} stop-losses in ${c.stoploss_lookback_minutes / 60} h → pause ${c.stoploss_lock_minutes} min · ` +
      `last ${c.lowprofit_trades} trades ≤ ${(c.lowprofit_required * 100).toFixed(1)}% → lock pair ${c.lowprofit_lock_hours} h · closed-trade drawdown ≥ ${(c.max_drawdown * 100).toFixed(0)}% in ${c.drawdown_lookback_hours} h → pause all ${c.drawdown_lock_hours} h.`;
  } catch {}
}
loadProtections(); setInterval(loadProtections, 15000);
loadTelegram();
loadUser(); tick();
setInterval(tick, 3000);
})();
