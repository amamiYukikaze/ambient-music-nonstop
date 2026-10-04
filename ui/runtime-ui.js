import {installGlassMotion} from './glass-motion.js';
installGlassMotion();
const scan=document.getElementById('scan'),install=document.getElementById('install'),result=document.getElementById('result'),log=document.getElementById('log');
scan.onclick=async()=>{try{const h=await window.runtime.scan();result.textContent=`内存 ${h.ram.toFixed(1)} GB · NVIDIA 显存 ${h.vram.toFixed(1)} GB · ${h.allowed?'符合应用最低门槛':'不满足要求，无法继续'}`;install.disabled=!h.allowed;}catch(e){result.textContent=e.message;}};
install.onclick=async()=>{try{install.disabled=true;document.getElementById('progress').hidden=false;await window.runtime.install();}catch(e){result.textContent=e.message;install.disabled=false;}};
window.runtime.progress(line=>{log.textContent=(log.textContent+line).slice(-12000);log.scrollTop=log.scrollHeight;if(line.includes('安装失败')){install.disabled=false;document.getElementById('progress').hidden=true;}});
