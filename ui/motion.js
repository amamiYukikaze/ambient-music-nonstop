const ease='cubic-bezier(.22,1,.36,1)';
const reduced=()=>document.body.classList.contains('reduced')||matchMedia('(prefers-reduced-motion: reduce)').matches;
export function morphText(el,text){
 text=String(text);if(el.dataset.targetText===text)return;el.dataset.targetText=text;
 const token=(el._textToken||0)+1;el._textToken=token;
 el.getAnimations().filter(a=>a.id==='text-morph').forEach(a=>a.cancel());
 if(!el.textContent||reduced()){el.textContent=text;return;}
 const out=el.animate([{opacity:getComputedStyle(el).opacity,translate:'0 0'},{opacity:0,translate:'0 -5px'}],{duration:180,easing:ease,fill:'forwards'});out.id='text-morph';
 out.finished.then(()=>{if(el._textToken!==token)return;el.textContent=text;out.cancel();const enter=el.animate([{opacity:0,translate:'0 8px'},{opacity:1,translate:'0 0'}],{duration:620,easing:ease});enter.id='text-morph';}).catch(()=>{});
}
export function reconcile(parent,items,key,create,update){
 const old=new Map([...parent.children].map(n=>[n.dataset.key,n]));const rects=new Map([...old.values()].map(n=>[n,n.getBoundingClientRect()]));const keep=new Set();
 for(const item of items){const id=String(key(item));let node=old.get(id);if(!node){node=create(item);node.dataset.key=id;parent.append(node);if(!reduced())node.animate([{opacity:0,translate:'0 18px',scale:'.93'},{opacity:1,translate:'0 0',scale:'1'}],{duration:750,easing:ease});}if(node._leaving){node._leaving.cancel();node._leaving=null;}update(node,item);keep.add(node);}
 // Stable nodes retain focus, range drag state and their breathing phase during polling.
 const ordered=items.map(i=>[...parent.children].find(n=>n.dataset.key===String(key(i))));
 ordered.forEach((n,i)=>{if(parent.children[i]!==n)parent.insertBefore(n,parent.children[i]||null);});
 for(const node of old.values())if(!keep.has(node)&&!node._leaving){
  const a=node.animate([{opacity:1,scale:'1'},{opacity:0,scale:'.8'}],{duration:reduced()?0:320,easing:ease,fill:'forwards'});node._leaving=a;node.inert=true;
  a.finished.then(()=>{const positions=new Map([...parent.children].map(n=>[n,n.getBoundingClientRect()]));node.remove();reflow(parent,positions);}).catch(()=>{node.inert=false;});
 }
 reflow(parent,rects);
}
function reflow(parent,rects){if(reduced())return;for(const n of parent.children){if(n._leaving)continue;const a=rects.get(n),b=n.getBoundingClientRect();if(a&&(Math.abs(a.x-b.x)>1||Math.abs(a.y-b.y)>1)){n._flip?.cancel();n._flip=n.animate([{translate:`${a.x-b.x}px ${a.y-b.y}px`},{translate:'0 0'}],{duration:700,easing:ease});}}}
export function popover(anchor,panel){
 panel.popover='auto';panel.classList.add('glass-popover');(anchor.closest('dialog')||document.body).append(panel);anchor.setAttribute('aria-expanded','false');
 let restore=false;
 function position(){const r=anchor.getBoundingClientRect(),width=Math.min(Number(panel.dataset.width)||Math.max(230,r.width),innerWidth-28);panel.style.width=`${width}px`;panel.style.maxHeight='min(440px,70vh)';const h=panel.offsetHeight,below=innerHeight-r.bottom-12,above=r.top-12,top=below<h&&above>below;panel.style.maxHeight=`${Math.max(80,Math.min(440,innerHeight*.7,(top?above:below)-12))}px`;const actual=panel.offsetHeight;panel.style.left=`${Math.min(innerWidth-width-14,Math.max(14,r.left))}px`;panel.style.top=`${Math.max(12,Math.min(innerHeight-actual-12,top?r.top-actual-12:r.bottom+12))}px`;panel.style.setProperty('--origin',top?'bottom center':'top center');}
 panel.addEventListener('toggle',e=>{anchor.setAttribute('aria-expanded',String(e.newState==='open'));if(e.newState==='closed'&&restore){restore=false;anchor.focus({preventScroll:true});}});
 panel.addEventListener('keydown',e=>{if(e.key==='Escape'){e.stopPropagation();e.preventDefault();restore=true;panel.hidePopover();}});
 const reposition=()=>{if(panel.matches(':popover-open'))position();};
 const followGlass=e=>{if(e.detail===anchor||e.detail.contains(anchor))reposition();};
 window.addEventListener('resize',reposition);document.addEventListener('scroll',reposition,true);document.addEventListener('glass-position',followGlass);
 return {panel,open(){if(panel.matches(':popover-open'))return;panel.showPopover();position();anchor.setAttribute('aria-expanded','true');},close(focus=false){restore=focus;panel.hidePopover();},toggle(){panel.matches(':popover-open')?this.close(true):this.open();},destroy(){window.removeEventListener('resize',reposition);document.removeEventListener('scroll',reposition,true);document.removeEventListener('glass-position',followGlass);panel.remove();}};
}
export function select(button,options,onChange){
 const panel=document.createElement('div');panel.setAttribute('role','listbox');panel.id=`${button.id}-options`;panel.setAttribute('aria-label',button.getAttribute('aria-label')||button.textContent);panel.dataset.width=button.id==='scene-mode'?'310':'245';
 button.setAttribute('role','combobox');button.setAttribute('aria-haspopup','listbox');button.setAttribute('aria-controls',panel.id);
 const label=document.createElement('span');label.className='select-label';const arrow=document.createElement('span');arrow.className='chevron';arrow.textContent='⌄';button.replaceChildren(label,arrow);
 const pop=popover(button,panel);let value,search='',searchTimer;
 function setValue(v){value=String(v);const chosen=options.find(o=>String(o.value)===value);morphText(label,chosen?.label||value);for(const el of panel.children)el.setAttribute('aria-selected',String(el.dataset.value===value));}
 function setOptions(next){options=next;panel.replaceChildren();for(const option of options){const el=document.createElement('button');el.className='select-option';el.setAttribute('role','option');el.dataset.value=String(option.value);el.disabled=Boolean(option.disabled);el.setAttribute('aria-disabled',String(el.disabled));if(option.thumbnail){const thumb=document.createElement('img');thumb.loading='lazy';thumb.decoding='async';thumb.src=option.thumbnail;thumb.alt='';thumb.className='scene-thumb';el.append(thumb);}const name=document.createElement('span');name.textContent=option.label;el.append(name);el.tabIndex=-1;el.onclick=()=>{setValue(option.value);pop.close(true);Promise.resolve(onChange(option.value)).catch(()=>{});};panel.append(el);}if(value!==undefined)setValue(value);}
 setOptions(options);
 function focus(index,direction=1){const opts=[...panel.children];for(let n=0;n<opts.length;n++){const item=opts[((index+n*direction)%opts.length+opts.length)%opts.length];if(!item.disabled){item.focus({preventScroll:true});return;}}}
 function open(last=false){pop.open();focus(last?options.length-1:Math.max(0,options.findIndex(o=>String(o.value)===value)));}
 button.onclick=()=>panel.matches(':popover-open')?pop.close(true):open();
 button.onkeydown=e=>{if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){e.preventDefault();open(e.key==='End');}};
 panel.addEventListener('keydown',e=>{const idx=[...panel.children].indexOf(document.activeElement);if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){e.preventDefault();focus(e.key==='Home'?0:e.key==='End'?options.length-1:idx+(e.key==='ArrowDown'?1:-1),['ArrowUp','End'].includes(e.key)?-1:1);}else if(e.key==='Tab'){pop.close();}else if(e.key.length===1&&e.key!==' '){search+=e.key.toLowerCase();clearTimeout(searchTimer);searchTimer=setTimeout(()=>search='',700);const i=options.findIndex(o=>!o.disabled&&o.label.toLowerCase().startsWith(search));if(i>=0)focus(i);}});
 return {setValue,setOptions,get value(){return value;},close:()=>pop.close()};
}
export function pages(){
 const listeners=new Set(),order=['home','settings','advanced'],hooks={},host=document.getElementById('pages');
 let view='home',sum=0,last=0,wheelDirection=0,gestureAt=0,position=0,target=0,velocity=0,frame=null,previous=0,intent=0,focusTimer,reboundTimer;
 host.style.transition='none';
 function draw(){host.style.transform=`translate3d(0,${-position*100}%,0)`;for(const listener of listeners)listener(position);}
 function step(time){const dt=Math.min(.025,(time-(previous||time))/1000);previous=time;velocity+=((target-position)*100-velocity*20)*dt;position+=velocity*dt;draw();if(Math.abs(target-position)<.00015&&Math.abs(velocity)<.0008){position=target;velocity=0;draw();frame=null;previous=0;return;}frame=requestAnimationFrame(step);}
 function move(value){target=value;if(reduced()){if(frame)cancelAnimationFrame(frame);frame=null;position=target;velocity=0;draw();return;}if(frame===null){previous=0;frame=requestAnimationFrame(step);}}
 function rebound(){clearTimeout(reboundTimer);host.dataset.rebounds=String(Number(host.dataset.rebounds||0)+1);move(order.indexOf(view)-.095);reboundTimer=setTimeout(()=>move(order.indexOf(view)),reduced()?0:180);}
 async function go(next,{force=false}={}){
  if(view===next||!order.includes(next))return true;const token=++intent;
  if(!force&&hooks[view]?.leave&&!await hooks[view].leave(next))return false;
  if(token!==intent)return false;
  if(hooks[next]?.enter)await hooks[next].enter();if(token!==intent)return false;
  clearTimeout(reboundTimer);view=next;sum=0;document.querySelectorAll(':popover-open').forEach(p=>p.hidePopover());document.body.dataset.view=view;
  for(const id of order){const page=document.getElementById(id);if(page)page.inert=view!==id;}
  move(order.indexOf(view));clearTimeout(focusTimer);focusTimer=setTimeout(()=>{if(!document.querySelector('dialog[open]'))document.getElementById({home:'enter-settings',settings:'settings-title',advanced:'advanced-title'}[view])?.focus({preventScroll:true});},reduced()?160:650);
  return true;
 }
 function change(direction){const index=order.indexOf(view);if(index+direction<0||index+direction>=order.length)return;go(order[index+direction]).catch(e=>{const note=document.getElementById('toast');note.textContent=e.message;note.classList.add('visible');});}
 document.addEventListener('wheel',e=>{
  if(e.ctrlKey||Math.abs(e.deltaX)>Math.abs(e.deltaY))return;
  if(document.querySelector(':popover-open,dialog[open]')||document.getElementById('delete-panel').classList.contains('visible'))return;
  const first=e.target.closest('.scroll-area');let scroller=first;
  while(scroller){
   if((e.deltaY<0&&scroller.scrollTop>1)||(e.deltaY>0&&scroller.scrollTop+scroller.clientHeight<scroller.scrollHeight-1)){
    if(scroller!==first){e.preventDefault();scroller.scrollTop+=e.deltaY*(e.deltaMode===1?20:e.deltaMode===2?innerHeight:1);}
    sum=0;return;
   }
   scroller=scroller.parentElement?.closest('.scroll-area');
  }
  e.preventDefault();const t=performance.now(),gap=t-last,delta=e.deltaY*(e.deltaMode===1?20:e.deltaMode===2?innerHeight:1);last=t;
  // Consume one wheel gesture, not two pages of trackpad momentum. A fresh
  // gesture or opposite direction can interrupt the moving spring at once.
  if(gap>210||wheelDirection!==Math.sign(delta)){sum=0;gestureAt=0;}
  wheelDirection=Math.sign(delta);
  sum+=delta;if(gestureAt)return;
  if(Math.abs(sum)>55){gestureAt=t;change(Math.sign(sum));}
 },{passive:false});
 document.addEventListener('keydown',e=>{if(e.defaultPrevented||document.querySelector(':popover-open,dialog[open]')||document.getElementById('delete-panel').classList.contains('visible'))return;if(['INPUT','TEXTAREA','SELECT','BUTTON'].includes(document.activeElement.tagName)&&e.key!=='Escape')return;if(e.key==='PageDown'){e.preventDefault();change(1);}if(e.key==='PageUp'||e.key==='Escape'){e.preventDefault();change(-1);}});
 return {go,rebound,subscribe(listener){listeners.add(listener);return ()=>listeners.delete(listener);},register(id,actions){hooks[id]=actions;},get view(){return view;},get position(){return position;}};
}

