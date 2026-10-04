/** Shared by the room, setup, menus and runtime installer. No idle animation loop. */
export function installGlassMotion(){
 if(document.documentElement.dataset.glassMotion)return;
 document.documentElement.dataset.glassMotion='ready';
 const fine=matchMedia('(hover:hover) and (pointer:fine)'),reduce=matchMedia('(prefers-reduced-motion:reduce)');
 const entries=new Map();let attached=null,frame=0,last=0,pressed=false;
 const enabled=()=>fine.matches&&!reduce.matches&&!document.hidden&&!document.body.matches('.reduced,.low-power');
 const usable=node=>node?.isConnected&&!node.closest('[inert],[hidden],[aria-hidden="true"]')&&!node.matches(':disabled')&&(!document.querySelector('dialog:modal')||node.closest('dialog:modal'));
 function clear(){cancelAnimationFrame(frame);frame=last=0;attached=null;for(const [node,e] of entries){e.effect.cancel();delete node.dataset.magnet;}entries.clear();}
 function release(){if(attached){const e=entries.get(attached);if(e)e.tx=e.ty=0;attached=null;}}
 function tick(now){
  if(!enabled()){clear();return;}
  const dt=Math.min((now-last)/1000,.025);last=now;let moving=false;
  for(const [node,e] of entries){
   if(!usable(node)){e.effect.cancel();entries.delete(node);delete node.dataset.magnet;if(attached===node)attached=null;continue;}
   // A damped spring keeps its velocity when the mouse changes direction.
   e.vx+=((e.tx-e.x)*125-e.vx*15)*dt;e.vy+=((e.ty-e.y)*125-e.vy*15)*dt;
   e.x+=e.vx*dt;e.y+=e.vy*dt;
   const settled=Math.abs(e.tx-e.x)+Math.abs(e.ty-e.y)<.035&&Math.abs(e.vx)+Math.abs(e.vy)<.09;
   if(settled){e.x=e.tx;e.y=e.ty;e.vx=e.vy=0;}
   e.effect.effect.setKeyframes([{transform:`translate3d(${e.x}px,${e.y}px,0)`,composite:'add'}]);
   node.dataset.magnet=`${e.x.toFixed(2)},${e.y.toFixed(2)}`;
   document.dispatchEvent(new CustomEvent('glass-position',{detail:node}));
   if(settled&&!e.tx&&!e.ty){e.effect.cancel();entries.delete(node);delete node.dataset.magnet;}else moving||=!settled;
  }
  frame=moving?requestAnimationFrame(tick):0;
 }
 function wake(){if(!frame){last=performance.now();frame=requestAnimationFrame(tick);}}
 function entry(node){
  if(!entries.has(node)){
   // Additive composition leaves breathing, entry motion and click scale intact.
   const effect=node.animate([{transform:'translate3d(0,0,0)',composite:'add'}],{duration:1,fill:'both'});
   effect.id='glass-magnet';effect.pause();effect.currentTime=1;
   entries.set(node,{x:0,y:0,vx:0,vy:0,tx:0,ty:0,effect});
  }
  return entries.get(node);
 }
 function choose(target){
  if(!(target instanceof Element))return null;
  // The whole ambience card is one surface; its range never pulls separately.
  return target.closest('.ambience-item')||target.closest('button,[role="button"],summary,input:not([type="range"]):not([type="checkbox"]),textarea,.switch-label,.liquid-choice,#enabled-styles label,.choice,.choice-grid label,.volume,.home-brightness');
 }
 function aim(node,event){
  const e=entry(node),r=node.getBoundingClientRect(),x=event.clientX-(r.left+r.width/2-e.x),y=event.clientY-(r.top+r.height/2-e.y);
  if(Math.abs(x)>r.width/2+25||Math.abs(y)>r.height/2+22)return false;
  const card=node.matches('.ambience-item,.volume,.home-brightness,input,textarea'),cap=card?8:15;
  e.tx=cap*Math.tanh(x/Math.max(48,r.width*.45));e.ty=(card?6:11)*Math.tanh(y/Math.max(32,r.height*.7));
  return true;
 }
 function move(event){
  if(event.pointerType!=='mouse'||pressed)return;
  if(!enabled()){clear();return;}
  const candidate=choose(event.target);
  // A real neighbouring target wins; empty space retains a sticky capture band.
  if(attached&&(!usable(attached)||(candidate&&candidate!==attached)||!aim(attached,event)))release();
  if(!attached&&usable(candidate)){attached=candidate;aim(attached,event);}
  wake();
 }
 function leave(){release();wake();}
 document.addEventListener('pointermove',move,{passive:true});
 document.addEventListener('pointerdown',event=>{
  pressed=true;
  const control=choose(event.target);if(control)control.dataset.interacting='true';
  for(const e of entries.values()){e.tx=e.x;e.ty=e.y;e.vx=e.vy=0;}
 },{passive:true});
 function up(){pressed=false;document.querySelectorAll('[data-interacting]').forEach(n=>delete n.dataset.interacting);leave();}
 document.addEventListener('pointerup',up,{passive:true});document.addEventListener('pointercancel',up,{passive:true});
 document.documentElement.addEventListener('pointerleave',()=>{if(!pressed)leave();});
 document.addEventListener('scroll',()=>{if(!pressed)leave();},{capture:true,passive:true});
 window.addEventListener('blur',up);document.addEventListener('visibilitychange',()=>{if(!enabled())clear();});
 fine.addEventListener('change',clear);reduce.addEventListener('change',clear);
 new MutationObserver(()=>{if(!enabled())clear();}).observe(document.body,{attributes:true,attributeFilter:['class','data-view']});
 window.addEventListener('pagehide',clear);
}

/** The selected tab itself compresses and rebounds twice, without a moving lens. */
export function bubblePress(button){
 const from=getComputedStyle(button).scale;
 button.getAnimations().filter(a=>a.id==='bubble-press').forEach(a=>a.cancel());
 if(document.body.classList.contains('reduced')||matchMedia('(prefers-reduced-motion:reduce)').matches)return;
 const a=button.animate([
  {scale:from==='none'?'1':from,offset:0},
  {scale:'1.045 .87',offset:.11},
  {scale:'.975 1.13',offset:.3},
  {scale:'1.017 .96',offset:.5},
  {scale:'.996 1.035',offset:.68},
  {scale:'1.002 .992',offset:.84},{scale:'1',offset:1}
 ],{duration:1000,easing:'ease-in-out'});
 a.id='bubble-press';
}
