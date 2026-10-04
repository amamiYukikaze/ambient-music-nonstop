const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {EventEmitter}=require('node:events');
const {pathToFileURL}=require('node:url');
const root=path.resolve(__dirname,'..');

for(const [file,namespace,method,channel,payload,expected] of [
 ['preload.cjs','ambient','onCloseRequest','close-requested',[],[]],
 ['preload.cjs','ambient','onVisibility','visibility',[true],[true]],
 ['runtime-preload.cjs','runtime','progress','runtime-progress',['progress'],['progress']],
])test(`${file} ${method} does not expose IPC event or emitter`,()=>{
 const ipcRenderer=new EventEmitter();let api;
 vm.runInNewContext(fs.readFileSync(path.join(root,'desktop',file),'utf8'),{require:()=>({ipcRenderer,contextBridge:{exposeInMainWorld(name,value){assert.equal(name,namespace);api=value;}}})});
 let received;const unsubscribe=api[method]((...args)=>received=args);
 ipcRenderer.emit(channel,{sender:'raw native IPC event'},...payload);
 assert.deepEqual(received,expected);
 assert.equal(typeof unsubscribe,'function');unsubscribe();
 assert.equal(ipcRenderer.listenerCount(channel),0);
});

test('IPC handlers reject other windows, subframes and navigated documents',()=>{
 const {trustedHandlers}=require('../desktop/security.cjs');
 const file=path.join(root,'ui/index.html');
 const frame={url:pathToFileURL(file).href};const contents={mainFrame:frame};
 const win={webContents:contents,isDestroyed:()=>false};
 const events=new EventEmitter(),calls={};events.handle=(channel,fn)=>calls[channel]=fn;
 let mutations=0;const guarded=trustedHandlers(events,()=>win,file);
 guarded.handle('invoke',()=>++mutations);guarded.on('event',()=>++mutations);
 const valid={sender:contents,senderFrame:frame};
 assert.equal(calls.invoke(valid),1);
 for(const invalid of [{sender:{},senderFrame:frame},{sender:contents,senderFrame:{url:frame.url}},{sender:contents,senderFrame:null}]){
  assert.throws(()=>calls.invoke(invalid),/Untrusted IPC sender/);events.emit('event',invalid);
 }
 frame.url='https://example.com/';assert.throws(()=>calls.invoke(valid),/Untrusted IPC sender/);
 events.emit('event',valid);assert.equal(mutations,1);
});

test('both windows block navigation, popups and unnecessary permissions',()=>{
 const {secureWindow}=require('../desktop/security.cjs');
 const file=path.join(root,'ui/index.html'),url=pathToFileURL(file).href;
 for(const allowAudioOutput of [false,true]){
  const contents=new EventEmitter(),handlers={};
  contents.mainFrame={url};contents.setWindowOpenHandler=fn=>handlers.open=fn;
  contents.session={setPermissionRequestHandler:fn=>handlers.request=fn,setPermissionCheckHandler:fn=>handlers.check=fn,setDevicePermissionHandler:fn=>handlers.device=fn};
  const win={webContents:contents,isDestroyed:()=>false};secureWindow(win,file,{allowAudioOutput});
  assert.equal(handlers.open().action,'deny');assert.equal(handlers.device({}),false);
  for(const name of ['will-navigate','will-frame-navigate','will-redirect','will-attach-webview']){
   let prevented=false;contents.emit(name,{preventDefault(){prevented=true;}});assert(prevented,name);
  }
  const details={isMainFrame:true,requestingUrl:url};
  for(const permission of ['media','geolocation','notifications','openExternal','clipboard-read'])assert.equal(handlers.check(contents,permission,'file://',details),false);
  assert.equal(handlers.check(contents,'speaker-selection','file://',details),allowAudioOutput);
  assert.equal(handlers.check(contents,'speaker-selection','file://',{...details,isMainFrame:false}),false);
  let accepted;handlers.request(contents,'media',value=>accepted=value,details);assert.equal(accepted,false);
 }
});
