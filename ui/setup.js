import {mixEditor} from './mix-editor.js';
import {recoverStartup} from './startup-recovery.js';
import {progressPanel,summaryText,playSetupIntro,formatBytes} from './onboarding.js';
const pause=ms=>new Promise(r=>setTimeout(r,ms));
export async function ensureSetup(api){
 await recoverStartup(api);
 let status=await api('GET','/setup');if(status.setup.complete){document.body.classList.remove('setup-pending');return;}
 const dialog=document.createElement('dialog');dialog.className='management-page setup-page';dialog.id='first-setup';dialog.setAttribute('aria-label','首次设置');
 dialog.innerHTML=`<header><div><p class="eyebrow">WELCOME TO YOUR SOUNDING HOME</p><h2>先为声音，安一个家。</h2></div><span class="setup-orbit" aria-hidden="true"><img class="brand-emblem" src="assets/brand.svg" alt=""></span></header><ol class="setup-steps"><li>设备</li><li>模型</li><li>曲库</li><li>第一首</li></ol><section id="setup-content" class="scroll-area"></section><p id="setup-message" role="status"></p>`;document.body.append(dialog);dialog.addEventListener('cancel',e=>e.preventDefault());dialog.showModal();
 const content=dialog.querySelector('#setup-content'),message=dialog.querySelector('#setup-message');
 if(await window.ambient.claimSetupIntro())playSetupIntro(dialog);
 function stage(n){dialog.querySelectorAll('.setup-steps li').forEach((e,i)=>e.classList.toggle('active',i<=n));}
 function error(e){summaryText(message,e.message||String(e));}
 function button(text,action){const b=document.createElement('button');b.className='glass';b.textContent=text;b.onclick=async()=>{b.disabled=true;message.textContent='';try{await action();}catch(e){error(e);}finally{b.disabled=false;}};return b;}
 let release;const finished=new Promise(r=>release=r);
 function firstProgress(){
  stage(3);content.innerHTML='<div class="setup-listening"><div class="transfer-orbit"><img class="brand-emblem" src="assets/brand.svg" alt=""></div><h3>一段声音，正在成为这个房间的一部分。</h3><p id="first-job-status">正在生成第一首音乐…</p><p class="fine">通过完整性、响度和重复检查后才能进入。失败会保留原因，可重试或返回调整。</p></div>';
  const progress=progressPanel(content,{label:'首曲准备状态'});let alive=true;
  (async()=>{while(alive){try{status=await api('GET','/setup');const job=status.first_job;
   const summary=status.setup.complete?'第一首音乐已入库，自动补库已开启。':job?.status==='processing'?'正在检查音频、统一响度与建立曲库…':job?.status==='queued'?'首曲任务已排队，即将开始…':'正在生成第一首音乐…';
   content.querySelector('#first-job-status').hidden=true;
   progress.update({summary,active:!status.setup.complete,detail:status.setup.complete?'可进入播放器，之后也可以在设置中暂停补库。':'生成与质检耗时取决于设备，完成前请保持应用打开。'});progress.log(summary,{heading:'首曲生成与质检',deduplicate:true});
   if(status.setup.complete){alive=false;content.append(button('走进声音里 →',()=>{dialog.close();document.body.classList.remove('setup-pending');release();}));return;}
   if(job&&['failed','cancelled'].includes(job.status)){alive=false;progress.update({summary:'首曲未能完成，可以返回重试。',detail:job.error||'任务已取消',active:false,error:true});progress.log(`${job.error_code} · ${job.error}`,{level:'error'});content.append(button('返回曲风设置，重试',library));return;}
  }catch(e){error(e);}await pause(1200);}})();
 }
 async function library(){
  stage(2);const {config}=await api('GET','/configuration');const sa3=config.setup.models?.includes('stable-audio-3-medium');const styles=config.styles.filter(s=>sa3||s.id!=='guzheng');
  content.innerHTML='<h3>选择要留在房间里的声音</h3><p class="fine">拖动一项时，其他未固定的项目按原比例共同让出或补回。未选曲风不会自动生成。</p><div id="setup-style-checks" class="choice-grid"></div><div id="setup-mix"></div><label class="field-label">音乐保存位置</label><output id="setup-library-path" class="path-display"></output><div id="setup-library-actions" class="inline-actions"></div>';
  let path=config.settings.library_path;content.querySelector('#setup-library-path').textContent=path;
  let selected=new Set(styles.filter(s=>config.settings.enabled_styles.includes(s.id)).map(s=>s.id));if(!selected.size)selected=new Set(styles.map(s=>s.id));
  let editor;const draft={...config.settings.style_weights};const rebuild=()=>{const active=styles.filter(s=>selected.has(s.id)),pins=editor?.pins||config.settings.style_pins||[];if(editor)Object.assign(draft,editor.values);editor=mixEditor(content.querySelector('#setup-mix'),active,draft,{pins});};
  for(const s of styles){const label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.checked=selected.has(s.id);check.onchange=()=>{check.checked?selected.add(s.id):selected.delete(s.id);rebuild();};label.append(check,document.createTextNode(s.name));content.querySelector('#setup-style-checks').append(label);}rebuild();
  const actions=content.querySelector('#setup-library-actions');actions.append(button('选择空目录…',async()=>{const p=await window.ambient.chooseFolder();if(p){path=p;content.querySelector('#setup-library-path').textContent=p;}}),button('返回模型',models),button('生成第一首 →',async()=>{const weights=Object.fromEntries(config.styles.map(s=>[s.id,editor.values[s.id]||0]));await api('POST','/setup/first',{library_path:path,weights,enabled:[...selected],pins:editor.pins});firstProgress();}));
 }
 async function models(){
  stage(1);const {config}=await api('GET','/configuration');let hw=config.setup.hardware;if(!hw?.ace){device();return;}
  content.innerHTML=`<h3>让旋律在本机生长</h3><p class="fine">ACE Turbo 是基础模型。SA3 需要在 Hugging Face 接受条款并获得访问权限；账户登录与模型授权是两件事。Token 仅用于本次下载，不写入应用配置。</p><label class="choice"><input id="setup-sa3" type="checkbox" ${hw.sa3?'checked':'disabled'}>使用 Stable Audio 3 Medium${hw.sa3?'':' · 设备未达支持门槛'}</label><label class="choice"><input id="setup-sft" type="checkbox">同时下载 ACE-Step SFT（可选）</label><p class="fine">只使用 ACE 时，空谷听泉禁用，其余曲风使用 Turbo。已有完整模型可选择同一总目录进行校验。</p><div class="inline-actions" id="hf-actions"></div><label class="field-label">Hugging Face 只读 Token（可留空，使用本机 HF 登录）<input id="setup-token" type="password" autocomplete="off" spellcheck="false"></label><label class="field-label">模型总目录<output id="setup-model-dir" class="path-display"></output></label><label class="choice"><input id="setup-local" type="checkbox">仅校验已有文件</label><div class="inline-actions" id="model-actions"></div><progress id="setup-download" max="100" value="0"></progress><p id="setup-download-detail" class="fine"></p>`;
  let path=config.paths.models;content.querySelector('#setup-model-dir').textContent=path;content.querySelector('#hf-actions').append(button('打开 SA3 授权页面 ↗',()=>window.ambient.hfHelp()));
  const consent=document.createElement('label');consent.className='choice';consent.innerHTML='<input id="setup-sa3-authorized" type="checkbox">已在 HF 模型页确认获得 SA3 访问权限（仅登录不够）';content.querySelector('#hf-actions').after(consent);
  const sa3Choice=content.querySelector('#setup-sa3');consent.hidden=!sa3Choice.checked;sa3Choice.addEventListener('change',()=>{consent.hidden=!sa3Choice.checked;});
  const actions=content.querySelector('#model-actions');actions.append(button('选择模型目录…',async()=>{const p=await window.ambient.chooseFolder();if(p){path=p;content.querySelector('#setup-model-dir').textContent=p;}}));
  content.querySelector('#setup-download').remove();content.querySelector('#setup-download-detail').remove();
  const progress=progressPanel(content,{id:'model-meter',label:'模型文件准备进度'});
  progress.update({summary:'选择模型位置后，开始下载或校验。',active:false});
  const phaseLabels={manifest:'正在读取模型文件清单…',verifying:'正在校验模型文件…',downloading:'正在下载模型文件…',done:'模型已就绪，可以继续。',failed:'模型准备未完成，可以重试。'};
  async function monitor(){
   const controls=[...content.querySelectorAll('button,input')],previous=controls.map(n=>n.disabled);controls.forEach(n=>n.disabled=true);
   let last='';
   try{while(progress.element.isConnected){const s=await api('GET','/setup'),d=s.download;
    const detail=d.error||`${d.file||''}${d.total?` · ${formatBytes(d.downloaded)} / ${formatBytes(d.total)}`:''}${d.eta_seconds==null?'':` · 约 ${Math.max(1,Math.ceil(d.eta_seconds/60))} 分钟`}`;
    progress.update({summary:phaseLabels[d.phase]||'等待模型准备…',detail,current:d.downloaded,total:d.total,active:d.active,error:d.phase==='failed'});
    const key=`${d.phase}:${d.file||''}:${d.error||''}`;if(key!==last){last=key;progress.log(detail||phaseLabels[d.phase],{heading:phaseLabels[d.phase],level:d.error?'error':'info'});}
    if(!d.active){if(d.phase==='done'){actions.append(button('模型已就绪，继续 →',library));return;}if(d.error)throw Error(d.error);return;}await pause(700);
   }}finally{controls.forEach((n,i)=>{if(n.isConnected)n.disabled=previous[i];});}
  }
  actions.append(button('下载 / 验证模型',async()=>{if(sa3Choice.checked&&!content.querySelector('#setup-sa3-authorized').checked)throw Error('请先打开 SA3 模型页，登录并确认已获得访问权限；也可取消 SA3，仅使用 ACE。');const models=['acestep-v15-turbo'];if(sa3Choice.checked)models.push('stable-audio-3-medium');if(content.querySelector('#setup-sft').checked)models.push('acestep-v15-sft');const input=content.querySelector('#setup-token'),token=input.value;input.value='';await api('POST','/setup/models',{models,directory:path,token:token||null,local_only:content.querySelector('#setup-local').checked});await monitor();}));
  const s=await api('GET','/setup');if(s.download.active)monitor().catch(error);else if(config.setup.models_verified)actions.append(button('使用已验证模型，继续 →',library));
 }
 function device(){stage(0);content.innerHTML='<h3>先了解这个房间的设备</h3><p class="management-intro">允许读取 CPU、内存容量、NVIDIA 显卡/驱动和磁盘可用空间吗？只在本机检查并保存结果，不上传设备信息。模型下载将连接 Hugging Face。</p><div class="requirement-grid"><article><h4>ACE-Step 1.5 Turbo</h4><p>Windows 10/11 x64<br>NVIDIA CUDA 显存 ≥4 GB<br>系统内存 ≥16 GB</p></article><article><h4>Stable Audio 3 Medium</h4><p>本应用保守支持门槛<br>NVIDIA 显存 ≥6 GB · 内存 ≥24 GB<br>运行时约需 16 GB 可用内存</p></article></div><p class="fine">暂不支持 AMD / Intel GPU、macOS、Linux 或纯 CPU 新安装。模型与运行环境另占空间，下载前会检查实际清单。</p><div id="scan-actions" class="inline-actions"></div><p id="hardware-result"></p>';
  content.querySelector('#scan-actions').append(button('允许扫描设备',async()=>{const h=await api('POST','/setup/scan',{consent:true});content.querySelector('#hardware-result').textContent=`内存 ${h.ram_gb.toFixed(1)} GB · ${h.gpus.map(g=>g.name+' '+g.vram_gb.toFixed(1)+' GB').join(' / ')||'未检测到支持的 NVIDIA 显卡'}`;if(!h.ace){message.textContent='当前设备不满足本应用最低要求，无法继续。可在更换设备或安装显卡驱动后重试。';return;}content.querySelector('#scan-actions').append(button('继续选择模型 →',models));}),button('暂不允许',()=>{message.textContent='未读取设备信息。完成设备检查后才能继续设置；可直接关闭窗口。';}));
 }
 if(status.first_job&&['queued','running','processing','done'].includes(status.first_job.status))firstProgress();else if(status.setup.hardware?.ace)await models();else device();
 await finished;
}
