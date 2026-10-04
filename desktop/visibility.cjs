const {spawn}=require('node:child_process');
const path=require('node:path');
const {powerMonitor}=require('electron');
function watchVisibility(win,python,root){
 let child,timer,buffer='',occluded=false,locked=false,stopped=false,last;
 const publish=()=>{if(win.isDestroyed())return;const visible=win.isVisible()&&!win.isMinimized()&&!occluded&&!locked;if(visible!==last){last=visible;win.webContents.send('visibility',visible);}};
 const lock=()=>{locked=true;publish();},unlock=()=>{locked=false;publish();};
 powerMonitor.on('lock-screen',lock);powerMonitor.on('unlock-screen',unlock);
 const launch=()=>{if(stopped||win.isDestroyed())return;
  const h=win.getNativeWindowHandle(),hwnd=h.length>=8?h.readBigUInt64LE().toString():String(h.readUInt32LE());
  child=spawn(python,['-u',path.join(root,'scripts/window_visibility.py'),hwnd],{windowsHide:true,stdio:['ignore','pipe','ignore']});
  buffer='';child.stdout.on('data',chunk=>{buffer+=chunk;const lines=buffer.split('\n');buffer=lines.pop();for(const line of lines){try{occluded=!JSON.parse(line).visible;publish();}catch{}}});
  child.on('error',()=>{occluded=false;publish();});
  child.on('exit',()=>{if(!stopped){occluded=false;publish();timer=setTimeout(launch,5000);}});
 };
 for(const event of ['restore','show','minimize','hide'])win.on(event,publish);
 win.webContents.on('did-finish-load',()=>{last=undefined;publish();});
 if(process.platform==='win32')launch();publish();
 return ()=>{stopped=true;clearTimeout(timer);child?.kill();powerMonitor.removeListener('lock-screen',lock);powerMonitor.removeListener('unlock-screen',unlock);};
}
module.exports={watchVisibility};
