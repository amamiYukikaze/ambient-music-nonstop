/** Shared presentation for runtime setup and model preparation. */
const reduce=()=>matchMedia('(prefers-reduced-motion: reduce)').matches||document.body.classList.contains('reduced');
export function playSetupIntro(host){
 if(host.dataset.introPlayed)return;
 host.dataset.introPlayed='true';host.classList.add('setup-enter');
 const light=document.createElement('div');light.className='setup-intro';light.setAttribute('aria-hidden','true');
 light.innerHTML='<div class="intro-halo"></div><img src="assets/brand.svg" alt="">';host.append(light);
 setTimeout(()=>{light.remove();host.classList.remove('setup-enter');},1100);
}
export function summaryText(node,text){
 if(node.textContent===text)return;
 // Cancel a superseded transition; rapid byte updates never animate this label.
 node.getAnimations().forEach(a=>a.cancel());node.textContent=text;
 const effect=node.animate(reduce()?[{opacity:.5},{opacity:1}]:[{opacity:0,transform:'translate3d(0,7px,0)'},{opacity:1,transform:'translate3d(0,0,0)'}],
  {duration:200,easing:getComputedStyle(node).getPropertyValue('--ease').trim()||'cubic-bezier(.22,1,.36,1)'});
 effect.id='setup-summary';
}
export const formatBytes=n=>{
 if(!Number.isFinite(n)||n<=0)return '0 B';
 const unit=Math.min(3,Math.floor(Math.log(n)/Math.log(1024)));return `${(n/1024**unit).toFixed(unit?1:0)} ${['B','KiB','MiB','GiB'][unit]}`;
};
export function animateDisclosure(details){
 const trigger=details.querySelector('summary'),content=details.querySelector('.setup-log-reveal');let effect=null,expanded=details.open;
 trigger.setAttribute('aria-expanded',String(expanded));
 trigger.addEventListener('click',event=>{
  event.preventDefault();expanded=!expanded;
  const from=details.open?content.getBoundingClientRect().height:0;
  const opacity=details.open?getComputedStyle(content).opacity:'0';
  effect?.cancel();details.open=true;
  trigger.setAttribute('aria-expanded',String(expanded));details.dataset.expanded=String(expanded);content.inert=!expanded;
  const target=expanded?content.scrollHeight:0;
  if(reduce()){
   details.open=expanded;
   effect=expanded?content.animate([{opacity:.5},{opacity:1}],{duration:150,easing:'ease'}):null;return;
  }
  effect=content.animate([{height:`${from}px`,opacity},{height:`${target}px`,opacity:expanded?1:0}],
   {duration:200,easing:getComputedStyle(content).getPropertyValue('--ease').trim()||'cubic-bezier(.22,1,.36,1)'});
  const current=effect;current.finished.then(()=>{if(effect===current){details.open=expanded;effect=null;}}).catch(()=>{});
 });
}
export function progressPanel(host,{id='setup-progress',label='准备进度'}={}){
 const panel=document.createElement('section');panel.className='setup-progress-card';
 panel.innerHTML=`<div class="setup-progress-heading"><p class="setup-summary" role="status" aria-live="polite"></p><span class="setup-step-count"></span></div><div class="setup-meter" id="${id}" role="progressbar" aria-label="${label}" aria-valuemin="0" aria-valuemax="100"><span></span></div><p class="setup-metrics"></p><details class="setup-logs"><summary><span class="logs-closed">展开日志</span><span class="logs-open">收起日志</span><span class="log-count"></span></summary><div class="setup-log-reveal"><div class="setup-log-scroll" tabindex="0" aria-label="详细日志"></div></div></details>`;
 host.append(panel);animateDisclosure(panel.querySelector('details'));
 const title=panel.querySelector('.setup-summary'),meter=panel.querySelector('.setup-meter'),fill=meter.firstElementChild,metrics=panel.querySelector('.setup-metrics'),logs=panel.querySelector('.setup-log-scroll');
 let group,lines=0,stage='',lastLog='';
 function log(text,{heading,level='info',deduplicate=false}={}){
  if(!text||deduplicate&&text===lastLog)return;lastLog=text;
  const follow=logs.scrollHeight-logs.scrollTop-logs.clientHeight<30;
  if(!group||heading&&stage!==heading){stage=heading||'详细记录';group=document.createElement('section');group.className='setup-log-group';const h=document.createElement('h4');h.textContent=stage;group.append(h);logs.append(group);}
  const row=document.createElement('p');row.dataset.level=level;row.textContent=text;group.append(row);lines++;
  // Bound the DOM and text size throughout multi-GB installs.
  while(logs.querySelectorAll('p').length>240){logs.querySelector('p').remove();if(logs.firstElementChild?.children.length===1)logs.firstElementChild.remove();}
  panel.querySelector('.log-count').textContent=lines>240?`最近 240 / ${lines} 条`:`${lines} 条`;
  if(follow)logs.scrollTop=logs.scrollHeight;
 }
 function update({summary,detail='',current=null,total=null,completed,stages,active=true,error=false}){
  if(summary)summaryText(title,summary);
  metrics.textContent=detail;
  panel.dataset.error=String(error);panel.dataset.active=String(active);
  const measured=Number.isFinite(current)&&Number.isFinite(total)&&total>0;
  const percentage=measured?Math.max(0,Math.min(100,100*current/total)):null;
  meter.dataset.measured=String(measured);meter.dataset.active=String(active);
  if(measured){meter.setAttribute('aria-valuenow',percentage.toFixed(1));fill.style.transform=`scaleX(${percentage/100})`;}
  else{meter.removeAttribute('aria-valuenow');fill.style.removeProperty('transform');}
  meter.setAttribute('aria-valuetext',measured?`${percentage.toFixed(1)}%，${detail}`:summary||'等待中');
  panel.querySelector('.setup-step-count').textContent=stages?`${completed||0} / ${stages} 步骤完成`:measured?`${percentage.toFixed(1)}%`:'';
 }
 return {element:panel,update,log};
}
