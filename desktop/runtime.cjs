const {BrowserWindow,ipcMain,shell}=require('electron');
const {spawn,execFile}=require('node:child_process');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {trustedHandlers,secureWindow}=require('./security.cjs');
const {checkRuntime}=require('./runtime-health.cjs');
const {progressDecoder}=require('./runtime-progress.cjs');
const {deviceSupport}=require('./runtime-device.cjs');

exports.ensureRuntime=({root,localRoot,specPath,initialCheck,claimIntro=()=>false})=>new Promise((resolve,reject)=>{
 const win=new BrowserWindow({icon:path.join(__dirname,'icon.ico'),width:980,height:780,minWidth:620,minHeight:540,backgroundColor:'#152a35',autoHideMenuBar:true,webPreferences:{preload:path.join(__dirname,'runtime-preload.cjs'),sandbox:true,contextIsolation:true,nodeIntegration:false}});
 const page=path.join(localRoot,'ui/runtime.html');secureWindow(win,page);
 const trustedIpc=trustedHandlers(ipcMain,()=>win,page);
 let child,checking=true,allowed=false,done=false;
 const checkAbort=new AbortController();
 let state={type:'state',status:'checking',root,phase:'checking',stage:'health',completed:0,stages:9};
 function send(event){if(event.type!=='log')state={...state,...event,intro:false};if(!win.isDestroyed())win.webContents.send('runtime-progress',event);}
 function fail(message){checking=false;send({type:'state',status:'failed',phase:'failed',error:message});}
 function complete(){if(win.isDestroyed())return;done=true;send({type:'state',status:'ready',phase:'done',completed:9});win.close();resolve();}
 trustedIpc.handle('runtime-state',()=>state);
 trustedIpc.handle('runtime-hf-help',()=>shell.openExternal('https://huggingface.co/stabilityai/stable-audio-3-medium'));
 trustedIpc.handle('runtime-scan',async()=>{
  const vram=await new Promise(r=>execFile('nvidia-smi',['--query-gpu=memory.total','--format=csv,noheader,nounits'],{windowsHide:true,timeout:12000},(e,out)=>r(e?0:Number(out.trim().split('\n')[0])/1024)));
  const result=deviceSupport({platform:process.platform,arch:process.arch,ram:os.totalmem()/1024**3,vram});allowed=result.allowed;return result;
 });
 trustedIpc.handle('runtime-install',()=>{
  if(!allowed)throw Error('请先允许设备检查并通过最低门槛');
  if(child||checking)throw Error('安装或检查正在进行');
  fs.mkdirSync(path.join(root,'.log'),{recursive:true});
  const log=fs.createWriteStream(path.join(root,'.log','runtime-install.log'),{flags:'w'});log.on('error',()=>{});
  send({type:'state',status:'installing',phase:'preparing',stage:'uv',completed:0,stages:9,reset:true});
  child=spawn('powershell.exe',['-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',path.join(root,'scripts/install-runtime.ps1'),'-RuntimeRoot',root],{cwd:root,windowsHide:true,stdio:['ignore','pipe','pipe']});
  for(const stream of [child.stdout,child.stderr]){
   const decoder=progressDecoder(send);stream.on('data',b=>{log.write(b);decoder.write(b);});stream.on('end',()=>decoder.end());
  }
  let spawnError;child.on('error',e=>{spawnError=e;});
  child.on('close',async code=>{
   child=null;log.end();if(win.isDestroyed())return;
   if(spawnError||code!==0){fail(spawnError?.message||`安装未完成（退出码 ${code}），展开日志查看原因，然后重试。`);return;}
   checking=true;send({type:'progress',phase:'checking',stage:'health',completed:8,stages:9});
   try{const health=await checkRuntime({root,specPath,signal:checkAbort.signal,startup:true});if(health.ok)complete();else fail(health.errors.join('\n'));}
   catch(error){fail(error.message);}
  });return true;
 });
 win.webContents.once('did-finish-load',async()=>{
  try{const health=await initialCheck(checkAbort.signal);if(win.isDestroyed())return;
   if(health.ok){complete();return;}
   checking=false;send({type:'state',status:'needs-install',phase:'waiting',error:health.errors.join('\n'),intro:claimIntro()});
   send({type:'log',text:'运行环境需要安装或修复：\n'+health.errors.join('\n')});
  }catch(error){fail(error.message);}
 });
 win.on('closed',()=>{
  checkAbort.abort();
  for(const channel of ['runtime-scan','runtime-install','runtime-state','runtime-hf-help'])ipcMain.removeHandler(channel);
  if(!done){if(child?.pid)execFile('taskkill',['/pid',String(child.pid),'/t','/f'],{windowsHide:true},()=>{});reject(Error('运行环境准备已取消'));}
 });
 win.loadFile(page);
});
