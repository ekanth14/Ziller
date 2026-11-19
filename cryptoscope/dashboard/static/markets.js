/* ZILLERS Markets: every coin listed on Binance spot. */
(() => {
'use strict';
const $ = id => document.getElementById(id);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const store = (k, d) => { try { return localStorage.getItem(k) || d; } catch { return d; } };
const state = {data: null, fx: null, ccy: store('desk.ccy', 'INR'), sort: 'volume_usd', dir: -1, open: new Set()};
const inr = () => state.ccy === 'INR' && state.fx;
const k = () => inr() ? state.fx.rate : 1;
const sym = () => inr() ? '₹' : '$';
const pct = v => v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(2)}%`;
const cls = v => v == null ? '' : v >= 0 ? 'up' : 'dn';
const price = v => { if (v == null) return '—'; const x = v * k();
  return sym() + x.toLocaleString(inr() ? 'en-IN' : 'en-US', {maximumFractionDigits: Math.abs(x) >= 100 ? 2 : Math.abs(x) >= 1 ? 4 : 8}); };
const big = v => { if (v == null) return '—'; const x = v * k();
  if (inr()) return x >= 1e7 ? `₹${(x / 1e7).toLocaleString('en-IN', {maximumFractionDigits: 2})} Cr` : x >= 1e5 ? `₹${(x / 1e5).toFixed(2)} L` : `₹${x.toFixed(0)}`;
  return x >= 1e9 ? `$${(x / 1e9).toFixed(2)}B` : x >= 1e6 ? `$${(x / 1e6).toFixed(2)}M` : x >= 1e3 ? `$${(x / 1e3).toFixed(1)}K` : `$${x.toFixed(0)}`; };

function render() {
  const d = state.data; if (!d) return;
  $('s-coins').textContent = d.counts.coins.toLocaleString();
  $('s-pairs').textContent = d.counts.pairs.toLocaleString();
  $('s-quotes').textContent = d.counts.quotes;
  $('s-vol').textContent = big(d.total_volume_usd);
  const q = $('q').value.trim().toUpperCase(), quote = $('quote').value, view = $('view').value;
  let rows = d.coins.filter(c => (!q || c.asset.includes(q) || (c.name || '').toUpperCase().includes(q)) && (!quote || c.quotes.includes(quote)));
  if (view === 'usdt') rows = rows.filter(c => c.usdt_pair);
  if (view === 'gainers') rows = rows.filter(c => c.chg_24h != null).sort((a, b) => b.chg_24h - a.chg_24h);
  else if (view === 'losers') rows = rows.filter(c => c.chg_24h != null).sort((a, b) => a.chg_24h - b.chg_24h);
  else {
    const v = c => state.sort === 'asset' ? c.asset : (c[state.sort] ?? (state.dir < 0 ? -Infinity : Infinity));
    rows.sort((a, b) => (v(a) > v(b) ? 1 : v(a) < v(b) ? -1 : 0) * state.dir);
  }
  $('meta').textContent = `${rows.length} of ${d.counts.coins} coins · updated ${new Date(d.generated_at * 1000).toLocaleTimeString('en-IN', {timeZone: 'Asia/Kolkata'})} IST${d.status === 'STALE' ? ' · STALE' : ''}`;
  const th = (key, label, num) => `<th data-k="${key}" class="${num ? 'num' : ''}">${label}${state.sort === key && view === 'all' ? (state.dir < 0 ? ' ▼' : ' ▲') : ''}</th>`;
  const html = [`<tr><th>#</th>${th('asset', 'COIN')}${th('price_usd', 'PRICE', 1)}${th('chg_24h', '24H', 1)}${th('volume_usd', '24H VOLUME', 1)}` +
    `${th('market_cap', 'MARKET CAP', 1)}${th('pair_count', 'PAIRS', 1)}${th('trades_24h', 'TRADES 24H', 1)}<th>QUOTES</th><th></th></tr>`];
  rows.forEach((c, i) => {
    html.push(`<tr data-a="${esc(c.asset)}"><td class="muted">${c.rank ? '#' + c.rank : i + 1}</td>` +
      `<td><span class="coin">${c.image ? `<img src="${esc(c.image)}" alt="" loading="lazy">` : ''}<b>${esc(c.asset)}</b>${c.name ? `<span class="n">${esc(c.name)}</span>` : ''}</span></td>` +
      `<td class="num">${price(c.price_usd)}</td><td class="num ${cls(c.chg_24h)}">${pct(c.chg_24h)}</td><td class="num">${big(c.volume_usd)}</td>` +
      `<td class="num">${c.market_cap ? big(c.market_cap) : '—'}</td><td class="num">${c.pair_count}</td><td class="num">${c.trades_24h.toLocaleString()}</td>` +
      `<td>${c.quotes.slice(0, 6).map(x => `<span class="q">${esc(x)}</span>`).join('')}${c.quotes.length > 6 ? `<span class="q">+${c.quotes.length - 6}</span>` : ''}</td>` +
      `<td>${c.usdt_pair ? `<a class="open" href="/?symbol=${encodeURIComponent(c.usdt_pair)}">OPEN</a>` : ''}</td></tr>`);
    if (state.open.has(c.asset)) c.pairs.forEach(p => html.push(`<tr class="more"><td></td><td>↳ ${esc(p.symbol)}</td>` +
      `<td class="num">${p.last != null ? p.last.toLocaleString('en-US', {maximumFractionDigits: 8}) + ' ' + esc(p.quote) : '—'}</td>` +
      `<td class="num ${cls(p.chg_24h)}">${pct(p.chg_24h)}</td><td class="num">${big(p.volume_usd)}</td><td colspan="5"></td></tr>`));
  });
  $('tbl').innerHTML = html.join('');
}

