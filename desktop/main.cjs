const { app, BrowserWindow, ipcMain, powerSaveBlocker, dialog, shell } = require('electron');
const { spawn, execFile } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const crypto = require('node:crypto');
const net = require('node:net');
const {watchVisibility}=require('./visibility.cjs');
const {brightness}=require('./brightness.cjs');
const {trustedHandlers,secureWindow}=require('./security.cjs');
const {checkRuntime}=require('./runtime-health.cjs');
const {runtimeRoot,claimSetupIntro}=require('./runtime-location.cjs');
app.setAppUserModelId('work.amamiykkz.ambientmusicnonstop');
if(process.env.AMBIENT_USER_DATA)app.setPath('userData',path.resolve(process.env.AMBIENT_USER_DATA));

let win, backend, stopVisibility, token = crypto.randomBytes(32).toString('hex'), base, quitting=false, restartDelay=1000;
let migrationBusy=false;
let preparingRuntime=false;
let unsavedSettings=false;
const localRoot = path.resolve(__dirname, '..');
const trustedIpc=trustedHandlers(ipcMain,()=>win,path.join(localRoot,'ui/index.html'));
const dataRoot=path.resolve(process.env.AMBIENT_DATA_DIR||(fs.existsSync('D:/AmbMusicNonstop/library.sqlite3')?'D:/AmbMusicNonstop':path.join(app.getPath('userData'),'data')));
process.env.AMBIENT_DATA_DIR=dataRoot;
const root=runtimeRoot({packaged:app.isPackaged,localRoot,dataRoot,override:process.env.AMBIENT_RUNTIME_DIR});
const python = path.join(root, 'vendor/ACE-Step-1.5/.venv/Scripts/python.exe');
app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');
if (!app.requestSingleInstanceLock()) app.quit();
app.on('second-instance', () => { if (win) { win.restore(); win.focus(); } });

async function port() {
  return new Promise(resolve => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => resolve(p)); }); });
}
async function api(method, route, body) {
  if (!/^\/(health|state|next|jobs|settings|plays|tracks|audio|ambience|library-move|setup|configuration|assets|images)(\/[a-zA-Z0-9_-]+)*([?][a-zA-Z0-9_=&.-]*)?$/.test(route)) throw Error('Invalid API path');
  if (!['GET','POST','PUT','PATCH','DELETE'].includes(method)) throw Error('Invalid method');
  const r = await fetch(base + route, { method, headers: { 'x-ambient-token': token, 'content-type': 'application/json' }, body: body == null ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(route==='/assets/import'?300000:30000) });
  if (!r.ok) throw Error(`服务返回 ${r.status}: ${await r.text()}`);
  return r;
}
trustedIpc.handle('api', async (_e, method, route, body) => {
  if(route==='/library-move'&&method==='POST')migrationBusy=true;
  try{const data=await (await api(method,route,body)).json();if(route==='/library-move')migrationBusy=Boolean(data.active);return data;}
  catch(e){if(route==='/library-move'&&method==='POST')migrationBusy=false;throw e;}
});
trustedIpc.handle('choose-library-folder',async()=>{
  if(migrationBusy)return null;
  const result=await dialog.showOpenDialog(win,{title:'选择新的空曲库目录',properties:['openDirectory','createDirectory']});
  return result.canceled?null:result.filePaths[0];
});
trustedIpc.handle('audio', async (_e, kind, id) => {
  if (!['audio','ambience'].includes(kind) || !/^[a-z0-9_-]+$/.test(id)) throw Error('Invalid audio id');
  return new Uint8Array(await (await api('GET', `/${kind}/${id}`)).arrayBuffer());
});
trustedIpc.handle('image',async(_e,id)=>{
  if(!/^custom_[a-f0-9]{32}$/.test(id))throw Error('Invalid image');
  return new Uint8Array(await (await api('GET',`/images/${id}`)).arrayBuffer());
});
trustedIpc.handle('choose-folder',async()=>{const r=await dialog.showOpenDialog(win,{properties:['openDirectory','createDirectory']});return r.canceled?null:r.filePaths[0];});
trustedIpc.handle('choose-import',async(_e,kind)=>{
  if(!['images','ambience'].includes(kind))throw Error('Invalid import kind');
  const r=await dialog.showOpenDialog(win,{properties:['openFile'],filters:[{name:kind==='images'?'图片':'环境声音',extensions:kind==='images'?['png','jpg','jpeg','webp','bmp']:['wav','mp3','opus','ogg','flac','m4a']} ]});return r.canceled?null:r.filePaths[0];
});
trustedIpc.handle('hf-help',()=>shell.openExternal('https://huggingface.co/stabilityai/stable-audio-3-medium'));
trustedIpc.handle('brightness',(_e,request)=>brightness(request));
trustedIpc.handle('setup-intro',()=>claimSetupIntro(app.getPath('userData')));
trustedIpc.on('unsaved-settings',(_e,value)=>{unsavedSettings=value===true;});
trustedIpc.handle('window', (_e, action) => {
  if (action === 'minimize') win.minimize();
  if (action === 'fullscreen') win.setFullScreen(!win.isFullScreen());
  if (action === 'close') win.close();
  if (action === 'close-saved') {unsavedSettings=false;win.close();}
});

