const fs=require('node:fs'),path=require('node:path'),{execFile}=require('node:child_process');
// Electron can read its ASAR; an external PowerShell process cannot. Send the
// trusted script as encoded text, with user values passed separately in env.
exports.brightness=async(request={})=>{
 if(process.platform!=='win32')return {supported:false,monitors:[],reason:'当前系统不支持 Windows 屏幕背光接口'};
 if(request.id!==undefined&&(typeof request.id!=='string'||request.id.length>500||!Number.isInteger(request.value)||request.value<0||request.value>100))throw Error('无效的亮度设置');
 const script=fs.readFileSync(path.join(__dirname,'brightness.ps1'),'utf8');
 const args=['-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-EncodedCommand',Buffer.from(script,'utf16le').toString('base64')];
 const env={...process.env,AMBIENT_BRIGHTNESS_INSTANCE:request.id||'',AMBIENT_BRIGHTNESS_LEVEL:String(request.id===undefined?-1:request.value)};
 return new Promise((resolve,reject)=>execFile('powershell.exe',args,{env,windowsHide:true,timeout:15000,encoding:'utf8'},(error,out)=>{
  if(error){reject(Error(request.id===undefined?'亮度检测未能完成，请重试。Windows 背光接口或检测脚本执行失败。':'Windows 未接受亮度调整，请重新检测屏幕。'));return;}
  try{const value=JSON.parse(out.trim()||'[]'),monitors=Array.isArray(value)?value:value?[value]:[];resolve({supported:monitors.length>0,monitors,reason:monitors.length?'':'未检测到支持 Windows WMI 调光的屏幕；外接屏 DDC/CI 暂未支持'});}
  catch{reject(Error('亮度接口返回的数据无法读取，请重试'));}
 }));
};
