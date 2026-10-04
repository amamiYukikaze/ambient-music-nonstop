const {execFile}=require('node:child_process');
const path=require('node:path');
exports.checkRuntime=({root,specPath,managed=true})=>new Promise(resolve=>{
 const python=path.join(root,'vendor/ACE-Step-1.5/.venv/Scripts/python.exe');
 const args=[path.join(root,'scripts/runtime_health.py'),'--root',root,'--spec',specPath,...(managed?[]:['--development'])];
 let timer,child,done=false;
 const finish=result=>{if(done)return;done=true;clearTimeout(timer);resolve(result);};
 const failed=error=>finish({ok:false,errors:['Python runtime health check failed: '+String(error?.message||'invalid response').slice(0,1000)]});
 try{child=execFile(python,args,{cwd:root,windowsHide:true,maxBuffer:1024*1024},(error,stdout)=>{
  try{const result=JSON.parse(stdout);if(typeof result.ok==='boolean'&&Array.isArray(result.errors)){finish(result);return;}}catch{}
  failed(error);
 });timer=setTimeout(()=>{if(child.pid)execFile('taskkill',['/PID',String(child.pid),'/T','/F'],{windowsHide:true},()=>{});failed(Error('Runtime check timed out; retry repair.'));},300000);}catch(error){failed(error);}
});