function startBackend(p,log){
  backend = spawn(python, ['-u','-m','server.app'], { cwd:root, env:{...process.env, PATH:path.join(root,'tools/ffmpeg/bin')+path.delimiter+process.env.PATH, AMBIENT_PORT:String(p), AMBIENT_API_TOKEN:token}, windowsHide:true, stdio:['ignore',log,log] });
  backend.on('error', error => {if(!quitting)dialog.showErrorBox('声音服务未能启动', error.message);});
  backend.on('exit',()=>{if(!quitting){const delay=restartDelay;restartDelay=Math.min(30000,restartDelay*2);setTimeout(()=>{if(!quitting)startBackend(p,log);},delay);}});
}
app.whenReady().then(async () => {
  if(app.isPackaged){
    fs.mkdirSync(root,{recursive:true});fs.cpSync(path.join(process.resourcesPath,'backend'),root,{recursive:true});
  }
  const specPath=app.isPackaged?path.join(process.resourcesPath,'runtime.json'):path.join(localRoot,'scripts/runtime-spec.json');
  preparingRuntime=true;
  try{const {ensureRuntime}=require('./runtime.cjs');await ensureRuntime({root,localRoot,specPath,
    initialCheck:async signal=>await checkRuntime({root,specPath,managed:app.isPackaged,signal}),
    claimIntro:()=>claimSetupIntro(app.getPath('userData'))});}
  catch{preparingRuntime=false;app.quit();return;}
  const p = await port(); base = `http://127.0.0.1:${p}`;
  const logDir = path.join(dataRoot,'.log'); fs.mkdirSync(logDir, { recursive:true });
  const logPath = path.join(logDir,'service.log');
  if(fs.existsSync(logPath)&&fs.statSync(logPath).size>5_000_000)fs.renameSync(logPath,path.join(logDir,'service.previous.log'));
  const log = fs.openSync(logPath,'a');
  startBackend(p,log);
  let ready = false;
  for (let i=0;i<120;i++) {
    try { await api('GET','/health'); ready=true; break; } catch { await new Promise(r=>setTimeout(r,500)); }
  }
  if (!ready) { dialog.showErrorBox('声音服务未能启动', '请查看 '+logPath); app.quit(); return; }
  win = new BrowserWindow({ width:1440,height:900,minWidth:980,minHeight:650,title:'栖声 · Ambient Music Nonstop',icon:path.join(__dirname,'icon.ico'),backgroundColor:'#20292e',autoHideMenuBar:true,
    webPreferences:{ preload:path.join(__dirname,'preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true,backgroundThrottling:false } });
  // Keep the handoff alive until the player window actually exists.
  preparingRuntime=false;
  secureWindow(win,path.join(localRoot,'ui/index.html'),{allowAudioOutput:true});
  win.on('close',e=>{if(migrationBusy&&!quitting)e.preventDefault();else if(unsavedSettings){e.preventDefault();win.webContents.send('close-requested');}});
  win.loadFile(path.join(localRoot,'ui/index.html'));
  stopVisibility=watchVisibility(win,python,root);
  powerSaveBlocker.start('prevent-app-suspension');
});
app.on('window-all-closed',()=>{if(!preparingRuntime)app.quit();});
app.on('before-quit',event=> { if(migrationBusy||unsavedSettings){event.preventDefault();if(unsavedSettings)win?.webContents.send('close-requested');return;}quitting=true;stopVisibility?.();if (backend?.pid) execFile('taskkill',['/pid',String(backend.pid),'/t','/f'],{windowsHide:true},()=>{}); });
