const {app,BrowserWindow,ipcMain}=require('electron');
const path=require('node:path');
const {trustedHandlers,secureWindow}=require('./security.cjs');
exports.createStartup=localRoot=>{
 const controller=new AbortController();let finished=false,state={phase:'metadata'};
 const page=path.join(localRoot,'ui/startup.html');
 const win=new BrowserWindow({width:620,height:420,minWidth:480,minHeight:360,show:false,backgroundColor:'#152a35',autoHideMenuBar:true,icon:path.join(__dirname,'icon.ico'),webPreferences:{preload:path.join(__dirname,'startup-preload.cjs'),sandbox:true,contextIsolation:true,nodeIntegration:false}});
 secureWindow(win,page);
 trustedHandlers(ipcMain,()=>win,page).handle('startup-state',()=>state);
 const timer=setTimeout(()=>{if(!win.isDestroyed())win.show();},200);
 win.on('closed',()=>{clearTimeout(timer);ipcMain.removeHandler('startup-state');if(!finished){controller.abort();app.quit();}});
 win.loadFile(page);
 return {signal:controller.signal,update:event=>{state=event;if(!win.isDestroyed())win.webContents.send('startup-progress',state);},
  finish:()=>{finished=true;clearTimeout(timer);if(!win.isDestroyed())win.close();}};
};