async function load() {
  try {
    const d = await (await fetch('/api/markets')).json();
    if (!d.coins || !d.coins.length) throw new Error(d.error || d.status);
    state.data = d;
    if ($('quote').options.length === 1) $('quote').innerHTML += Object.entries(d.quote_counts).map(([q, n]) => `<option value="${esc(q)}">${esc(q)} (${n})</option>`).join('');
    $('live-dot').className = 'dot'; $('live-label').textContent = d.status === 'STALE' ? 'STALE' : 'LIVE';
    render();
  } catch (e) { $('live-dot').className = 'dot off'; $('live-label').textContent = 'OFFLINE'; $('meta').textContent = `unavailable: ${e.message}`; }
}
function renderCcy() {
  document.querySelectorAll('#ccy-seg button').forEach(b => { b.classList.toggle('on', b.dataset.ccy === (state.fx ? state.ccy : 'USD')); if (b.dataset.ccy === 'INR') b.disabled = !state.fx; });
  $('fx').textContent = state.fx ? `₹${state.fx.rate.toFixed(2)}/USD` : 'INR rate unavailable';
}

$('q').addEventListener('input', render);
$('quote').addEventListener('change', render);
$('view').addEventListener('change', render);
$('tbl').addEventListener('click', e => {
  const key = e.target.closest('th')?.dataset.k;
  if (key) { state.dir = state.sort === key ? -state.dir : -1; state.sort = key; return render(); }
  if (e.target.closest('a')) return;
  const a = e.target.closest('tr')?.dataset.a; if (!a) return;
  state.open.has(a) ? state.open.delete(a) : state.open.add(a); render();
});
document.querySelectorAll('#ccy-seg button').forEach(b => b.addEventListener('click', () => {
  if (b.dataset.ccy === 'INR' && !state.fx) return;
  state.ccy = b.dataset.ccy; try { localStorage.setItem('desk.ccy', state.ccy); } catch {} renderCcy(); render();
}));
(async () => {
  try { const r = await (await fetch('/api/fx/rate')).json(); state.fx = (r.status === 'available' || r.status === 'stale') && r.rate > 0 ? r : null; } catch {}
  renderCcy(); await load(); setInterval(load, 60000);
})();
})();
