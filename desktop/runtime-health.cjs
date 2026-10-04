const {execFile}=require('node:child_process');
const path=require('node:path');
const {StringDecoder}=require('node:string_decoder');
exports.checkRuntime=({root,specPath,managed=true,signal,startup=false,onProgress=()=>{}})=>new Promise(resolve=>{
 const python=path.join(root,'vendor/ACE-Step-1.5/.venv/Scripts/python.exe');
 const args=['-u',path.join(root,'scripts/runtime_health.py'),'--root',root,'--spec',specPath,'--progress',...(managed?[]:['--development']),...(startup?['--startup']:[])];
 let timer,child,done=false;
 const finish=result=>{if(done)return;done=true;clearTimeout(timer);signal?.removeEventListener('abort',abort);resolve(result);};
 const failed=error=>finish({ok:false,errors:['Python runtime health check failed: '+String(error?.message||'invalid response').slice(0,1000)]});
 const stop=()=>{if(child?.pid)execFile('taskkill',['/PID',String(child.pid),'/T','/F'],{windowsHide:true},()=>{});};
 const abort=()=>{stop();failed(Error('Runtime check cancelled'));};
 if(signal?.aborted){abort();return;}
 signal?.addEventListener('abort',abort,{once:true});
 try{child=execFile(python,args,{cwd:root,windowsHide:true,maxBuffer:1024*1024},(error,stdout)=>{
  try{const result=JSON.parse(stdout.trim().split(/\r?\n/).at(-1));if(typeof result.ok==='boolean'&&Array.isArray(result.errors)){finish(result);return;}}catch{}
  failed(error);
 });
 const decoder=new StringDecoder('utf8');let pending='';
 child.stdout.on('data',bytes=>{pending+=decoder.write(bytes);const lines=pending.split(/\r?\n/);pending=lines.pop();for(const line of lines){if(line.startsWith('AMBIENT_HEALTH ')){try{onProgress(JSON.parse(line.slice(15)));}catch{}}}});
 timer=setTimeout(()=>{stop();failed(Error('Runtime check timed out; retry repair.'));},720000);}catch(error){failed(error);}
});
