import {readFileSync} from 'node:fs';
import {analyze,demoInput,verifyProvenance} from './adapter.mjs';

try{
  const args=process.argv.slice(2);
  if(args.length!==1||!['--demo','--stdin'].includes(args[0]))throw new Error('Usage: node cli.mjs --demo | --stdin');
  const input=args[0]==='--demo'?demoInput():JSON.parse(readFileSync(0,'utf8'));
  const result=analyze(input);
  console.log(JSON.stringify({...result,upstream:verifyProvenance(),network_requests:0},null,2));
}catch(error){
  console.error(JSON.stringify({status:'failed',error:error.message}));
  process.exitCode=1;
}
