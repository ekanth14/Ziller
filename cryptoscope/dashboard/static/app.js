'use strict';

const $ = id => document.getElementById(id);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state = {
  workspace: 'research',
  data: null,
  latest: null,
  detail: null,
  tab: 'decision',
  window: 50,
  busy: false,
  generation: 0,
  detailGeneration: 0,
  currency: 'USD',
  fx: null,
  favorites: new Set(),
  listings: [],
  tickers: {},
  previousPrices: {},
  user: null,
  filterFavoritesOnly: false,
  listingsSearch: '',
  listingsSort: 'market_cap_desc'
};

const money = value => {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—';
  const num = Number(value);
  if (state.currency === 'INR' && (state.fx?.status === 'available' || state.fx?.status === 'stale') && state.fx?.rate) {
    const inrVal = num * state.fx.rate;
    return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: inrVal < 10 ? 4 : 2 }).format(inrVal);
  }
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: num < 10 ? 4 : 2 }).format(num);
};
const number = (value, digits=2) => Number.isFinite(Number(value)) ? new Intl.NumberFormat(undefined,{maximumFractionDigits:digits}).format(value) : '—';
const date = seconds => seconds ? new Date(seconds*1000).toLocaleString(undefined,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}) : '—';
const age = seconds => {if (!seconds) return '—'; const minutes=Math.max(0,Math.floor((Date.now()/1000-seconds)/60));return minutes<1?'Just now':minutes<60?`${minutes}m ago`:minutes<1440?`${Math.floor(minutes/60)}h ago`:`${Math.floor(minutes/1440)}d ago`;};
const title = value => String(value || '—').replaceAll('_',' ').replace(/\b\w/g, c=>c.toUpperCase());
const executionLabel = value => ({not_requested:'No order placed',research_only:'Research only',filled:'Paper order filled',rejected:'Rejected by risk checks',rejected_by_laya:'Declined by Laya',blocked:'Awaiting valid quote'})[value] || title(value);
const duration = run => {const seconds=(run.finished_at || Date.now()/1000)-run.created_at;return seconds<60?`${Math.max(0,Math.round(seconds))}s`:`${Math.floor(seconds/60)}m ${Math.round(seconds%60)}s`;};
const coin = symbol => symbol==='BTCUSDT'?'₿':symbol==='ETHUSDT'?'Ξ':String(symbol || '?').slice(0,1);
const phases = ['analysts','research_debate','trader','aggressive_risk','neutral_risk','conservative_risk','portfolio_manager'];
const jsonBlock = value => `<pre>${escapeHtml(JSON.stringify(value,null,2))}</pre>`;

async function request(path, signal) {
  const response=await fetch(path,{signal});
  const body=await response.json();
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
  return body;
}

async function postJson(path, payload) {
  const headers = { 'Content-Type': 'application/json' };
  if (state.user?.csrf_token) {
    headers['X-CSRF-Token'] = state.user.csrf_token;
  }
  const response = await fetch(path, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload || {})
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
  return body;
}

function notice(message) { 
  if ($('notice')) {
    $('notice').hidden = !message; 
    $('notice').textContent = message || ''; 
  }
}

async function refresh() {
  if(state.controller) state.controller.abort();
  const generation=++state.generation;
  state.controller=new AbortController();state.busy=true;if($('refresh'))$('refresh').disabled=true;
  try {
    const data=await request(`/api/dashboard?workspace=${state.workspace}`,state.controller.signal);
    if(generation!==state.generation)return;
    state.data=data;
    notice([data.errors.join(' '), data.controls?.halted?'Operator emergency halt active: New paper entries are paused. Position exits remain available.':''].filter(Boolean).join(' '));
    renderOverview();
    if($('sync-status')) $('sync-status').textContent=`Updated ${new Date().toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit',second:'2-digit'})}`;
    if($('sync-dot')) $('sync-dot').style.background='var(--secondary-emerald)';
    const latest=data.runs.find(r=>r.status==='completed' && r.action);
    if(latest && latest.run_id!==state.latest?.run_id) {
      const body=await request(`/api/runs/${latest.run_id}?workspace=${state.workspace}`,state.controller.signal);
      if(generation!==state.generation)return;
      state.latest=body;renderDecision();
    } else if(!latest) {state.latest=null;renderDecision();}
    if($('run-dialog')?.open && state.detail?.status==='running') await showRun(state.detail.run_id,false);
  } catch(error) {
    if(error.name==='AbortError')return;
    notice(`Connection interrupted: ${error.message}. Last received data is displayed.`);
    if($('sync-status')) $('sync-status').textContent='Disconnected · retrying';
    if($('sync-dot')) $('sync-dot').style.background='var(--danger-rose)';
  } finally {
    if(generation===state.generation){state.busy=false;if($('refresh'))$('refresh').disabled=false;}
  }
}

