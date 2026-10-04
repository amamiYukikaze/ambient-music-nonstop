/** Rasterize the editable SVG once and encode standard PNG-backed Windows ICO sizes. */
const {app,BrowserWindow}=require('electron');
const fs=require('node:fs'),path=require('node:path');
app.whenReady().then(async()=>{
 const root=path.resolve(__dirname,'..'),svg=fs.readFileSync(path.join(root,'ui/assets/brand.svg'),'utf8');
 const win=new BrowserWindow({show:false,width:1024,height:1024,transparent:true,webPreferences:{offscreen:true,contextIsolation:true,sandbox:true}});
 await win.loadURL('data:text/html;charset=utf-8,'+encodeURIComponent(`<style>html,body{margin:0;width:1024px;height:1024px;background:transparent;overflow:hidden}svg{display:block;width:1024px;height:1024px}</style>${svg}`));
 await win.webContents.executeJavaScript('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');
 const source=await win.webContents.capturePage({x:0,y:0,width:1024,height:1024});
 fs.writeFileSync(path.join(root,'ui/assets/brand.png'),source.resize({width:1024,height:1024,quality:'best'}).toPNG());
 fs.writeFileSync(path.join(root,'desktop/icon.png'),source.resize({width:256,height:256,quality:'best'}).toPNG());
 const sizes=[16,24,32,48,64,128,256],images=sizes.map(size=>source.resize({width:size,height:size,quality:'best'}).toPNG());
 const header=Buffer.alloc(6+16*sizes.length);header.writeUInt16LE(1,2);header.writeUInt16LE(sizes.length,4);let offset=header.length;
 images.forEach((image,i)=>{const pos=6+i*16,size=sizes[i];header[pos]=header[pos+1]=size===256?0:size;header.writeUInt16LE(1,pos+4);header.writeUInt16LE(32,pos+6);header.writeUInt32LE(image.length,pos+8);header.writeUInt32LE(offset,pos+12);offset+=image.length;});
 fs.writeFileSync(path.join(root,'desktop/icon.ico'),Buffer.concat([header,...images]));
 console.log('Standing-crane SVG rasterized to PNG and seven ICO sizes.');win.destroy();app.quit();
}).catch(e=>{console.error(e);app.exit(1);});
