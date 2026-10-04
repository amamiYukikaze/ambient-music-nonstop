const summary=document.getElementById('startup-summary'),detail=document.getElementById('startup-detail'),meter=document.getElementById('startup-progress');
const steps={'source-ace':'ACE 源码校验','source-sa3':'SA3 源码校验','environment-base':'Python / ACE 依赖与 CUDA','environment-sa3':'SA3 依赖与 CUDA',ffmpeg:'FFmpeg 校验',ffprobe:'FFprobe 校验',dependencies:'依赖完整性',complete:'完整检查完成'};
function render(state){
 meter.removeAttribute('value');
 if(state.phase==='deep'){
  summary.textContent='运行环境首次复核或发生变化，正在完整检查';
  detail.textContent=steps[state.stage]||'正在重新验证；通过后将更新快速启动记录。';
  if(state.stages){meter.max=state.stages;meter.value=state.completed;detail.textContent+=` · ${state.completed} / ${state.stages} 项完成（不是预计耗时）`;}
 }else if(state.phase==='inventory'){
  summary.textContent='检查运行文件是否发生变化';detail.textContent=`已检查 ${(state.files||0).toLocaleString()} 个文件，不重复导入模型依赖。`;
 }else if(state.phase==='driver'){
  summary.textContent='确认显卡与驱动';detail.textContent='驱动或设备变化时会重新执行完整检查。';
 }else if(state.phase==='backend'){
  summary.textContent='正在启动本地声音服务';detail.textContent='运行环境已就绪，正在等待本地服务响应。';
 }else{summary.textContent='检查本地运行环境';detail.textContent='确认安装记录与运行环境版本。';}
 meter.setAttribute('aria-valuetext',summary.textContent+'，'+detail.textContent);
}
window.startup.progress(render);window.startup.state().then(render);