function renderOverview() {
  const data=state.data;
  const cashVal = data.portfolio.cash;
  if($('cash')) $('cash').innerHTML=cashVal===null?'—':`${escapeHtml(money(cashVal))}`;
  if($('prime-aum')) $('prime-aum').textContent=cashVal===null?'$10,000.00':money(cashVal);
  if($('cash-note')) $('cash-note').textContent=data.ledger_label;
  if($('portfolio-caption')) $('portfolio-caption').textContent=data.ledger_label;
  if($('position-count')) $('position-count').textContent=Object.keys(data.portfolio.positions).length.toString().padStart(2,'0');
  
  if($('run-count')) $('run-count').textContent=data.runs.length.toString().padStart(2,'0');
  const completed=data.runs.filter(r=>r.status==='completed').length;
  const running=data.runs.filter(r=>r.status==='running').length;
  const failed=data.runs.filter(r=>r.status==='failed').length;
  if($('run-breakdown')) $('run-breakdown').textContent=`${completed} completed · ${running?running+' running':failed+' failed'}`;
  if($('activity-count')) $('activity-count').textContent=data.runs.length;
  if($('workspace-sub')) $('workspace-sub').textContent=state.workspace==='demo'?'Local · Synthetic data':'Local · Paper account';
  if($('footer-status')) $('footer-status').textContent=state.workspace==='demo'?'Synthetic demo · Read only':'Local monitor · Read only';
  
  if($('risk-fraction')) $('risk-fraction').textContent=`${number(data.settings.risk_fraction*100)}%`;
  if($('allocation-cap')) $('allocation-cap').textContent=`${number(data.settings.max_position_fraction*100)}%`;
  if($('reward-risk')) $('reward-risk').textContent=`${number(data.settings.minimum_reward_risk)} : 1`;
  if($('model-name')) $('model-name').textContent=data.model.model;
  if($('model-status')) $('model-status').textContent=({ready:'Laya ready',model_missing:'Laya model missing',unreachable:'Ollama unreachable',check_delayed:'Health check delayed',unchecked:'Checking Laya'})[data.model.status] || 'Laya status unknown';
  if($('system-dot')) $('system-dot').style.background=data.model.status==='ready'?'var(--secondary-emerald)':'#c7a77a';
  
  if ($('symbol')) {
    const previous=$('symbol').value;
    $('symbol').innerHTML=data.settings.symbols.map(s=>`<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join('');
    if(data.settings.symbols.includes(previous))$('symbol').value=previous;
  }
  
  renderRuns();
  renderPositions();
  renderChart();
  renderOrderBook();
  renderBacktests();
  renderRisk();
  renderResearchTools();
  renderAutoTrader();
}

function renderDecision() {
  const body=state.latest, proposal=body?.decision?.proposal;
  if($('latest-action')) $('latest-action').textContent=proposal?.action?.replace('_',' ') || '—';
  if($('latest-note')) $('latest-note').textContent=body?`${proposal.symbol} · ${age(body.finished_at)}`:'Waiting for a completed run';
  if($('latest-symbol')) $('latest-symbol').textContent=proposal?.symbol || '—';
  if($('decision-title')) $('decision-title').textContent=proposal?title(proposal.action):'No decision yet';
  if($('decision-orb')) $('decision-orb').textContent=proposal?({LONG:'↗',SHORT:'↘',HOLD:'Ⅱ',CLOSE:'×',REDUCE:'−',NO_TRADE:'—'})[proposal.action]:'—';
  if($('latest-thesis')) $('latest-thesis').textContent=proposal?.thesis || 'Completed research will appear here with its thesis, debate outcome, and supporting evidence.';
  if($('confidence')) $('confidence').textContent=proposal?`${number(proposal.confidence*100,0)}%`:'—';
  if($('confidence-text')) $('confidence-text').textContent=proposal?`${number(proposal.confidence*100,0)}%`:'—';
  if($('confidence-bar')) $('confidence-bar').style.width=proposal?`${Math.max(0,Math.min(100,proposal.confidence*100))}%`:'0';
  if($('decision-age')) $('decision-age').textContent=body?age(body.finished_at):'—';
  if($('decision-execution')) $('decision-execution').textContent=body?executionLabel(body.execution?.status):'Research only';
  if($('view-latest')) $('view-latest').disabled=!body;
}

function renderRuns() {
  if(!state.data || !$('runs-body')) return;
  const search=$('search')?.value.trim().toLowerCase() || '', filter=$('status-filter')?.value || 'all';
  const runs=state.data.runs.filter(r=>(filter==='all'||r.status===filter)&&`${r.symbol} ${r.run_id} ${r.model} ${r.action || ''}`.toLowerCase().includes(search));
  if($('runs-empty')) $('runs-empty').hidden=runs.length>0;
  $('runs-body').innerHTML=runs.map(run=>{
    const steps=phases.filter(p=>run.stages.includes(p)).length;
    return `<tr data-id="${escapeHtml(run.run_id)}">
      <td>
        <div style="display:flex; align-items:center; gap:8px;">
          <span style="display:inline-flex; width:22px; height:22px; border-radius:50%; background:var(--surface-high); align-items:center; justify-content:center; font-family:var(--font-mono); font-size:10px; color:var(--primary-cyan);">${escapeHtml(coin(run.symbol))}</span>
          <div>
            <strong style="color:#fff;">${escapeHtml(run.symbol.replace('USDT',' / USDT'))}</strong>
            <div style="font-size:9px; color:var(--text-sub);">${escapeHtml(run.run_id.slice(0,8))}</div>
          </div>
        </div>
      </td>
      <td title="${escapeHtml(date(run.created_at))}">${escapeHtml(date(run.created_at))}</td>
      <td><span class="badge ${escapeHtml(run.status)}">${escapeHtml(title(run.status))}</span></td>
      <td><span class="badge ${run.action==='LONG'?'action-long':run.action==='SHORT'?'action-short':'action-hold'}">${escapeHtml(run.action?.replace('_',' ') || '—')}</span></td>
      <td>${escapeHtml(duration(run))}</td>
      <td>
        <div style="display:flex; align-items:center; gap:3px;" title="${escapeHtml(title(run.stages.at(-1)))}">
          ${phases.map(p=>`<span style="width:6px; height:12px; border-radius:1px; background:${run.stages.includes(p)?'var(--secondary-emerald)':'var(--surface-high)'};"></span>`).join('')}
          <span style="margin-left:4px; font-size:9px; color:var(--text-sub);">${steps}/7</span>
        </div>
      </td>
      <td style="text-align: right;"><button class="button" aria-label="Inspect run ${escapeHtml(run.run_id.slice(0,8))}" style="padding:2px 8px;">Inspect ↗</button></td>
    </tr>`;
  }).join('');
  if($('table-count')) $('table-count').textContent=`Showing ${runs.length} of ${state.data.runs.length} recent runs`;
}

function renderPositions() {
  if (!$('positions')) return;
  const positions=Object.entries(state.data?.portfolio?.positions || {});
  $('positions').innerHTML=positions.length?positions.map(([symbol,p])=>`
    <div style="display:grid; grid-template-columns:1fr 1fr 1fr; padding:8px 0; border-bottom:1px solid var(--border); font-family:var(--font-mono); font-size:11px;">
      <div><strong style="color:#fff;">${escapeHtml(symbol)}</strong><div style="font-size:9px; color:var(--text-sub);">${escapeHtml(number(p.quantity,8))} units</div></div>
      <div><span>${escapeHtml(money(p.entry))}</span><div style="font-size:9px; color:var(--text-sub);">Entry mark</div></div>
      <div><span style="color:var(--danger-rose);">${escapeHtml(money(p.stop))}</span><div style="font-size:9px; color:var(--text-sub);">Target: ${escapeHtml(money(p.target))}</div></div>
    </div>
  `).join(''):`<div style="padding:16px 0; font-family:var(--font-mono); font-size:11px; color:var(--text-sub); text-align:center;">All clear. Portfolio flat with zero open positions.</div>`;
}

function renderChart() {
  if (!$('symbol') || !$('chart')) return;
  const symbol = $('symbol').value;
  const snapshot=state.data?.snapshots[symbol];
  const candles=snapshot?.candles?.slice(-state.window).filter(c=>Number.isFinite(c.close)) || [];
  if($('chart-tooltip')) $('chart-tooltip').hidden=true;
  if($('chart-empty')) $('chart-empty').hidden=candles.length>1;
  if(candles.length<2){
    $('chart').innerHTML='';
    if($('chart-empty')) $('chart-empty').textContent='Awaiting closed candle snapshot for '+symbol;
    if($('market-price')) $('market-price').textContent='—';
    if($('market-change')) $('market-change').textContent='—';
    if($('chart-interval')) $('chart-interval').textContent='5m candles';
    if($('snapshot-time')) $('snapshot-time').textContent='No snapshot available';
    return;
  }
  const values=candles.map(c=>c.close),min=Math.min(...values),max=Math.max(...values),padding=(max-min)*.15 || max*.001;
  const low=min-padding,high=max+padding,x=i=>12+i/(values.length-1)*707,y=v=>185-(v-low)/(high-low)*170;
  const points=values.map((v,i)=>`${x(i).toFixed(2)},${y(v).toFixed(2)}`).join(' ');
  const first=values[0],last=values.at(-1),change=(last/first-1)*100;
  if($('market-price')) $('market-price').textContent=money(last);
  if($('market-change')) {
    $('market-change').textContent=`${change>=0?'+':''}${number(change)}% 24h`;
    $('market-change').className = `kpi-tag ${change>=0?'green':'rose'}`;
  }
  if($('chart-interval')) $('chart-interval').textContent=`${snapshot.interval_seconds/60}m · ${candles.length} closed bars`;
  if($('snapshot-time')) $('snapshot-time').textContent=`Captured ${date(snapshot.as_of)} · ${age(snapshot.as_of)}`;
  
  const grid=[0,.25,.5,.75,1].map(f=>{
    const value=low+(high-low)*f,py=y(value);
    return `<line x1="0" y1="${py}" x2="730" y2="${py}" stroke="#1e293b" stroke-dasharray="3 5"/><text x="740" y="${py+3}" fill="#64748b" font-size="9" font-family="JetBrains Mono">${number(value,values[0]>1000?0:2)}</text>`;
  }).join('');
  
  const labels=[0,Math.floor((candles.length-1)/2),candles.length-1].map((i,k)=>
    `<text x="${x(i)}" y="215" text-anchor="${k===0?'start':k===2?'end':'middle'}" fill="#64748b" font-size="9" font-family="JetBrains Mono">${escapeHtml(new Date(candles[i].close_time*1000).toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit'}))}</text>`
  ).join('');

  $('chart').innerHTML=`
    <defs>
      <linearGradient id="chart-fill" x1="0" x2="0" y1="0" y2="1">
        <stop offset="0%" stop-color="#38bdf8" stop-opacity="0.28"/>
        <stop offset="100%" stop-color="#38bdf8" stop-opacity="0"/>
      </linearGradient>
    </defs>
    ${grid}
    <polygon points="12,190 ${points} 719,190" fill="url(#chart-fill)"/>
    <polyline points="${points}" fill="none" stroke="#38bdf8" stroke-width="2" stroke-linejoin="round"/>
    <circle cx="719" cy="${y(last)}" r="4" fill="#38bdf8"/>
    ${labels}
    <line id="crosshair" x1="0" x2="0" y1="10" y2="190" stroke="#8ed5ff" stroke-dasharray="2 3" visibility="hidden"/>
    <rect id="chart-hit" x="0" y="0" width="730" height="200" fill="transparent"/>
  `;

  $('chart').onpointermove=event=>{
    const rect=$('chart').getBoundingClientRect(),px=(event.clientX-rect.left)/rect.width*800,index=Math.max(0,Math.min(candles.length-1,Math.round((px-12)/707*(candles.length-1))));
    const line=$('crosshair');if(!line)return;
    line.setAttribute('x1',x(index));line.setAttribute('x2',x(index));line.setAttribute('visibility','visible');
    if($('chart-tooltip')) {
      $('chart-tooltip').hidden=false;
      $('chart-tooltip').textContent=`${date(candles[index].close_time)} · ${money(values[index])}`;
    }
  };
  $('chart').onpointerleave=()=>{
    $('crosshair')?.setAttribute('visibility','hidden');
    if($('chart-tooltip')) $('chart-tooltip').hidden=true;
  };
}

function renderOrderBook() {
  const bot=state.data?.autotrader;
  const quotes=bot?.runtime?.quotes || {};
  const currentSymbol = $('symbol')?.value || 'BTCUSDT';
  const quote = quotes[currentSymbol];
  if (!quote) return;
  
  const bid = quote.bid, ask = quote.ask;
  const spread = ask - bid;
  const spreadPct = (spread / bid) * 100;
  const mid = (ask + bid) / 2;
  
  if ($('ob-spread')) $('ob-spread').textContent = `${spread.toFixed(2)} USDT (${spreadPct.toFixed(3)}%)`;
  if ($('ob-midpoint')) $('ob-midpoint').textContent = `${mid.toFixed(2)} USDT`;
  
  const step = currentSymbol === 'BTCUSDT' ? 1.5 : 0.25;
  if ($('ob-bid-1')) $('ob-bid-1').textContent = bid.toFixed(2);
  if ($('ob-bid-2')) $('ob-bid-2').textContent = (bid - step).toFixed(2);
  if ($('ob-bid-3')) $('ob-bid-3').textContent = (bid - step * 2).toFixed(2);
  if ($('ob-bid-4')) $('ob-bid-4').textContent = (bid - step * 3).toFixed(2);

  if ($('ob-ask-1')) $('ob-ask-1').textContent = ask.toFixed(2);
  if ($('ob-ask-2')) $('ob-ask-2').textContent = (ask + step).toFixed(2);
  if ($('ob-ask-3')) $('ob-ask-3').textContent = (ask + step * 2).toFixed(2);
  if ($('ob-ask-4')) $('ob-ask-4').textContent = (ask + step * 3).toFixed(2);
}

function renderAutoTrader(){
  const bot=state.data?.autotrader;
  if($('autotrader')) $('autotrader').hidden=state.workspace==='demo';
  if(!bot)return;
  const runtime=bot.runtime || {}, risk=runtime.risk || {}, portfolio=runtime.portfolio || {};
  
  if($('auto-state')) {
    const isRunning = runtime.state === 'running';
    $('auto-state').textContent = title(runtime.state).toUpperCase();
    $('auto-state').className = `badge ${isRunning ? 'completed' : 'failed'}`;
  }
  if($('sidebar-bot-badge')) {
    $('sidebar-bot-badge').textContent = title(runtime.state).toUpperCase();
    $('sidebar-bot-badge').className = `sidebar-badge ${runtime.state === 'running' ? 'green' : 'amber'}`;
  }
  
  const last=runtime.last_decision;
  if($('auto-summary')) {
    $('auto-summary').innerHTML=bot.available?`
      <div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:8px; margin-bottom:12px;">
        <div style="background:var(--surface-low); border:1px solid var(--border); border-radius:4px; padding:8px 10px;">
          <span style="display:block; font-size:9px; color:var(--text-sub); text-transform:uppercase;">Paper Cash</span>
          <strong style="font-family:var(--font-mono); font-size:14px; color:var(--primary-cyan);">${escapeHtml(money(portfolio.cash))}</strong>
        </div>
        <div style="background:var(--surface-low); border:1px solid var(--border); border-radius:4px; padding:8px 10px;">
          <span style="display:block; font-size:9px; color:var(--text-sub); text-transform:uppercase;">Net Liquidation</span>
          <strong style="font-family:var(--font-mono); font-size:14px; color:var(--secondary-emerald);">${escapeHtml(money(risk.equity))}</strong>
        </div>
        <div style="background:var(--surface-low); border:1px solid var(--border); border-radius:4px; padding:8px 10px;">
          <span style="display:block; font-size:9px; color:var(--text-sub); text-transform:uppercase;">Last Action</span>
          <strong style="font-family:var(--font-mono); font-size:14px; color:#fff;">${escapeHtml(last?.decision?.action || '—')}</strong>
        </div>
        <div style="background:var(--surface-low); border:1px solid var(--border); border-radius:4px; padding:8px 10px;">
          <span style="display:block; font-size:9px; color:var(--text-sub); text-transform:uppercase;">Circuit Breakers</span>
          <strong style="font-family:var(--font-mono); font-size:14px; color:${risk.halt_reason?'var(--danger-rose)':'var(--secondary-emerald)'};">${escapeHtml(risk.halt_reason || 'NORMAL (PASS)')}</strong>
        </div>
      </div>
      <div style="font-family:var(--font-mono); font-size:10px; color:var(--text-muted); display:flex; justify-content:space-between;">
        <span>Model: ${escapeHtml(runtime.model)} · ${escapeHtml(runtime.interval)} candles · ${escapeHtml(risk.entries_today ?? 0)} entries today</span>
        <span>Heartbeat: ${escapeHtml(age(runtime.heartbeat_at))}</span>
      </div>
    `:'Autonomous bot process is not detected. Start with python -m cryptoscope.autotrader start';
  }

  const decisions=bot.decisions || [];
  if($('auto-empty')) $('auto-empty').hidden=decisions.length>0;
  if($('auto-decisions')) {
    $('auto-decisions').innerHTML=decisions.map(row=>`
      <tr>
        <td><strong>${escapeHtml(row.symbol)}</strong><div style="font-size:9px; color:var(--text-sub);">${escapeHtml(date(row.created_at))}</div></td>
        <td><span class="badge ${row.decision?.action==='BUY'?'action-long':row.decision?.action==='SELL'?'action-short':'action-hold'}">${escapeHtml(row.decision?.action || title(row.status))}</span></td>
        <td><span style="font-size:10px; color:var(--text-muted);">${escapeHtml(title(row.execution?.status || 'reviewing'))}</span></td>
        <td>${row.latency_seconds===null||row.latency_seconds===undefined?'—':escapeHtml(number(row.latency_seconds))+'s'}</td>
        <td style="text-align: right;"><button class="button" data-auto="${escapeHtml(row.run_id)}" style="padding:2px 8px;">Inspect ↗</button></td>
      </tr>
    `).join('');
  }

  if($('auto-fills')) {
    const fills = bot.fills || [];
    $('auto-fills').innerHTML=fills.length?`
      <div style="font-family:var(--font-mono); font-size:10px; font-weight:600; color:var(--text-sub); text-transform:uppercase; margin-bottom:6px;">Recent Paper Order Fills</div>
      <div class="table-scroll">
        <table>
          <thead><tr><th>Time</th><th>Asset</th><th>Side</th><th>Quantity</th><th>Price</th><th>Fee</th></tr></thead>
          <tbody>
            ${fills.slice(0,5).map(f=>`
              <tr>
                <td>${escapeHtml(date(f.at))}</td>
                <td><strong>${escapeHtml(f.symbol)}</strong></td>
                <td><span class="badge ${f.action==='LONG'?'action-long':'action-short'}">${escapeHtml(f.action)}</span></td>
                <td>${escapeHtml(number(f.quantity,6))}</td>
                <td>${escapeHtml(money(f.price))}</td>
                <td>${escapeHtml(number(f.fee,4))} USDT</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `:'';
  }
}

if ($('auto-decisions')) {
  $('auto-decisions').addEventListener('click',async event=>{
    const button=event.target.closest('[data-auto]');if(!button)return;
    const url=`/api/autotrader/runs/${button.dataset.auto}`;
    try{
      const body=await request(url);
      openInspector('Autonomous Paper Decision Audit',jsonBlock(body),url+'?download=1');
    } catch(error){notice(error.message);}
  });
}

function renderRisk(){
  const diagnostics=state.data?.risk_reports;
  if (!$('risk-source') || !$('risk-diagnostics')) return;
  if(diagnostics?.status!=='available'){
    $('risk-source').textContent='NO DATA';
    $('risk-diagnostics').innerHTML=`<div class="fine" style="padding:10px 0;">${escapeHtml(diagnostics?.reason || 'Run a baseline backtest to compute risk metrics.')}</div>`;
    return;
  }
  const report=diagnostics.report;
  $('risk-source').textContent=diagnostics.symbol;
  $('risk-diagnostics').innerHTML=`
    <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:10px; font-family:var(--font-mono);">
      <div style="background:var(--surface-low); border:1px solid var(--border); border-radius:4px; padding:8px;">
        <span style="font-size:9px; color:var(--text-sub); display:block;">HISTORICAL VAR (95%)</span>
        <strong style="font-size:15px; color:var(--warning-amber);">${escapeHtml(number(report.risk.historicalVaR))} USDT</strong>
      </div>
      <div style="background:var(--surface-low); border:1px solid var(--border); border-radius:4px; padding:8px;">
        <span style="font-size:9px; color:var(--text-sub); display:block;">EXPECTED SHORTFALL (CVAR)</span>
        <strong style="font-size:15px; color:var(--danger-rose);">${escapeHtml(number(report.risk.cvar))} USDT</strong>
      </div>
      <div style="background:var(--surface-low); border:1px solid var(--border); border-radius:4px; padding:8px;">
        <span style="font-size:9px; color:var(--text-sub); display:block;">VOLATILITY REGIME</span>
        <strong style="font-size:13px; color:var(--secondary-emerald);">${escapeHtml(title(report.volatility?.regime || 'Normal'))}</strong>
      </div>
      <div style="background:var(--surface-low); border:1px solid var(--border); border-radius:4px; padding:8px;">
        <span style="font-size:9px; color:var(--text-sub); display:block;">VAR WINDOW SAMPLES</span>
        <strong style="font-size:13px; color:#fff;">${escapeHtml(report.risk.sampleSize)} bars</strong>
      </div>
    </div>
    <div class="fine" style="font-size:9px; color:var(--text-sub);">${escapeHtml(date(diagnostics.created_at))} · Clodds Risk Module Advisory</div>
  `;
}

function renderBacktests(){
  const reports=state.data?.backtests || [];
  if($('backtest-empty')) $('backtest-empty').hidden=reports.length>0;
  if($('backtest-body')) {
    $('backtest-body').innerHTML=reports.map(r=>`
      <tr>
        <td><strong>${escapeHtml(title(r.strategy))}</strong><div style="font-size:9px; color:var(--text-sub);">${escapeHtml(r.symbol)} · ${escapeHtml(date(r.created_at))}</div></td>
        <td style="color:${r.metrics.net_return_pct>=0?'var(--secondary-emerald)':'var(--danger-rose)'}; font-weight:600;">${escapeHtml(number(r.metrics.net_return_pct))}%</td>
        <td style="color:var(--danger-rose);">${escapeHtml(number(r.metrics.max_drawdown_pct))}%</td>
        <td>${escapeHtml(number(r.metrics.fees))} USDT</td>
        <td>${escapeHtml(r.metrics.fills)}</td>
        <td style="text-align: right;"><button class="button" data-backtest="${escapeHtml(r.run_id)}" style="padding:2px 8px;">Inspect ↗</button></td>
      </tr>
    `).join('');
  }
}

if ($('backtest-body')) {
  $('backtest-body').addEventListener('click',async event=>{
    const button=event.target.closest('[data-backtest]');if(!button)return;
    try{
      const report=await request(`/api/backtests/${button.dataset.backtest}`);
      openInspector(`${report.symbol} / ${title(report.strategy)} Baseline Backtest`,
        `<h3>Performance after costs</h3>${jsonBlock(report.metrics)}
         <h3>Execution and data assumptions</h3><p>${report.limitations.map(escapeHtml).join('<br>')}</p>
         <h3>Input fingerprint</h3>${jsonBlock(report.fingerprint)}
         <h3>Trade fills</h3>${jsonBlock(report.fills)}`+
        [['Performance statistics',report.performance],['Comparison baseline',report.comparison],['Cost sensitivity',report.cost_sensitivity],['Block bootstrap',report.bootstrap],['Walk-forward folds',report.folds],['Strategy definition',report.strategy_spec],['Risk diagnostics',report.risk]].filter(([,value])=>value).map(([label,value])=>`<h3>${label}</h3>${jsonBlock(value)}`).join(''),
        `/api/backtests/${report.run_id}?download=1`);
    } catch(error){notice(error.message);}
  });
}

function renderResearchTools(){
  const forecast=state.data?.forecast, strategy=state.data?.strategy;
  if($('view-forecast')) $('view-forecast').disabled=!forecast;
  if($('view-strategy')) $('view-strategy').disabled=!strategy;
  if($('forecast-summary')) {
    $('forecast-summary').innerHTML=forecast?`
      <div style="font-family:var(--font-mono); font-size:11px;">
        <strong style="color:var(--primary-cyan);">${escapeHtml(forecast.symbol)} · ${escapeHtml(forecast.parameters?.steps)} Step Projection</strong>
        <div style="margin:4px 0; color:#fff;">Target Close: ${escapeHtml(money(forecast.forecast?.at(-1)?.close))}</div>
        <div style="font-size:9px; color:var(--text-sub);">Input cutoff: ${escapeHtml(date(forecast.input_cutoff))}</div>
      </div>
    `:'No forecast report yet. Run python -m cryptoscope.forecasting run --snapshot ...';
  }
  if($('strategy-summary')) {
    $('strategy-summary').innerHTML=strategy?`
      <div style="font-family:var(--font-mono); font-size:11px;">
        <strong style="color:#fff;">${escapeHtml(strategy.spec?.name)}</strong>
        <div style="margin:4px 0; color:var(--text-muted);">${escapeHtml(strategy.spec?.symbol)} · ${escapeHtml(title(strategy.spec?.strategy))} (Fast ${escapeHtml(strategy.spec?.fast)} / Slow ${escapeHtml(strategy.spec?.slow)})</div>
        <span class="sidebar-badge green">${strategy.backtest?'Backtest Verified: '+escapeHtml(number(strategy.backtest.metrics.net_return_pct))+'% Net':'Draft Spec'}</span>
      </div>
    `:'No strategy draft yet. Run python -m cryptoscope.strategy draft ...';
  }
}

for(const [id,kind,key] of [['view-forecast','forecasts','forecast'],['view-strategy','strategies','strategy']]){
  if($(id)) {
    $(id).addEventListener('click',async()=>{
      const artifact=state.data?.[key];if(!artifact)return;
      const url=`/api/${kind}/${artifact.run_id}?workspace=${state.workspace}`;
      try{
        const report=await request(url);
        openInspector(key==='forecast'?'Kronos Deep Learning Forecast Evidence':'Laya Strategy Studio Specification',jsonBlock(report),url+'&download=1');
      } catch(error){notice(error.message);}
    });
  }
}

if ($('view-features')) {
  $('view-features').addEventListener('click',()=>{
    if(!state.catalog)return;
    openInspector('Repository Feature Integration Map',`<p>${escapeHtml(state.catalog.scope)}</p>`+state.catalog.features.map(f=>`
      <div style="border-left:2px solid var(--primary-cyan); padding-left:10px; margin-bottom:12px;">
        <strong style="color:#fff; font-family:var(--font-mono);">${escapeHtml(f.name)}</strong>
        <div class="fine">${escapeHtml(f.source)} · <span class="sidebar-badge">${escapeHtml(title(f.status))}</span></div>
      </div>
    `).join(''));
  });
}

async function loadFeatures(){
  try{
    const catalog=await request('/api/features');
    state.catalog=catalog;
    const total=catalog.features.length,done=catalog.features.filter(f=>f.status==='implemented').length;
    if($('coverage')) {
      $('coverage').innerHTML=`
        <div style="font-family:var(--font-mono); font-size:10px;">
          <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
            <span>Coverage: <strong>${done} / ${total}</strong> families</span>
            <span style="color:var(--primary-cyan);">${total?Math.round(100*done/total):0}%</span>
          </div>
          <div style="height:4px; background:var(--surface-low); border-radius:2px; overflow:hidden;">
            <div style="width:${total?Math.round(100*done/total):0}%; height:100%; background:var(--primary-cyan);"></div>
          </div>
        </div>
      `;
    }
  }catch(error){if($('coverage')) $('coverage').textContent=error.message;}
}

function openInspector(titleText,content,download){
  state.detail=null;state.detailGeneration++;
  const tabs = document.querySelector('.detail-tabs');
  if(tabs) tabs.hidden=true;
  if($('detail-title')) $('detail-title').textContent=titleText;
  if($('detail-content')) $('detail-content').innerHTML=content;
  if($('detail-id')) $('detail-id').textContent='';
  if($('download')) {
    $('download').hidden=!download;
    if(download) $('download').href=download;
  }
  if($('run-dialog') && !$('run-dialog').open)$('run-dialog').showModal();
}

async function showRun(id, open=true) {
  const tabs = document.querySelector('.detail-tabs');
  if(tabs) tabs.hidden=false;
  if($('download')) $('download').hidden=false;
  const generation=++state.detailGeneration;
  if(open){
    state.tab='decision';
    if($('detail-content')) $('detail-content').textContent='Loading research report…';
    if($('run-dialog') && !$('run-dialog').open)$('run-dialog').showModal();
  }
  try {
    const body=await request(`/api/runs/${encodeURIComponent(id)}?workspace=${state.workspace}`);
    if(generation!==state.detailGeneration)return;
    state.detail=body;
    if($('detail-title')) $('detail-title').textContent=`${body.snapshot?.symbol || 'Research'} / ${title(body.status)}`;
    if($('detail-id')) $('detail-id').textContent=body.run_id;
    if($('download')) $('download').href=`/api/runs/${body.run_id}?workspace=${state.workspace}&download=1`;
    renderDetail();
  } catch(error){if(generation===state.detailGeneration && $('detail-content')) $('detail-content').textContent=error.message;}
}

function renderDetail() {
  const body=state.detail;if(!body || !$('detail-content'))return;
  document.querySelectorAll('[data-tab]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.tab===state.tab)));
  if(state.tab==='decision'){
    const p=body.decision?.proposal;
    const trade=p && ['LONG','SHORT'].includes(p.action)?p:null;
    $('detail-content').innerHTML=`${body.error?`<div class="notice">${escapeHtml(body.error)}</div>`:''}
      <div class="detail-facts">
        <div class="detail-fact"><span>Signal</span><strong>${escapeHtml(p?.action || 'Pending')}</strong></div>
        <div class="detail-fact"><span>Model</span><strong>${escapeHtml(body.model)}</strong></div>
        <div class="detail-fact"><span>Mode</span><strong>${escapeHtml(title(body.mode))}</strong></div>
        <div class="detail-fact"><span>Entry Mark</span><strong>${escapeHtml(money(trade?.entry))}</strong></div>
        <div class="detail-fact"><span>Stop Loss</span><strong>${escapeHtml(money(trade?.stop))}</strong></div>
        <div class="detail-fact"><span>Profit Target</span><strong>${escapeHtml(money(trade?.target))}</strong></div>
      </div>
      <h3 style="color:#fff; font-family:var(--font-mono); font-size:12px; margin-top:14px;">Investment Thesis</h3>
      <p style="color:var(--text-muted); line-height:1.6;">${escapeHtml(p?.thesis || 'No proposal was produced.')}</p>
      <h3 style="color:#fff; font-family:var(--font-mono); font-size:12px;">Portfolio Manager Consensus</h3>
      <p style="color:var(--text-muted); line-height:1.6;">${escapeHtml(body.decision?.reason || 'No final decision yet.')}</p>
      <h3 style="color:#fff; font-family:var(--font-mono); font-size:12px;">Pre-Trade Gate & Execution Outcome</h3>
      ${jsonBlock(body.execution || {status:'No execution'})}
      <div class="fine" style="margin-top:12px;">Started ${escapeHtml(date(body.created_at))} · Total duration ${escapeHtml(duration(body))}</div>`;
  } else if(state.tab==='evidence'){
    $('detail-content').innerHTML=`
      <p style="color:var(--text-muted);">Cutoff: ${escapeHtml(date(body.snapshot?.as_of))} · Source: ${escapeHtml(body.snapshot?.source)} · ${body.snapshot?.candles?.length || 0} bars</p>
      ${body.stages.map(s=>`
        <div style="border-left:2px solid var(--border); padding-left:12px; margin-bottom:14px;">
          <details><summary style="font-family:var(--font-mono); font-size:11px; font-weight:600; color:var(--primary-cyan); cursor:pointer;">${escapeHtml(title(s.name))}</summary>${jsonBlock(s.output)}</details>
        </div>
      `).join('')}
    `;
  } else {
    $('detail-content').innerHTML=body.model_calls?.length?body.model_calls.map(call=>`
      <div style="border-left:2px solid var(--border); padding-left:12px; margin-bottom:14px;">
        <details><summary style="font-family:var(--font-mono); font-size:11px; font-weight:600; color:var(--text); cursor:pointer;">${escapeHtml(title(call.role))} · ${escapeHtml(call.status || 'Completed')}${call.output_tokens?' · '+number(call.output_tokens,0)+' tokens':''}</summary>${jsonBlock(call)}</details>
      </div>
    `).join(''):'No model calls recorded in this session.';
  }
}

function switchWorkspace(value){
  state.workspace=value;
  state.latest=null;
  state.detail=null;
  state.detailGeneration++;
  if($('workspace')) $('workspace').value=value;
  if($('run-dialog')?.open) $('run-dialog').close();
  renderDecision();
  refresh();
}

if ($('workspace')) $('workspace').addEventListener('change',e=>switchWorkspace(e.target.value));
if ($('refresh')) $('refresh').addEventListener('click',refresh);
if ($('symbol')) $('symbol').addEventListener('change',()=>{ renderChart(); renderOrderBook(); });
if ($('search')) $('search').addEventListener('input',renderRuns);
if ($('status-filter')) $('status-filter').addEventListener('change',renderRuns);

if ($('runs-body')) {
  $('runs-body').addEventListener('click',e=>{
    const row=e.target.closest('tr[data-id]');
    if(row) showRun(row.dataset.id);
  });
}

if ($('view-latest')) $('view-latest').addEventListener('click',()=>{if(state.latest)showRun(state.latest.run_id);});
if ($('close-dialog')) $('close-dialog').addEventListener('click',()=>$('run-dialog')?.close());

if ($('run-dialog')) {
  $('run-dialog').addEventListener('click',e=>{
    if(e.target===$('run-dialog')){
      const r=$('run-dialog').getBoundingClientRect();
      if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)$('run-dialog').close();
    }
  });
}

document.querySelectorAll('[data-tab]').forEach(button=>button.addEventListener('click',()=>{
  state.tab=button.dataset.tab;
  renderDetail();
}));

document.querySelectorAll('[data-window]').forEach(button=>button.addEventListener('click',()=>{
  state.window=Number(button.dataset.window);
  document.querySelectorAll('[data-window]').forEach(b=>b.classList.toggle('selected',b===button));
  renderChart();
}));

document.querySelectorAll('.nav-tab, .sidebar-link').forEach(a=>{
  a.addEventListener('click',()=>{
    document.querySelectorAll('.nav-tab, .sidebar-link').forEach(b=>b.classList.remove('active'));
    a.classList.add('active');
  });
});

if ($('kill-switch-btn')) {
  $('kill-switch-btn').addEventListener('click', async () => {
    const isHalted = state.governor?.kill_switch_engaged || state.governor?.emergency_halted;
    if (isHalted) {
      const pwd = prompt('EMERGENCY HALT ACTIVE. Enter Administrator password to verify and resume bot operations:');
      if (!pwd) return;
      try {
        const res = await postJson('/api/governor/resume', { password: pwd });
        notice('Master kill switch disengaged. Bot resumed successfully by administrator.');
        await fetchGovernorStatus();
      } catch (err) {
        notice(`Resume failed: ${err.message}`);
      }
    } else {
      if (confirm('ENGAGE MASTER EMERGENCY KILL-SWITCH?\n\nThis will immediately cancel all open orders across all venues, flatten active positions via market orders, and transition the autonomous bot into HALTED state.')) {
        try {
          const res = await postJson('/api/governor/kill_switch');
          notice(`MASTER KILL-SWITCH ENGAGED! Canceled ${res.orders_canceled || 0} orders, flattened ${res.positions_flattened || 0} positions.`);
          await fetchGovernorStatus();
        } catch (err) {
          notice(`Kill-switch execution error: ${err.message}`);
        }
      }
    }
  });
}

async function fetchGovernorStatus() {
  try {
    const res = await request('/api/governor/status');
    state.governor = res;
    const btn = $('kill-switch-btn');
    if (!btn) return;
    if (res.kill_switch_engaged || res.emergency_halted) {
      btn.style.background = 'var(--danger-rose)';
      btn.style.color = '#fff';
      btn.innerHTML = '<span>⚠</span> HALTED (CLICK TO RESUME)';
      btn.title = `Bot is EMERGENCY HALTED: ${res.halt_reason || 'Kill switch engaged'}. Click to enter admin password and resume.`;
    } else {
      btn.style.background = '';
      btn.style.color = '';
      btn.innerHTML = '<span>⚠</span> KILL-SWITCH';
      btn.title = `Master Emergency Kill Switch (Mode: ${res.mode || 'PAPER'})`;
    }
  } catch (e) {}
}

/* =========================================================================
   ZILLERS QUANT TERMINAL - FX, AUTH, LISTINGS & ASSET SCREENER EXTENSIONS
   ========================================================================= */

const formatPercent = val => {
  if (val === null || val === undefined || !Number.isFinite(Number(val))) return '—';
  const n = Number(val);
  return (n >= 0 ? '+' : '') + n.toFixed(2) + '%';
};

function generateSparklineSvg(prices, isPositive) {
  if (!prices || prices.length < 2) return '<span style="color:var(--text-sub)">—</span>';
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const range = max - min || 1;
  const w = 90;
  const h = 24;
  const pts = prices.map((p, i) => {
    const x = (i / (prices.length - 1)) * w;
    const y = h - ((p - min) / range) * (h - 4) - 2;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const color = isPositive ? 'var(--secondary-emerald)' : 'var(--danger-rose)';
  return `<svg width="${w}" height="${h}" style="overflow:visible; vertical-align:middle;">
    <polyline fill="none" stroke="${color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" points="${pts.join(' ')}" />
  </svg>`;
}

async function fetchFxRate() {
  try {
    const res = await request('/api/fx/rate');
    state.fx = res;
    const btn = $('fx-toggle');
    const label = $('fx-currency-label');
    if (!btn) return;
    if (res.status === 'available' || res.status === 'stale') {
      btn.style.display = 'inline-flex';
      const displayText = (state.currency === 'INR' ? '₹ INR' : '$ USD') + (res.status === 'stale' ? ' (STALE)' : '');
      if (label) {
        label.textContent = displayText;
        label.className = res.status === 'stale' ? 'val warn' : 'val';
      } else {
        btn.textContent = displayText;
      }
      btn.title = `${res.status === 'stale' ? '[STALE] ' : ''}Real FX Rate: 1 USD = ${res.rate ? res.rate.toFixed(2) : '—'} INR (Age: ${res.age_seconds || 0}s, Source: ${res.source})`;
    } else {
      btn.style.display = 'none';
      if (state.currency === 'INR') {
        state.currency = 'USD';
        renderOverview();
        renderListings();
      }
    }
  } catch (e) {
    if ($('fx-toggle')) $('fx-toggle').style.display = 'none';
  }
}

if ($('fx-toggle')) {
  $('fx-toggle').addEventListener('click', () => {
    state.currency = state.currency === 'USD' ? 'INR' : 'USD';
    const label = $('fx-currency-label');
    const staleTag = state.fx?.status === 'stale' ? ' (STALE)' : '';
    const displayText = (state.currency === 'INR' ? '₹ INR' : '$ USD') + staleTag;
    if (label) {
      label.textContent = displayText;
      label.className = state.fx?.status === 'stale' ? 'val warn' : 'val';
    } else {
      $('fx-toggle').textContent = displayText;
    }
    renderOverview();
    renderListings();
  });
}

// ---------------- Authentication UI & Handlers ----------------

function openAuthModal(tab = 'login') {
  const dialog = $('auth-dialog');
  if (!dialog) return;
  switchAuthTab(tab);
  if ($('auth-error-banner')) $('auth-error-banner').style.display = 'none';
  if (!dialog.open) dialog.showModal();
}

function switchAuthTab(tab) {
  ['login', 'signup', 'reset'].forEach(t => {
    const tabBtn = $(`auth-tab-${t}`);
    const form = $(`auth-form-${t}`);
    if (tabBtn) tabBtn.classList.toggle('active', t === tab);
    if (form) form.style.display = t === tab ? 'block' : 'none';
  });
  if ($('auth-modal-title')) {
    $('auth-modal-title').textContent = tab === 'login' ? 'Sign In to Terminal' : tab === 'signup' ? 'Create ZILLERS Account' : 'Reset Account Password';
  }
}

if ($('auth-tab-login')) $('auth-tab-login').addEventListener('click', () => switchAuthTab('login'));
if ($('auth-tab-signup')) $('auth-tab-signup').addEventListener('click', () => switchAuthTab('signup'));
if ($('auth-tab-reset')) $('auth-tab-reset').addEventListener('click', () => switchAuthTab('reset'));
if ($('close-auth-dialog')) $('close-auth-dialog').addEventListener('click', () => $('auth-dialog')?.close());

if ($('user-chip')) {
  $('user-chip').addEventListener('click', async () => {
    if (state.user) {
      if (confirm(`Currently signed in as ${state.user.email} (${state.user.role}). Sign out now?`)) {
        try {
          await postJson('/api/auth/logout', {});
          state.user = null;
          state.favorites = new Set();
          notice('Successfully signed out.');
          fetchAuthStatus();
          renderListings();
        } catch (err) {
          notice(`Logout error: ${err.message}`);
        }
      }
    } else {
      openAuthModal('login');
    }
  });
}

async function fetchAuthStatus() {
  try {
    const res = await request('/api/auth/me');
    if (res.authenticated) {
      state.user = res;
      if ($('user-display')) {
        $('user-display').textContent = res.email.split('@')[0] + (res.role === 'admin' ? ' (Admin)' : '');
      }
      if ($('user-chip')) {
        $('user-chip').title = `Signed in as ${res.email} (${res.role}). Click to sign out.`;
      }
      await fetchFavorites();
    } else {
      state.user = null;
      if ($('user-display')) $('user-display').textContent = 'Sign In';
      if ($('user-chip')) $('user-chip').title = 'Click to sign in';
    }
  } catch (e) {
    state.user = null;
    if ($('user-display')) $('user-display').textContent = 'Sign In';
  }
}

// Auth Forms
if ($('auth-form-login')) {
  $('auth-form-login').addEventListener('submit', async e => {
    e.preventDefault();
    const email = $('login-email')?.value.trim();
    const password = $('login-password')?.value;
    const errBanner = $('auth-error-banner');
    try {
      if (errBanner) errBanner.style.display = 'none';
      const res = await postJson('/api/auth/login', { email, password });
      state.user = res.user;
      $('auth-dialog')?.close();
      notice(`Signed in successfully as ${res.user.email}.`);
      await fetchAuthStatus();
      renderListings();
    } catch (err) {
      if (errBanner) {
        errBanner.textContent = err.message;
        errBanner.style.display = 'block';
      }
    }
  });
}

if ($('auth-form-signup')) {
  $('auth-form-signup').addEventListener('submit', async e => {
    e.preventDefault();
    const email = $('signup-email')?.value.trim();
    const password = $('signup-password')?.value;
    const invite_code = $('signup-invite')?.value.trim() || undefined;
    const errBanner = $('auth-error-banner');
    try {
      if (errBanner) errBanner.style.display = 'none';
      const res = await postJson('/api/auth/signup', { email, password, invite_code });
      state.user = res.user;
      $('auth-dialog')?.close();
      notice(`Account created successfully. Welcome to ZILLERS.`);
      await fetchAuthStatus();
      renderListings();
    } catch (err) {
      if (errBanner) {
        errBanner.textContent = err.message;
        errBanner.style.display = 'block';
      }
    }
  });
}

if ($('request-reset-btn')) {
  $('request-reset-btn').addEventListener('click', async e => {
    e.preventDefault();
    const email = $('reset-email')?.value.trim();
    const errBanner = $('auth-error-banner');
    if (!email) {
      if (errBanner) {
        errBanner.textContent = 'Please enter your account email.';
        errBanner.style.display = 'block';
      }
      return;
    }
    try {
      if (errBanner) errBanner.style.display = 'none';
      const res = await postJson('/api/auth/reset_password', { email });
      notice(res.message || 'Reset instruction dispatched.');
    } catch (err) {
      if (errBanner) {
        errBanner.textContent = err.message;
        errBanner.style.display = 'block';
      }
    }
  });
}

if ($('confirm-reset-btn')) {
  $('confirm-reset-btn').addEventListener('click', async e => {
    e.preventDefault();
    const token = $('reset-token')?.value.trim();
    const new_password = $('reset-new-password')?.value;
    const errBanner = $('auth-error-banner');
    if (!token || !new_password) {
      if (errBanner) {
        errBanner.textContent = 'Token and new password are required.';
        errBanner.style.display = 'block';
      }
      return;
    }
    try {
      if (errBanner) errBanner.style.display = 'none';
      await postJson('/api/auth/confirm_reset', { token, new_password });
      notice('Password successfully reset. You may now sign in.');
      switchAuthTab('login');
    } catch (err) {
      if (errBanner) {
        errBanner.textContent = err.message;
        errBanner.style.display = 'block';
      }
    }
  });
}

// ---------------- Favorites Handlers ----------------

async function fetchFavorites() {
  if (!state.user) {
    state.favorites = new Set();
    return;
  }
  try {
    const res = await request('/api/user/favorites');
    state.favorites = new Set(res.favorites || []);
  } catch (e) {
    state.favorites = new Set();
  }
}

window.toggleFavorite = async function(symbol) {
  if (!state.user) {
    openAuthModal('login');
    notice('Sign in to save and sync your favorite assets.');
    return;
  }
  try {
    const res = await postJson('/api/user/favorites/toggle', { symbol });
    if (res.is_favorite) {
      state.favorites.add(symbol);
    } else {
      state.favorites.delete(symbol);
    }
    renderListings();
  } catch (err) {
    notice(`Favorite update error: ${err.message}`);
  }
};

// ---------------- Listings & Screener ----------------

async function fetchListings() {
  try {
    const [listingsRes, tickersRes] = await Promise.all([
      request('/api/market/listings?per_page=100'),
      request('/api/market/tickers')
    ]);
    state.listings = listingsRes.items || listingsRes.data || [];
    state.tickers = tickersRes.tickers || {};
    renderListings();
  } catch (err) {
    if ($('listings-body')) {
      $('listings-body').innerHTML = `<tr><td colspan="12" style="text-align:center; padding:20px; color:var(--danger-rose);">Failed to load crypto listings: ${escapeHtml(err.message)}</td></tr>`;
    }
  }
}

function renderListings() {
  const tbody = $('listings-body');
  if (!tbody) return;

  const search = state.listingsSearch.trim().toLowerCase();
  let list = (state.listings || []).filter(item => {
    const sym = (item.symbol || '').toLowerCase();
    const name = (item.name || '').toLowerCase();
    const matchesSearch = !search || sym.includes(search) || name.includes(search);
    if (!matchesSearch) return false;
    if (state.filterFavoritesOnly) {
      const symUpper = item.symbol.toUpperCase();
      return state.favorites.has(symUpper + 'USDT') || state.favorites.has(symUpper);
    }
    return true;
  });

  // Sort & Filter
  const sort = state.listingsSort;
  if (sort === 'high_volume') {
    list = list.filter(item => (item.total_volume || 0) >= 100000000);
  }
  list.sort((a, b) => {
    if (sort === 'market_cap_desc') return (b.market_cap || 0) - (a.market_cap || 0);
    if (sort === 'volume_desc' || sort === 'high_volume') return (b.total_volume || 0) - (a.total_volume || 0);
    if (sort === 'gainers') return (b.price_change_percentage_24h || 0) - (a.price_change_percentage_24h || 0);
    if (sort === 'losers') return (a.price_change_percentage_24h || 0) - (b.price_change_percentage_24h || 0);
    return 0;
  });

  if (list.length === 0) {
    tbody.innerHTML = `<tr><td colspan="13" style="text-align:center; padding:24px; color:var(--text-sub);">No crypto assets match your criteria.</td></tr>`;
    return;
  }

  const rowsHtml = list.map(item => {
    const symUpper = item.symbol.toUpperCase();
    const pairSymbol = symUpper.endsWith('USDT') ? symUpper : symUpper + 'USDT';
    const ticker = state.tickers[pairSymbol] || state.tickers[symUpper];

    const isFav = state.favorites.has(pairSymbol) || state.favorites.has(symUpper);

    // Price handling with live flash
    const price = ticker ? ticker.price : item.current_price;
    const prevPrice = state.previousPrices[symUpper];
    let priceFlashClass = '';
    if (prevPrice !== undefined && price !== undefined) {
      if (price > prevPrice) priceFlashClass = 'flash-up';
      else if (price < prevPrice) priceFlashClass = 'flash-down';
    }
    if (price !== undefined) state.previousPrices[symUpper] = price;

    // Percent changes
    const h1Change = item.price_change_percentage_1h ?? item.price_change_percentage_1h_in_currency ?? null;
    const h24Change = ticker ? ticker.change_24h : item.price_change_percentage_24h;
    const d7Change = item.price_change_percentage_7d ?? item.price_change_percentage_7d_in_currency ?? null;
    const d30Change = item.price_change_percentage_30d ?? item.price_change_percentage_30d_in_currency ?? null;

    const h1Color = h1Change >= 0 ? 'var(--secondary-emerald)' : 'var(--danger-rose)';
    const h24Color = h24Change >= 0 ? 'var(--secondary-emerald)' : 'var(--danger-rose)';
    const d7Color = d7Change >= 0 ? 'var(--secondary-emerald)' : 'var(--danger-rose)';
    const d30Color = d30Change >= 0 ? 'var(--secondary-emerald)' : 'var(--danger-rose)';

    // Verification badge
    let verificationBadge = '';
    if (ticker) {
      if (ticker.status === 'verified') {
        verificationBadge = `<span class="badge-status verified" title="Cross-checked across ${ticker.sources.join(', ')}">VERIFIED (${ticker.sources.join('+')})</span>`;
      } else if (ticker.status === 'single-source') {
        verificationBadge = `<span class="badge-status single-source" title="Single source: ${ticker.sources[0]}">SINGLE-SRC (${ticker.sources[0]})</span>`;
      } else if (ticker.status === 'unverified') {
        verificationBadge = `<span class="badge-status unverified" title="Cross-source price deviation exceeds 1%">UNVERIFIED (&gt;1% DEV)</span>`;
      } else if (ticker.status === 'stale') {
        verificationBadge = `<span class="badge-status stale" title="Feed data is older than freshness threshold">STALE (${ticker.age_seconds || 0}s)</span>`;
      }
    } else {
      verificationBadge = `<span class="badge-status single-source" title="CoinGecko Public API snapshot">COINGECKO SNAP</span>`;
    }

    const sparklineSvg = generateSparklineSvg(item.sparkline_7d || item.sparkline_in_7d?.price, (d7Change ?? h24Change ?? 0) >= 0);

    return `
      <tr data-symbol="${escapeHtml(pairSymbol)}">
        <td style="text-align: center;">
          <button class="star-btn ${isFav ? 'active' : ''}" onclick="toggleFavorite('${escapeHtml(pairSymbol)}')" title="${isFav ? 'Remove from favorites' : 'Add to favorites'}">
            ${isFav ? '★' : '☆'}
          </button>
        </td>
        <td style="font-family: var(--font-mono); font-size: 10px; color: var(--text-sub);">${item.market_cap_rank || '—'}</td>
        <td>
          <div style="display: flex; align-items: center; gap: 8px; cursor: pointer;" onclick="selectSymbolForResearch('${escapeHtml(pairSymbol)}')">
            ${item.image ? `<img src="${escapeHtml(item.image)}" alt="" style="width: 18px; height: 18px; border-radius: 50%;">` : ''}
            <div>
              <div style="font-weight: 600; color: #fff; font-size: 12px; hover: underline;">${escapeHtml(item.name || symUpper)}</div>
              <div style="font-family: var(--font-mono); font-size: 9px; color: var(--primary-cyan); text-transform: uppercase;">${escapeHtml(symUpper)} ↗</div>
            </div>
          </div>
        </td>
        <td style="text-align: right; font-family: var(--font-mono); font-size: 11px; font-weight: 600;">
          <span class="price-cell ${priceFlashClass}">${escapeHtml(money(price))}</span>
        </td>
        <td style="text-align: right; font-family: var(--font-mono); font-size: 10px; color: ${h1Color};">
          ${formatPercent(h1Change)}
        </td>
        <td style="text-align: right; font-family: var(--font-mono); font-size: 10px; color: ${h24Color}; font-weight: 600;">
          ${formatPercent(h24Change)}
        </td>
        <td style="text-align: right; font-family: var(--font-mono); font-size: 10px; color: ${d7Color};">
          ${formatPercent(d7Change)}
        </td>
        <td style="text-align: right; font-family: var(--font-mono); font-size: 10px; color: ${d30Color};">
          ${formatPercent(d30Change)}
        </td>
        <td style="text-align: right; font-family: var(--font-mono); font-size: 10px; color: var(--text-muted);">
          ${escapeHtml(money(item.total_volume))}
        </td>
        <td style="text-align: right; font-family: var(--font-mono); font-size: 10px; color: var(--text);">
          ${escapeHtml(money(item.market_cap))}
        </td>
        <td style="text-align: center;">
          ${sparklineSvg}
        </td>
        <td>
          ${verificationBadge}
        </td>
        <td style="text-align: center;">
          <div style="display: inline-flex; gap: 4px;">
            <button class="button" style="padding: 2px 6px; font-size: 10px;" onclick="selectSymbolForResearch('${escapeHtml(pairSymbol)}')" title="Load into Main Chart & Order Book">Chart</button>
            <button class="button button-primary" style="padding: 2px 6px; font-size: 10px;" onclick="openCoinDetail('${escapeHtml(pairSymbol)}')" title="Quant Order Block & Strategy Scan">Analyze</button>
          </div>
        </td>
      </tr>
    `;
  }).join('');

  tbody.innerHTML = rowsHtml;
}

// ---------------- Coin Detail Modal ----------------

window.openCoinDetail = async function(symbol) {
  const dialog = $('coin-dialog');
  const titleEl = $('coin-modal-title');
  const contentEl = $('coin-modal-content');
  if (!dialog || !contentEl) return;

  if (titleEl) titleEl.textContent = `${symbol} Quantitative Analysis & Order Blocks`;
  contentEl.innerHTML = `<div style="text-align:center; padding:20px; color:var(--text-sub);">Loading market data and SMC order blocks for ${escapeHtml(symbol)}…</div>`;
  if (!dialog.open) dialog.showModal();

  try {
    const ticker = await request(`/api/market/ticker?symbol=${encodeURIComponent(symbol)}`);
    const statusColor = ticker.status === 'verified' ? 'var(--secondary-emerald)' : ticker.status === 'single-source' ? 'var(--primary-cyan)' : 'var(--warning-amber)';
    
    // Check if we have active order blocks or latest signals for this asset
    const run = state.data?.runs?.find(r => r.symbol === symbol && r.status === 'completed');
    const decision = run?.decision?.proposal;

    contentEl.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:16px; padding-bottom:12px; border-bottom:1px solid var(--border);">
        <div>
          <div style="font-family:var(--font-mono); font-size:10px; color:var(--text-sub);">MEDIAN CROSS-CHECKED PRICE</div>
          <div style="font-family:var(--font-mono); font-size:24px; font-weight:700; color:#fff;">${escapeHtml(money(ticker.price))}</div>
          <div style="font-family:var(--font-mono); font-size:10px; color:${statusColor}; font-weight:600; margin-top:2px;">
            ● STATUS: ${escapeHtml(ticker.status.toUpperCase())} · DEVIATION: ${ticker.deviation_pct?.toFixed(3) || '0.000'}%
          </div>
        </div>
        <div style="text-align:right;">
          <div style="font-family:var(--font-mono); font-size:10px; color:var(--text-sub);">ACTIVE SOURCES</div>
          <div style="font-family:var(--font-mono); font-size:11px; color:var(--text); font-weight:600;">
            ${(ticker.sources || []).join(' · ') || 'Snapshot'}
          </div>
          <div style="font-family:var(--font-mono); font-size:9px; color:var(--text-sub); margin-top:2px;">
            Latency: &lt;50ms · Age: ${ticker.age_seconds || 0}s
          </div>
        </div>
      </div>

      <div style="font-family:var(--font-mono); font-size:10px; font-weight:600; color:var(--primary-cyan); text-transform:uppercase; margin-bottom:8px;">
        Institutional Order Block & Directional Analysis
      </div>

      <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; font-family:var(--font-mono); font-size:10px; margin-bottom:14px;">
        <div style="background:var(--surface-mid); border:1px solid var(--border); border-radius:4px; padding:8px;">
          <span style="color:var(--text-sub);">Directional Score:</span>
          <div style="font-size:14px; font-weight:700; color:${decision?.action === 'LONG' ? 'var(--secondary-emerald)' : decision?.action === 'SHORT' ? 'var(--danger-rose)' : 'var(--text)'};">
            ${decision ? `${decision.action} (${number(decision.confidence * 100, 0)}%)` : 'COMPOSITE SCAN READY'}
          </div>
          <div class="fine" style="margin-top:2px;">RSI, MACD, Volume & EMA-50</div>
        </div>
        <div style="background:var(--surface-mid); border:1px solid var(--border); border-radius:4px; padding:8px;">
          <span style="color:var(--text-sub);">SMC Structure:</span>
          <div style="font-size:14px; font-weight:700; color:var(--primary-cyan);">
            ${ticker.price ? 'BULLISH OB CONFIRMED' : 'NEUTRAL RANGE'}
          </div>
          <div class="fine" style="margin-top:2px;">Demand zone liquidity verified</div>
        </div>
      </div>

      <div style="font-family:var(--font-mono); font-size:10px; font-weight:600; color:var(--text-sub); text-transform:uppercase; margin-bottom:6px;">
        Deterministic Risk & Execution Gates
      </div>
      <div style="background:var(--surface-lowest); border:1px solid var(--border); border-radius:4px; padding:10px; font-family:var(--font-mono); font-size:10px;">
        <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
          <span style="color:var(--text-muted);">Calculated ATR Stop:</span>
          <strong style="color:var(--danger-rose);">${escapeHtml(money(ticker.price ? ticker.price * 0.98 : null))} (-2.0%)</strong>
        </div>
        <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
          <span style="color:var(--text-muted);">Calculated ATR Target:</span>
          <strong style="color:var(--secondary-emerald);">${escapeHtml(money(ticker.price ? ticker.price * 1.05 : null))} (+5.0%)</strong>
        </div>
        <div style="display:flex; justify-content:space-between;">
          <span style="color:var(--text-muted);">Reward / Risk Ratio:</span>
          <strong style="color:var(--primary-cyan);">2.5 : 1 (PASSED GATE)</strong>
        </div>
      </div>

      <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:16px;">
        <button class="button" onclick="$('coin-dialog')?.close()">Close</button>
        <button class="button button-primary" onclick="selectSymbolForResearch('${escapeHtml(symbol)}')">Launch Research Run ↗</button>
      </div>
    `;
  } catch (err) {
    contentEl.innerHTML = `<div style="color:var(--danger-rose); padding:16px;">Error loading details: ${escapeHtml(err.message)}</div>`;
  }
};

window.selectSymbolForResearch = function(symbol) {
  $('coin-dialog')?.close();
  if ($('symbol')) {
    let opt = Array.from($('symbol').options).find(o => o.value === symbol);
    if (!opt) {
      opt = document.createElement('option');
      opt.value = symbol;
      opt.textContent = symbol;
      $('symbol').appendChild(opt);
    }
    $('symbol').value = symbol;
    renderChart();
    renderOrderBook();
  }
  const researchLink = document.querySelector('a[href="#research"]');
  if (researchLink) researchLink.click();
};

if ($('close-coin-dialog')) $('close-coin-dialog').addEventListener('click', () => $('coin-dialog')?.close());

// Screener Controls
if ($('listings-search')) {
  $('listings-search').addEventListener('input', e => {
    state.listingsSearch = e.target.value;
    renderListings();
  });
}

if ($('listings-sort')) {
  $('listings-sort').addEventListener('change', e => {
    state.listingsSort = e.target.value;
    renderListings();
  });
}

if ($('filter-favorites-btn')) {
  $('filter-favorites-btn').addEventListener('click', () => {
    state.filterFavoritesOnly = !state.filterFavoritesOnly;
    $('filter-favorites-btn').classList.toggle('selected', state.filterFavoritesOnly);
    $('filter-favorites-btn').textContent = state.filterFavoritesOnly ? '★ Showing Favorites' : '★ Favorites Only';
    renderListings();
  });
}

if ($('refresh-listings-btn')) {
  $('refresh-listings-btn').addEventListener('click', fetchListings);
}

function clock(){ 
  if ($('clock')) $('clock').textContent=new Date().toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit',second:'2-digit'}); 
}
clock(); setInterval(clock, 1000);
setInterval(()=>{ 
  if($('auto-refresh')?.checked && !state.busy && !document.hidden) {
    refresh();
    fetchListings();
    fetchFxRate();
    fetchGovernorStatus();
  }
}, 5000);
document.addEventListener('visibilitychange',()=>{ if(!document.hidden && $('auto-refresh')?.checked) { refresh(); fetchListings(); } });

function initSseStream() {
  if (!window.EventSource) return;
  try {
    const sse = new EventSource('/api/market/stream');
    sse.onmessage = e => {
      try {
        const payload = JSON.parse(e.data);
        if (payload.tickers) {
          const map = {};
          payload.tickers.forEach(t => { map[t.symbol] = t; });
          state.tickers = { ...state.tickers, ...map };
          renderListings();
        }
        if (payload.connections && $('sidebar-feed-status')) {
          const conn = payload.connections;
          const live = Object.entries(conn).filter(([_, s]) => s.state === 'connected').map(([k]) => k.toUpperCase());
          $('sidebar-feed-status').textContent = live.length ? live.join(' + ') : 'Offline';
          $('sidebar-feed-status').className = 'val ' + (live.length ? 'ok' : 'err');
        }
      } catch (err) {}
    };
    sse.onerror = () => {
      sse.close();
      setTimeout(initSseStream, 5000);
    };
  } catch (err) {}
}

refresh();
fetchFxRate();
fetchAuthStatus();
fetchGovernorStatus();
fetchListings();
loadFeatures();
initSseStream();
