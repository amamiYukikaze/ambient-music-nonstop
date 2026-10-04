const {pathToFileURL}=require('node:url');
function assertSender(event,win,file){
 let trusted=false;
 try{trusted=Boolean(win&&!win.isDestroyed()&&event.sender===win.webContents&&event.senderFrame===win.webContents.mainFrame&&event.senderFrame?.url===pathToFileURL(file).href);}catch{}
 if(!trusted)throw Error('Untrusted IPC sender');
}
function trustedHandlers(ipc,getWindow,file){
 return {
  handle(channel,handler){ipc.handle(channel,(event,...args)=>{assertSender(event,getWindow(),file);return handler(event,...args);});},
  on(channel,handler){ipc.on(channel,(event,...args)=>{try{assertSender(event,getWindow(),file);}catch{return;}handler(event,...args);});},
 };
}
function secureWindow(win,file,{allowAudioOutput=false}={}){
 const contents=win.webContents,url=pathToFileURL(file).href;
 contents.setWindowOpenHandler(()=>({action:'deny'}));
 for(const event of ['will-navigate','will-frame-navigate','will-redirect','will-attach-webview'])contents.on(event,e=>e.preventDefault());
 const permitted=(sender,permission,details)=>Boolean(allowAudioOutput&&!win.isDestroyed()&&sender===contents&&permission==='speaker-selection'&&details?.isMainFrame===true&&details.requestingUrl===url&&contents.mainFrame.url===url);
 contents.session.setPermissionCheckHandler((sender,permission,_origin,details)=>permitted(sender,permission,details));
 contents.session.setPermissionRequestHandler((sender,permission,callback,details)=>callback(permitted(sender,permission,details)));
 contents.session.setDevicePermissionHandler(()=>false);
}
module.exports={trustedHandlers,secureWindow};
