import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {analyze,demoInput,verifyProvenance} from '../adapter.mjs';

test('selected files match reviewed upstream Git blob hashes',()=>{
  assert.equal(verifyProvenance().commit,'c930628c47a4a745f497e29035a3b64622f97cc7');
});
test('historical losses and stress shocks have known values',()=>{
  const result=analyze({pnl_usd:[-100,-50,20,30],returns_pct:[-1,-.5,.2,.3],
    positions:[{id:'BTC',platform:'binance-spot',value:1000,pnlPct:0,side:'long'}]});
  assert.equal(result.risk.historicalVaR,100);
  assert.equal(result.risk.cvar,100);
  assert.equal(result.stress.find(s=>s.scenario==='flash_crash').estimatedLoss,200);
  assert.equal(result.stress.find(s=>s.scenario==='black_swan').estimatedLoss,400);
  assert.equal(result.volatility,null);
});
test('sequential calibration detects extreme regime after a shock',()=>{
  const result=analyze(demoInput());
  assert.equal(result.volatility.regime,'extreme');
  assert.equal(result.volatility.shouldHalt,true);
  assert.equal(result.advisory_only,true);
});
test('invalid observations fail before calculations',()=>{
  for(const input of [{pnl_usd:[NaN,1],returns_pct:[1,1]},
    {pnl_usd:[1,2],returns_pct:[1]},
    {pnl_usd:[1,2],returns_pct:[1,2],confidence:1},
    {pnl_usd:[1,2],returns_pct:[1,'2']},
    {pnl_usd:[1,2],returns_pct:[1,2],positions:[{id:'x',platform:'binance',value:-1,pnlPct:0,side:'long'}]}]){
    assert.throws(()=>analyze(input));
  }
});
test('shorts and duplicate positions are refused by the spot boundary',()=>{
  const input=demoInput();input.positions[0].side='short';
  assert.throws(()=>analyze(input),/long positions only/);
  const dup=demoInput();dup.positions.push(dup.positions[0]);
  assert.throws(()=>analyze(dup),/unique IDs/);
});
test('empty portfolio has no stressed exposure',()=>{
  const input=demoInput();input.positions=[];
  const result=analyze(input);
  assert.ok(result.stress.every(s=>s.estimatedLoss===0));
});
test('CLI malformed input exits nonzero with explicit JSON error',()=>{
  const result=spawnSync(process.execPath,[fileURLToPath(new URL('../cli.mjs',import.meta.url)),'--stdin'],
    {input:'invalid json',encoding:'utf8'});
  assert.notEqual(result.status,0);
  assert.equal(JSON.parse(result.stderr).status,'failed');
});
