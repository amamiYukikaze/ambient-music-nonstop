import {installGlassMotion} from './glass-motion.js';
import {sharedTransport} from './shared-transport.js';
import {roomClock} from './clock.js';
installGlassMotion();
import {attachHomeBrightness} from './home-brightness.js';
import {ensureSetup} from './setup.js';
import {registerCustomScenes} from './custom-scenes.js';
await ensureSetup((method,path,body)=>window.ambient.request(method,path,body));
import {librarySettings} from './library-settings.js';
import {initializeFraming} from './framing.js';
import {RoomAudio} from './audio.js';
import {OutputDevices} from './output-devices.js';
import {visuals} from './visuals.js';
import {morphText,reconcile,select,popover,pages} from './motion.js';
import {styleBubbles} from './style-bubbles.js';
import {SCENES,SCENE_OPTIONS,chooseScene} from './scenes.js';
import {transportIcons} from './icons.js';
import {renderDistribution} from './pool-chart.js';
transportIcons();
const $=id=>document.getElementById(id),api=(method,path,body)=>window.ambient.request(method,path,body);
let preferences={};try{preferences=JSON.parse(localStorage.getItem('room-preferences')||'{}');}catch{}
let management;
initializeFraming(SCENES);
let state,toastTimer,weatherMode=preferences.weather||'auto',sceneMode=preferences.scene||'auto',sceneToken=0,currentScene;
const save=()=>localStorage.setItem('room-preferences',JSON.stringify(preferences));
if(sceneMode!=='auto'&&!SCENES[sceneMode]&&!/^custom_[a-f0-9]{32}$/.test(sceneMode)){sceneMode='auto';preferences.scene='auto';save();}
// One-time requested volume migration; later deliberate volume choices are preserved.
if(preferences.volumeRevision!==3){preferences.volume=50;preferences.volumeRevision=3;save();}
const layers=new Map(),quick=new Map(),selectors={},navigation=pages();
const make=(tag,text,cls)=>{const el=document.createElement(tag);if(text!=null)el.textContent=text;if(cls)el.className=cls;return el;};
const text=(id,value)=>morphText($(id),value);
function toast(message){text('toast',message);$('toast').classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').classList.remove('visible'),5000);}
function weather(){if(weatherMode!=='auto')return weatherMode;if(layers.get('snow')>0)return 'snow';if(layers.get('fireflies')>0)return 'fireflies';return layers.get('rain')>0||layers.get('thunder')>0?'rain':'none';}
const audio=new RoomAudio(api,toast,()=>{if(!audio.blocked){preferences.playing=audio.playing;save();}renderPlayback();refresh().catch(e=>toast(e.message));});
audio.setVolume(Math.max(0,Math.min(100,Number(preferences.volume)||0))/100);
if(preferences.style)audio.style=({bright_piano:'daily_piano',hybrid:'orchestral'})[preferences.style]||preferences.style;
const canvas=visuals(audio,weather,()=>currentScene||'rain',()=>preferences.effects!==false),fmt=n=>`${String(Math.floor(n/60)).padStart(2,'0')}:${String(Math.floor(n%60)).padStart(2,'0')}`;
export {audio,navigation,canvas as visualEngine};
const sceneNames={beach:['沙滩','≈'],ocean:['海洋','≋'],birds:['鸟鸣','♧'],campfire:['篝火','♨'],fireplace:['壁炉','♨'],forest:['森林','♧'],rain:['屋檐大雨','☂'],stream:['溪流','⌁'],fireflies:['萤火虫','✧'],snow:['大雪','❄'],train:['火车','▣'],wind:['风声','〰'],thunder:['雷声','ϟ']};
function renderPlayback(){
 if(state){const variant=state.styles.find(s=>s.id===audio.style)?.model_variant;const canGenerate=state.models?.some(m=>m.id===variant&&m.installed&&m.eligible);$('generate').disabled=!canGenerate;$('generate').title=canGenerate?'为当前风格生成三首音乐':'需先通过设备检查并安装对应模型';}
 const track=audio.current?.track;for(const id of ['play']){$(id).classList.toggle('is-playing',audio.playing);$(id).setAttribute('aria-label',audio.playing?'暂停播放':'开始播放');}
 text('play-status',track?(audio.playing?'NOW PLAYING · 本地生成':'PAUSED · 稍作停留'):'等待一段新的声音');
 const title=state?.styles.find(s=>s.id===(track?.style||audio.style))?.name||'窗边咖啡';text('track-title',title);text('mini-track',title);
 const tempo=track?.metadata.timesignature_requested==='free'?'散板 · 自由呼吸':`${track?.metadata.bpm_requested} BPM`;
 text('track-info',track?`${track.metadata.model} · ${tempo} · ${track.metadata.qc.final.lufs.toFixed(1)} LUFS · ${track.plays}/${state?.settings.plays_before_retire||4} 次`:`${state?.styles.find(s=>s.id===audio.style)?.subtitle||'本地生成'} · 本地音乐库`);$('delete').disabled=!track;
}
function setLayer(id,value){
 layers.set(id,value);preferences.layers=Object.fromEntries(layers);save();audio.layer(id,value).catch(e=>{if(layers.get(id)!==value)return;layers.set(id,0);preferences.layers=Object.fromEntries(layers);save();toast(e.message);drawLayers();updateScene();});drawLayers();updateScene();
}
async function updateScene(){
 const hour=new Date().getHours(),dominant=[...layers].filter(([,v])=>v>0).sort((a,b)=>b[1]-a[1])[0]?.[0];
 const mode=sceneMode==='auto'?chooseScene({hour,dominant,weather:weather(),style:audio.style}):(SCENES[sceneMode]?sceneMode:'morning');
 const token=++sceneToken;if(mode===currentScene)return;let image=document.querySelector(`[data-scene="${mode}"]`);
 if(!image){image=document.createElement('img');image.className='wallpaper';image.dataset.scene=mode;image.alt='';image.src=SCENES[mode].custom?URL.createObjectURL(new Blob([await window.ambient.image(mode)],{type:'image/webp'})):`assets/${SCENES[mode].asset}.png`;document.querySelector('#wallpaper-stack').insertBefore(image,$('scene-fx'));}
 try{await image.decode();}catch{toast('这张风景暂时未能加载。');return;}if(token!==sceneToken)return;
 currentScene=mode;document.querySelectorAll('.wallpaper').forEach(el=>el.classList.toggle('selected',el===image));
 // Retain both sides of the crossfade, then release old full-size decodes.
 setTimeout(()=>{if(token===sceneToken)document.querySelectorAll('.wallpaper:not(.selected)').forEach(el=>{if(el.src.startsWith('blob:'))URL.revokeObjectURL(el.src);el.remove();});},2800);
 document.body.dataset.scene=mode;text('scene-title',SCENES[mode].name);updateQuote();
}
let quoteIndex=0;
function updateQuote(){const scene=SCENES[currentScene||'rain'];text('room-quote',scene.quotes[quoteIndex%scene.quotes.length]);}
setInterval(()=>{quoteIndex++;updateQuote();},90000);
function renderActivity(running,pending){
 const phase=running?.status||'idle',message=running?(phase==='processing'?'正在质检与整理':'正在酝酿新旋律'):`${pending} 项等待中`;
 const box=$('queue-activity');box.dataset.phase=phase;box.classList.toggle('active',Boolean(running));
 if($('queue-state').dataset.message!==message){$('queue-state').dataset.message=message;$('queue-state').setAttribute('aria-label',message);$('queue-state').replaceChildren(...[...message].map((letter,i)=>{const s=make('span',letter);s.setAttribute('aria-hidden','true');s.style.setProperty('--letter',i);return s;}));}
 return message;
}
function drawLayers(){
 document.querySelectorAll('#ambience-list [data-sound]').forEach(el=>{const active=(layers.get(el.dataset.sound)||0)>0;el.setAttribute('aria-pressed',String(active));el.closest('.ambience-item').classList.toggle('active',active);});
 document.querySelectorAll('[data-level]').forEach(el=>{el.value=String(Math.round((layers.get(el.dataset.level)||0)*100));});
 const active=(state?.ambience||[]).filter(i=>layers.get(i.id)>0);
 text('active-count',active.length?`${active.length} 种声音，轻轻叠加`:'此刻，静谧');
 reconcile($('quick-sounds'),active,x=>x.id,item=>{
  quick.get(item.id)?.pop.destroy();const [name,symbol]=sceneNames[item.id]||[item.name||item.id,item.icon||'♪'],button=make('button',null,'glass sound-pill floating');button.dataset.sound=item.id;button.setAttribute('aria-label',`调节${name}音量`);button.setAttribute('aria-haspopup','dialog');button.style.setProperty('--phase',`${-Math.random()*9}s`);button.append(make('span',symbol,'sound-symbol'),make('span',name));
  const panel=make('div',null,'volume-popover');panel.dataset.width='260';panel.setAttribute('role','dialog');panel.setAttribute('aria-label',`${name}音量`);const head=make('div',null,'popover-heading'),output=make('output');head.append(make('span',`${symbol}  ${name}`),output);const slider=make('input');slider.type='range';slider.min=0;slider.max=100;slider.dataset.level=item.id;slider.setAttribute('aria-label',`${name}音量`);slider.oninput=()=>setLayer(item.id,+slider.value/100);const off=make('button','关闭这层声音','text-button');panel.append(head,slider,off);const pop=popover(button,panel);button.onclick=()=>{pop.toggle();slider.focus({preventScroll:true});};off.onclick=()=>{pop.close();setLayer(item.id,0);$('ambience-toggle').focus({preventScroll:true});};quick.set(item.id,{pop,output,slider});return button;
 },(button,item)=>{const q=quick.get(item.id);if(q){q.slider.value=Math.round(layers.get(item.id)*100);q.output.textContent=`${q.slider.value}%`;}});
 for(const [id,q] of quick)if(!(layers.get(id)>0)){q.pop.close();setTimeout(()=>{if(!(layers.get(id)>0)){q.pop.destroy();quick.delete(id);}},650);}
}
function buildAmbience(items){
 for(const item of items){if(document.querySelector(`#ambience-list [data-sound="${item.id}"]`))continue;const [name,symbol]=sceneNames[item.id]||[item.name||item.id,item.icon||'♪'];const row=make('div',null,'ambience-item'),toggle=make('button',null,'floating');toggle.dataset.sound=item.id;toggle.setAttribute('aria-label',`开关${name}`);toggle.style.setProperty('--phase',`${-Math.random()*10}s`);toggle.append(make('span',symbol),make('span',name),make('small','＋'));toggle.onclick=()=>setLayer(item.id,layers.get(item.id)>0?0:.3);const slider=make('input');slider.type='range';slider.min=0;slider.max=100;slider.dataset.level=item.id;slider.setAttribute('aria-label',`${name}音量`);slider.oninput=()=>setLayer(item.id,+slider.value/100);row.append(toggle,slider);$('ambience-list').append(row);}
 const sources=new Map(items.flatMap(i=>i.sources||[]).map(s=>[s.url,s]));for(const s of sources.values())$('credits').append(make('p',`${s.author} · ${s.license} · ${s.url}`,'fine'));drawLayers();
}
function renderLibrary(){
 const count=state.pool.reduce((s,p)=>s+p.count,0),seconds=state.pool.reduce((s,p)=>s+p.seconds,0),bytes=state.archive?.bytes??state.pool.reduce((s,p)=>s+p.bytes,0);text('pool-status',`${count} 段声音 · ${(seconds/60).toFixed(0)} 分钟`);
 reconcile($('metrics'),[[String(count),'可播放曲目'],[`${(seconds/60).toFixed(0)} min`,'当下的声音时长'],[`${(bytes/1e9).toFixed(3)} / ${state.settings.capacity_gb} GB`,'共享曲库存储']],x=>x[1],()=>{const e=make('div',null,'metric floating');e.style.setProperty('--lift','2px');e.append(make('strong'),make('span'));return e;},(el,[v,label])=>{morphText(el.firstChild,v);el.lastChild.textContent=label;});
 const running=state.jobs.find(j=>['running','processing'].includes(j.status)),pending=state.jobs.filter(j=>j.status==='queued').length;const status=renderActivity(running,pending);text('generation-caption',running?`${status} · ${running.model_name||'本地模型'} · 播放不会中断`:state.settings.auto_generate?'曲库正在自然生长':'为下一次相遇，留一点新鲜。');
 $('auto-generate').checked=state.settings.auto_generate;selectors.duration?.setValue(state.settings.duration);
 text('library-note',`共享 ${state.settings.capacity_gb} GB · 完整播放 ${state.settings.plays_before_retire} 次后退休 · 最近 150 次播放参与去重${state.archive?.review_count?` · ${state.archive.review_count} 首旧配方待复核（保留文件，占用计入）`:''}`);
 const tracks=state.tracks.length?state.tracks.slice(0,60):[{id:'empty',title:'第一段声音正在路上。'}];
 reconcile($('track-list'),tracks,t=>t.id,()=>{const el=make('div',null,'track-row');el.append(make('span'),make('small'),make('small'));return el;},(el,t)=>{morphText(el.children[0],t.title);morphText(el.children[1],t.duration?`${fmt(t.duration)} · ${t.metadata.qc.final.lufs.toFixed(1)} LUFS`:'可以先打开环境声');morphText(el.children[2],t.duration?`${t.plays} / ${state.settings.plays_before_retire} 次`:'');});
 reconcile($('events'),state.events.slice(0,30),e=>e.id,()=>make('div',null,'event'),(el,e)=>{el.className=`event ${e.level}`;const value=`${new Date(e.time).toLocaleTimeString()} · ${e.model_name?`${e.model_name} · `:''}${e.code} · ${e.detail}`;if(el.textContent!==value)el.textContent=value;});
 const priority=state.refill?.priority?.[0];text('refill-note',priority?`${state.settings.auto_generate?'接下来优先补齐':'恢复补库后优先'}：${priority.name} · 当前首数占比 ${priority.current_percent.toFixed(1)}% / 目标 ${priority.target_percent.toFixed(1)}%`:'所选风格暂在等待重试');
 renderDistribution($('pool-bar'),$('pool-legend'),state.styles,state.pool);
 const enabled=state.settings.enabled_styles;
 reconcile($('enabled-styles'),state.styles,s=>s.id,s=>{const l=make('label'),c=make('input');c.type='checkbox';c.setAttribute('aria-label',`自动生成${s.name}`);c.onchange=async()=>{const selected=new Set(state.settings.enabled_styles);c.checked?selected.add(s.id):selected.delete(s.id);try{await api('PATCH','/settings',{enabled_styles:[...selected]});await refresh();}catch(e){c.checked=!c.checked;toast(e.message);}};l.append(c,make('span'));return l;},(l,s)=>{const available=state.models?.some(m=>m.id===s.model_variant&&m.installed&&m.eligible);l.firstChild.checked=enabled.includes(s.id);l.firstChild.disabled=!available&&!l.firstChild.checked;l.lastChild.textContent=s.name+(!available?' · 模型未就绪':s.validation_status?' · 待验证':'');l.title=!available?'需先通过设备检查并安装对应模型':s.validation_status?'该配方尚未通过调式筛查，暂不自动补库；可手动试生成':`允许自动补充${s.name}，不改变已有曲目`;});
}
let refreshing=false;
let styleSignature='',imageSignature='',ambienceSignature='';
async function refresh(){if(refreshing||management?.busy)return;refreshing=true;try{state=await api('GET','/state');audio.crossfade=state.settings.crossfade;if(!preferences.style&&!styleSignature)audio.style=state.pool.find(p=>p.count>0)?.style||state.settings.enabled_styles[0]||state.styles[0].id;
 const selectable=state.styles.map(s=>({...s,disabled:!state.models?.some(m=>m.id===s.model_variant&&m.installed&&m.eligible)&&!state.pool.some(p=>p.style===s.id&&p.count>0)}));
 const signature=JSON.stringify(selectable.map(s=>[s.id,s.name,s.subtitle,s.disabled]));if(signature!==styleSignature){styleSignature=signature;if(!state.styles.some(s=>s.id===audio.style)){audio.style='lofi';preferences.style='lofi';save();}selectors.style?.destroy?.();selectors.style=styleBubbles($('style-select'),selectable,value=>{audio.style=value;preferences.style=value;save();renderPlayback();updateScene();if(audio.playing)audio.next(true);});selectors.style.setValue(audio.style);}
 const ai=JSON.stringify(state.ambience.map(i=>[i.id,i.name,i.icon]));if(ai!==ambienceSignature){ambienceSignature=ai;buildAmbience(state.ambience);}
 const im=JSON.stringify(state.images||[]);if(im!==imageSignature){imageSignature=im;registerCustomScenes(state.images||[]);if(sceneMode!=='auto'&&!SCENES[sceneMode]){sceneMode='auto';preferences.scene='auto';save();}selectors.scene.setOptions(SCENE_OPTIONS);selectors.scene.setValue(sceneMode);updateScene();}
 renderLibrary();renderPlayback();}finally{refreshing=false;}}

for(const id of ['ambience-toggle','library-toggle','enter-settings'])$(id).onclick=()=>navigation.go('settings');for(const id of ['back-home','return-hint'])$(id).onclick=()=>navigation.go('home');
for(const id of ['play'])$(id).onclick=()=>audio.toggle().catch(e=>toast(e.message));$('next').onclick=()=>audio.next(true);$('music-volume').oninput=e=>{audio.setVolume(+e.target.value/100);preferences.volume=+e.target.value;save();};
function confirm(open){$('delete-panel').classList.toggle('visible',open);$('delete-panel').inert=!open;$('delete-panel').setAttribute('aria-hidden',String(!open));$('pages').inert=open;$('room-transport').inert=open;setTimeout(()=>$(open?'cancel-delete':'delete').focus({preventScroll:true}),0);}
$('delete').onclick=()=>confirm(true);$('cancel-delete').onclick=()=>confirm(false);$('confirm-delete').onclick=async()=>{confirm(false);try{await audio.removeCurrent();await refresh();toast('这首音乐已离开曲库。');}catch(e){toast(e.message);}};
$('delete-panel').addEventListener('keydown',e=>{if(e.key==='Escape'){e.stopPropagation();confirm(false);}if(e.key==='Tab'){e.preventDefault();$(document.activeElement.id==='cancel-delete'?'confirm-delete':'cancel-delete').focus();}});
$('motion').onclick=()=>{canvas.reduce(!canvas.reduced);preferences.reduced=canvas.reduced;save();$('motion').setAttribute('aria-pressed',String(canvas.reduced));};$('fullscreen').onclick=()=>window.ambient.window('fullscreen');
$('room-effects').checked=preferences.effects!==false;$('room-effects').onchange=e=>{preferences.effects=e.target.checked;save();};
selectors.weather=select($('weather-mode'),[['auto','跟随环境声'],['rain','细雨'],['snow','落雪'],['fireflies','萤火'],['none','静谧']].map(([value,label])=>({value,label})),value=>{weatherMode=value;preferences.weather=value;save();updateScene();});selectors.weather.setValue(weatherMode);
selectors.scene=select($('scene-mode'),SCENE_OPTIONS,value=>{sceneMode=value;preferences.scene=value;save();updateScene();});selectors.scene.setValue(sceneMode);
selectors.duration=select($('generation-duration'),[{value:180,label:'3 分钟'},{value:150,label:'2 分 30 秒'},{value:90,label:'1 分 30 秒'}],async value=>{try{await api('PATCH','/settings',{duration:Number(value)});await refresh();}catch(e){toast(e.message);selectors.duration.setValue(state.settings.duration);}});
let outputOptions='';
selectors.output=select($('audio-output'),[{value:'',label:'跟随系统默认设备'}],async value=>{
 try{await outputDevices.choose(value);}catch{toast('无法切换到这个输出设备，已保留原来的选择。');}
});
const outputDevices=new OutputDevices(audio.context,{saved:preferences.outputDevice||'',notify:toast,changed:status=>{
 const signature=JSON.stringify(status.options);if(signature!==outputOptions){selectors.output.close();selectors.output.setOptions(status.options);outputOptions=signature;}
 selectors.output.setValue(status.value);$('audio-output').disabled=status.busy||!status.supported;$('refresh-outputs').disabled=status.busy||!status.supported;
 $('audio-output').setAttribute('aria-busy',String(status.busy));
 text('output-note',!status.supported?'当前环境仅使用系统默认输出':status.busy?'正在连接声音的去处…':'音乐与环境声一起输出 · 设备断开时回到系统默认');
 if(!status.busy&&status.supported){preferences.outputDevice=status.value;save();}
}});
const outputReady=outputDevices.init().catch(()=>toast('暂时无法读取音频输出设备，继续使用系统默认设备。'));
$('refresh-outputs').onclick=()=>outputDevices.refresh().catch(()=>toast('暂时无法刷新输出设备，请稍后重试。'));
window.addEventListener('pagehide',()=>outputDevices.dispose());
export {outputDevices};
$('generate').onclick=async()=>{try{await api('POST','/jobs',{style:audio.style,duration:state.settings.duration,count:3});toast('三段新的声音已经加入生成队列。');await refresh();}catch(e){toast(e.message);}};
$('auto-generate').onchange=async e=>{try{await api('PATCH','/settings',{auto_generate:e.target.checked});await refresh();}catch(e){toast(e.message);e.target.checked=state.settings.auto_generate;}};
$('credits-toggle').onclick=()=>{const open=$('credits-panel').classList.toggle('open');$('credits-toggle').setAttribute('aria-expanded',String(open));$('credits-panel').inert=!open;};
function tab(id){for(const x of ['tracks','events']){const on=id===x;$(x+'-tab').setAttribute('aria-selected',String(on));$(x+'-tab').tabIndex=on?0:-1;const panel=$(x==='tracks'?'track-list':'events');panel.classList.toggle('active',on);panel.inert=!on;}}
for(const x of ['tracks','events']){$(x+'-tab').onclick=()=>tab(x);$(x+'-tab').onkeydown=e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const other=x==='tracks'?'events':'tracks';tab(other);$(other+'-tab').focus();}};}
window.addEventListener('keydown',e=>{if(e.code==='Space'&&!['INPUT','TEXTAREA','SELECT','BUTTON'].includes(document.activeElement.tagName)&&!document.activeElement.isContentEditable&&!document.querySelector(':popover-open,dialog[open]')&&!$('delete-panel').classList.contains('visible')){e.preventDefault();audio.toggle().catch(er=>toast(er.message));}});
const updateClock=roomClock($('clock'));
setInterval(()=>{const seconds=audio.elapsed();$('elapsed').textContent=fmt(seconds);$('duration').textContent=fmt(audio.current?.buffer.duration||0);$('progress-fill').style.transform=`scaleX(${Math.min(1,seconds/(audio.current?.buffer.duration||1))})`;updateClock();},500);
setInterval(()=>refresh().catch(e=>toast(`服务连接中断：${e.message}`)),7000);window.addEventListener('unhandledrejection',e=>toast(e.reason?.message||'操作未完成，请稍后重试。'));
attachHomeBrightness({navigation,toast});
management=librarySettings({api,audio,navigation,getState:()=>state,refresh,restoreLayers:()=>{for(const [id,v] of layers)audio.layer(id,v).catch(e=>toast(e.message));}});
sharedTransport(navigation);
Promise.all([management.recover().then(refresh),outputReady]).then(()=>{if(Number.isFinite(preferences.volume)){$('music-volume').value=String(preferences.volume);audio.setVolume(preferences.volume/100);}canvas.reduce(Boolean(preferences.reduced)||matchMedia('(prefers-reduced-motion: reduce)').matches);$('motion').setAttribute('aria-pressed',String(canvas.reduced));for(const [id,v] of Object.entries(preferences.layers||{}))if(state.ambience.some(x=>x.id===id))setLayer(id,Math.max(0,Math.min(1,Number(v)||0)));updateScene();if(preferences.playing&&!audio.playing)audio.toggle().catch(e=>toast(e.message));}).catch(e=>toast(e.message));setInterval(updateScene,60000);

document.addEventListener('dblclick',e=>{if(e.target.closest('button,input,textarea,label,select,a,dialog,[role=button],[role=combobox],[popover]'))return;getSelection()?.removeAllRanges();window.ambient.window('fullscreen');});
