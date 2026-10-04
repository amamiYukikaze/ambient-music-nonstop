/** One live player toolbar. Page slots describe layout, never duplicate controls. */
export function sharedTransport(navigation){
 const home=document.querySelector('.player-top'),shell=document.createElement('div');
 shell.id='room-transport';shell.setAttribute('role','toolbar');shell.setAttribute('aria-label','音乐播放控制');
 const transport=home.querySelector('.transport'),volume=home.querySelector('.volume');
 const anchor=document.createElement('div');anchor.className='transport-anchor';anchor.dataset.transportSlot='home';anchor.setAttribute('aria-hidden','true');transport.before(anchor);
 shell.append(transport,volume);document.body.append(shell);
 const order=['home','settings','advanced'];let slots=[],resizeFrame=0,started=false,frame=0,last=0,x=0,y=0,vx=0,vy=0,tx=0,ty=0,view=navigation.view;
 const reduced=()=>document.body.classList.contains('reduced')||matchMedia('(prefers-reduced-motion:reduce)').matches;
 function measure(){
  const p=navigation.position,h=document.getElementById('pages').getBoundingClientRect().height;
  slots=order.map((view,i)=>{const node=document.querySelector(`[data-transport-slot="${view}"]`),r=node.getBoundingClientRect();return {x:r.x+r.width/2-shell.offsetWidth/2,y:r.y-(i-p)*h+r.height/2-shell.offsetHeight/2};});
  // Layout changes are not navigation. Resize/font/content updates land directly,
  // including a resize that interrupts a page transition; never start a spring.
  cancelAnimationFrame(frame);frame=last=0;vx=vy=0;
  view=navigation.view;const slot=slots[order.indexOf(view)];x=tx=slot.x;y=ty=slot.y;
  shell.dataset.moving='false';draw();if(!started){started=true;shell.dataset.ready='true';}
 }
 function draw(){shell.style.transform=`translate3d(${x}px,${y}px,0)`;}
 function step(now){
  const dt=Math.min(.025,(now-(last||now))/1000);last=now;
  // A slower independent spring makes the controls float into their new place.
  // Retained velocity also handles a return gesture halfway through the journey.
  vx+=((tx-x)*42-vx*13)*dt;vy+=((ty-y)*42-vy*13)*dt;x+=vx*dt;y+=vy*dt;
  if(reduced()||(Math.abs(tx-x)+Math.abs(ty-y)<.08&&Math.abs(vx)+Math.abs(vy)<.2)){x=tx;y=ty;vx=vy=0;frame=last=0;shell.dataset.moving='false';draw();return;}
  draw();frame=requestAnimationFrame(step);
 }
 function aim(){
  if(!slots.length)return;const slot=slots[order.indexOf(navigation.view)];tx=slot.x;ty=slot.y;
  if(reduced()){cancelAnimationFrame(frame);frame=last=0;x=tx;y=ty;vx=vy=0;shell.dataset.moving='false';draw();return;}
  if(Math.abs(tx-x)+Math.abs(ty-y)<.08&&!frame){shell.dataset.moving='false';draw();return;}
  if(!frame){last=0;shell.dataset.moving='true';frame=requestAnimationFrame(step);}
 }
 function schedule(){cancelAnimationFrame(resizeFrame);resizeFrame=requestAnimationFrame(measure);}
 navigation.subscribe(()=>{if(view!==navigation.view){view=navigation.view;aim();}});
 const observer=new ResizeObserver(schedule);document.querySelectorAll('.transport-anchor').forEach(n=>observer.observe(n));observer.observe(home);
 window.addEventListener('resize',schedule);document.fonts.ready.then(schedule);
 // The home player has a one-time entrance transform; sample its final slot.
 home.closest('.player').addEventListener('animationend',schedule);measure();
 window.addEventListener('pagehide',()=>{observer.disconnect();cancelAnimationFrame(resizeFrame);cancelAnimationFrame(frame);});
 return shell;
}
