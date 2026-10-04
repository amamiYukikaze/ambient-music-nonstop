const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('ambient', {
  request: (method, path, body) => ipcRenderer.invoke('api', method, path, body),
  audio: (kind, id) => ipcRenderer.invoke('audio', kind, id),
  window: action => ipcRenderer.invoke('window', action),
  chooseLibraryFolder: () => ipcRenderer.invoke('choose-library-folder'),
  chooseFolder: () => ipcRenderer.invoke('choose-folder'),
  chooseImport: kind => ipcRenderer.invoke('choose-import',kind),
  image: id => ipcRenderer.invoke('image',id),
  hfHelp: () => ipcRenderer.invoke('hf-help'),
  brightness: request => ipcRenderer.invoke('brightness',request),
  claimSetupIntro: () => ipcRenderer.invoke('setup-intro'),
  setUnsaved: value => ipcRenderer.send('unsaved-settings',value),
  onCloseRequest: fn => {const listener=()=>fn();ipcRenderer.on('close-requested',listener);return ()=>ipcRenderer.removeListener('close-requested',listener);},
  onVisibility: fn => {const listener=(_,visible)=>fn(Boolean(visible));ipcRenderer.on('visibility',listener);return ()=>ipcRenderer.removeListener('visibility',listener);},
});
