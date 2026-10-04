const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('startup',{
 state:()=>ipcRenderer.invoke('startup-state'),
 progress:callback=>{if(typeof callback!=='function')return()=>{};const listener=(_event,value)=>callback(value);ipcRenderer.on('startup-progress',listener);return()=>ipcRenderer.removeListener('startup-progress',listener);}
});
