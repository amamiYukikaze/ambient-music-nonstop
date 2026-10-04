const {execFile}=require('node:child_process');
const path=require('node:path');
exports.checkRuntime=({root,specPath,managed=true,signal})=>new Promise(resolve=>{
 const python=path.join(root,'vendor/ACE-Step-1.5/.venv/Scripts/python.exe');
 const args=[path.join(root,'scripts/runtime_health.py'),'--root',root,'--spec',specPath,...(managed?[]:['--development'])];
 let timer,child,done=false;
 const finish=result=>{if(done)return;done=true;clearTimeout(timer);signal?.removeEventListener('abort',abort);resolve(result);};
 const failed=error=>finish({ok:false,errors:['Python runtime health check failed: '+String(error?.message||'invalid response').slice(0,1000)]});
 const stop=()=>{if(child?.pid)execFile('taskkill',['/PID',String(child.pid),'/T','/F'],{windowsHide:true},()=>{});};
 const abort=()=>{stop();failed(Error('Runtime check cancelled'));};
 if(signal?.aborted){abort();return;}
 signal?.addEventListener('abort',abort,{once:true});
 try{child=execFile(python,args,{cwd:root,windowsHide:true,maxBuffer:1024*1024},(error,stdout)=>{
  try{const result=JSON.parse(stdout);if(typeof result.ok==='boolean'&&Array.isArray(result.errors)){finish(result);return;}}catch{}
  failed(error);
 });timer=setTimeout(()=>{stop();failed(Error('Runtime check timed out; retry repair.'));},720000);}catch(error){failed(error);}
});
