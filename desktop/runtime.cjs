const {BrowserWindow,ipcMain}=require('electron');
const {spawn,execFile}=require('node:child_process');
const path=require('node:path'),os=require('node:os');
const {trustedHandlers,secureWindow}=require('./security.cjs');
const {checkRuntime}=require('./runtime-health.cjs');
exports.ensureRuntime=({root,localRoot,specPath,reason})=>new Promise((resolve,reject)=>{
 const win=new BrowserWindow({icon:path.join(__dirname,'icon.ico'),width:900,height:700,backgroundColor:'#172632',autoHideMenuBar:true,webPreferences:{preload:path.join(__dirname,'runtime-preload.cjs'),sandbox:true,contextIsolation:true,nodeIntegration:false}});
 const page=path.join(localRoot,'ui/runtime.html');secureWindow(win,page);
 const trustedIpc=trustedHandlers(ipcMain,()=>win,page);
 let processHandle,checking=false,allowed=false,done=false;win.loadFile(page);
 win.webContents.once('did-finish-load',()=>win.webContents.send('runtime-progress','需要安装或修复运行环境：\n'+reason+'\n'));
 trustedIpc.handle('runtime-scan',async()=>{const result=await new Promise(r=>execFile('nvidia-smi',['--query-gpu=memory.total','--format=csv,noheader,nounits'],{windowsHide:true,timeout:12000},(e,out)=>r(e?0:Number(out.trim().split('\n')[0])/1024)));const ram=os.totalmem()/1024**3;allowed=process.platform==='win32'&&ram>=15.5&&result>=3.8;return {allowed,ram,vram:result};});
 trustedIpc.handle('runtime-install',()=>{
  if(!allowed)throw Error('请先允许设备检查并通过最低门槛');if(processHandle||checking)throw Error('安装正在进行');
  processHandle=spawn('powershell.exe',['-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',path.join(root,'scripts/install-runtime.ps1'),'-RuntimeRoot',root],{windowsHide:true,stdio:['ignore','pipe','pipe']});
  for(const stream of [processHandle.stdout,processHandle.stderr])stream.on('data',b=>{if(!win.isDestroyed())win.webContents.send('runtime-progress',b.toString().slice(-4000));});
  processHandle.on('error',e=>{processHandle=null;if(!win.isDestroyed())win.webContents.send('runtime-progress','安装失败：'+e.message);});
  processHandle.on('exit',async code=>{
   processHandle=null;checking=code===0;
   if(code===0){const health=await checkRuntime({root,specPath});if(health.ok&&!win.isDestroyed()){processHandle=null;done=true;win.close();resolve();return;}
    if(!win.isDestroyed())win.webContents.send('runtime-progress','安装失败，运行环境检查未通过：'+health.errors.join('\n'));
   }else if(!win.isDestroyed())win.webContents.send('runtime-progress','安装失败，可点击重试。退出码 '+code);
   checking=false;
  });return true;
 });
 win.on('closed',()=>{ipcMain.removeHandler('runtime-scan');ipcMain.removeHandler('runtime-install');if(!done){if(processHandle)execFile('taskkill',['/pid',String(processHandle.pid),'/t','/f'],{windowsHide:true},()=>{});reject(Error('运行环境安装已取消'));}});
});
