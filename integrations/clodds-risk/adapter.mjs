/** Validated advisory boundary; upstream files stay byte-for-byte unchanged. */
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {createVaRCalculator} from './src/risk/var.ts';
import {createVolatilityDetector} from './src/risk/volatility.ts';
import {runAllScenarios} from './src/risk/stress.ts';

export function verifyProvenance() {
  const provenance=JSON.parse(readFileSync(new URL('./provenance.json', import.meta.url),'utf8'));
  for(const item of provenance.installed_modules){
    const bytes=readFileSync(new URL(item.path,import.meta.url));
    const hash=createHash('sha1').update(Buffer.from(`blob ${bytes.length}\0`)).update(bytes).digest('hex');
    if(hash!==item.git_blob_sha)throw new Error(`Upstream source integrity mismatch: ${item.path}`);
  }
  return {repository:provenance.repository,commit:provenance.commit,version:provenance.version};
}

function finite(value,name){
  if(typeof value!=='number'||!Number.isFinite(value))throw new Error(`${name} must be a finite number`);
  return value;
}

export function analyze(input){
  verifyProvenance();
  if(!input||typeof input!=='object'||Array.isArray(input))throw new Error('Input must be an object');
  const pnl=input.pnl_usd,returns=input.returns_pct;
  if(!Array.isArray(pnl)||!Array.isArray(returns)||pnl.length!==returns.length||pnl.length<2||pnl.length>10000){
    throw new Error('pnl_usd and returns_pct must be aligned arrays with 2..10000 observations');
  }
  pnl.forEach((v,i)=>finite(v,`pnl_usd[${i}]`));
  returns.forEach((v,i)=>finite(v,`returns_pct[${i}]`));
  const confidence=input.confidence??0.95;
  finite(confidence,'confidence');
  if(confidence<0.5||confidence>=1)throw new Error('confidence must be >= 0.5 and < 1');
  const positions=input.positions??[];
  if(!Array.isArray(positions)||positions.length>1000)throw new Error('positions must be an array with at most 1000 entries');
  const ids=new Set();
  for(const position of positions){
    if(!position||typeof position.id!=='string'||!position.id||ids.has(position.id)||
       typeof position.platform!=='string'||!position.platform)throw new Error('Positions need unique IDs and a platform');
    ids.add(position.id);
    if(position.side!=='long')throw new Error('This spot advisory adapter supports long positions only');
    if(finite(position.value,'position.value')<0)throw new Error('Position value must be non-negative');
    finite(position.pnlPct,'position.pnlPct');
  }
  const calculator=createVaRCalculator({windowSize:100,confidenceLevel:confidence});
  pnl.forEach((v,i)=>calculator.addObservation({pnlUsd:v,pnlPct:returns[i],timestamp:new Date(0)}));
  const risk=calculator.calculate();
  // Retain a fixed warmup window. Upstream detectRegime() calibrates on its full
  // input and generally classifies that same input as normal; do not use it here.
  const detector=createVolatilityDetector({lookbackWindow:30,haltOnExtreme:true});
  returns.forEach(v=>detector.addObservation(v));
  const volatility=returns.length>30?detector.detect():null;
  const warnings=[
    'Advisory diagnostics only; no order placement or automatic sizing changes.',
    'VaR/CVaR are per observation, not annualized; keep a fixed sampling interval.',
    'Stress scenarios use fixed heuristic shocks, not a fitted liquidation model.',
    'Volatility input uses percentage points: 1 means 1%, not 0.01.',
  ];
  if(pnl.length<100)warnings.push('Fewer than 100 P&L observations; tail estimates may be unstable.');
  if(!volatility)warnings.push('Volatility needs more than 30 observations so evaluation follows calibration.');
  const report={
    status:'completed',advisory_only:true,source:input.source??'user_supplied',
    units:{pnl:'USD',returns:'percentage_points',stress_position_value:'USD',stress_position_pnlPct:'decimal_fraction'},
    observation_count:pnl.length,risk,volatility,stress:runAllScenarios(positions),warnings,
  };
  if(!JSON.stringify(report)||!Number.isFinite(risk.historicalVaR)||!Number.isFinite(risk.cvar))throw new Error('Invalid risk calculation');
  return report;
}

export function demoInput(){
  return {source:'synthetic_installation_check_not_a_trading_signal',
    pnl_usd:Array.from({length:60},(_,i)=>(i%2?1:-1)*(i<30?10:50)),
    returns_pct:Array.from({length:60},(_,i)=>(i%2?1:-1)*(i<30?1:5)),
    positions:[{id:'BTC-demo',platform:'binance-spot',value:1000,pnlPct:0,side:'long'}]};
}
