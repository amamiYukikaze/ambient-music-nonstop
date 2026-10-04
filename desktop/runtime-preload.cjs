const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('runtime',{scan:()=>ipcRenderer.invoke('runtime-scan'),install:()=>ipcRenderer.invoke('runtime-install'),progress:fn=>{const listener=(_,line)=>fn(String(line));ipcRenderer.on('runtime-progress',listener);return ()=>ipcRenderer.removeListener('runtime-progress',listener);}});
