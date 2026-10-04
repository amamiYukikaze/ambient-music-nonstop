import {installGlassMotion} from './glass-motion.js';
import {progressPanel,playSetupIntro,formatBytes} from './onboarding.js';
installGlassMotion();
const scan=document.getElementById('scan'),install=document.getElementById('install'),result=document.getElementById('result'),options=document.getElementById('install-options');
const panel=progressPanel(document.getElementById('runtime-progress'),{id:'runtime-meter',label:'当前安装步骤进度'});
const labels={uv:'安装工具',ace:'ACE 源码',sa3:'SA3 源码','ace-dependencies':'Python 与 ACE 依赖','backend-dependencies':'声音服务依赖','sa3-dependencies':'SA3 依赖','sa3-source':'SA3 组件',ffmpeg:'音频工具',health:'完整性与显卡检查'};
const phases={preparing:'正在准备',downloading:'正在下载',cached:'已验证缓存，正在复用',verifying:'正在校验',extracting:'正在解压',installing:'正在安装',checking:'正在检查','stage-done':'已完成',done:'正在进行启动复核'};
let state={status:'checking',stage:'health',phase:'checking'},allowed=false,downloadedPackages=0;
function render(event){
 if(event.type==='log'){
  const text=event.text;panel.log(text,{heading:labels[state.stage],level:/\b(error|failed)\b|失败/i.test(text)?'error':/warning/i.test(text)?'warning':'info'});
  if(/^\s*Downloaded /.test(text))downloadedPackages++;
  if(/^\s*(Downloading|Downloaded|Building|Built|Prepared|Installed|Resolved) /.test(text)){
   const label=/^\s*Download/.test(text)?`正在下载依赖，已完成 ${downloadedPackages} 项`:/^\s*Build/.test(text)?'正在构建本机依赖':'正在安装并整理依赖';
   panel.update({summary:`${labels[state.stage]||'运行环境'} · ${label}`,detail:text.trim(),completed:state.completed,stages:9});
  }return;
 }
 const previous=state.stage;state={...state,...event};
 if(event.reset){downloadedPackages=0;state.error=null;}
 if(event.intro)playSetupIntro(document.getElementById('runtime-setup'));
 if(state.root)document.getElementById('runtime-path').textContent=state.root;
 const busy=['checking','installing'].includes(state.status);options.hidden=busy;scan.disabled=busy;install.disabled=busy||!allowed;
 if(state.status==='failed')install.textContent='重试安装 →';
 let summary=state.status==='needs-install'?'先检查设备，再准备本地声音环境。':state.status==='failed'?'这一步没有完成，可以重试。':state.status==='checking'?'正在检查本地运行环境，请稍候。':`${phases[state.phase]||'正在处理'}${labels[state.stage]||'运行环境'}…`;
 const measured=['downloading','verifying','cached'].includes(state.phase)&&state.total>0;
 let detail=measured?`${state.file} · ${formatBytes(state.downloaded)} / ${formatBytes(state.total)} · ${(100*state.downloaded/state.total).toFixed(1)}%`:state.phase==='downloading'?`${state.file} · 已接收 ${formatBytes(state.downloaded)}，正在等待完整大小`:state.status==='failed'?state.error:state.status==='needs-install'?'依赖安装与模型下载会分别显示进度。':state.stage==='health'?'正在核验源码、依赖导入和 CUDA；首次检查可能需要几分钟。':'完成当前步骤后将继续。';
 panel.update({summary,detail,current:measured?state.downloaded:null,total:measured?state.total:null,completed:Math.min(8,state.completed||0),stages:busy&&state.status!=='checking'?9:null,active:busy,error:state.status==='failed'});
 if(state.status==='failed'&&event.type==='state')panel.log(state.error,{heading:labels[state.stage],level:'error'});
}
scan.onclick=async()=>{scan.disabled=true;try{const h=await window.runtime.scan();allowed=h.allowed;result.textContent=`内存 ${h.ram.toFixed(1)} GB · NVIDIA 显存 ${h.vram.toFixed(1)} GB · ${h.allowed?h.sa3?'支持 ACE 与 SA3':'支持 ACE；SA3 不满足要求，无法选择':'未达到最低要求，已阻止安装。可关闭窗口，或更新驱动后重试检查。'}`;document.getElementById('sa3-guidance').hidden=!h.sa3;install.disabled=!allowed;}catch(e){result.textContent=e.message;}finally{scan.disabled=false;}};
document.getElementById('runtime-hf-help').onclick=()=>window.runtime.hfHelp().catch(e=>{result.textContent=e.message;});
install.onclick=async()=>{try{install.disabled=true;scan.disabled=true;await window.runtime.install();}catch(e){result.textContent=e.message;install.disabled=!allowed;scan.disabled=false;}};
window.runtime.progress(render);
render(await window.runtime.state());
