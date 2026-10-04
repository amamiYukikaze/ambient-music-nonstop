/** A title-anchored constellation, using native popover focus/light-dismiss semantics. */
export function styleBubbles(trigger,styles,onChange){
 const panel=document.createElement('div');panel.id='style-bubbles';panel.className='bubble-menu';panel.popover='auto';panel.setAttribute('role','listbox');panel.setAttribute('aria-label','声音的颜色');
 const caption=document.createElement('p');caption.className='bubble-caption';caption.textContent='声音的颜色 · 选一种此刻的心情';panel.append(caption);document.body.append(panel);
 trigger.setAttribute('aria-controls',panel.id);trigger.setAttribute('aria-haspopup','listbox');trigger.setAttribute('aria-expanded','false');
 // Sample the documented mass=1, stiffness=100, damping=10 spring into a compositor easing.
 const values=Array.from({length:61},(_,i)=>{const t=i/60*1.3;return i===60?1:1-Math.exp(-5*t)*(Math.cos(Math.sqrt(75)*t)+5/Math.sqrt(75)*Math.sin(Math.sqrt(75)*t));});
 panel.style.setProperty('--bubble-spring',`linear(${values.map(x=>x.toFixed(5)).join(',')})`);
 const symbols=styles.map(s=>({lofi:'☕',ambient:'◌',daily_piano:'♧',anime_daily:'✿',orchestral:'♬',guzheng:'🏞️',guitar:'♫',artcore:'✦'})[s.id]||'♪'),buttons=[];let value,restore=false;
 styles.forEach((s,i)=>{const orbit=document.createElement('div');orbit.className='bubble-orbit';orbit.style.setProperty('--i',i);const button=document.createElement('button');button.className='style-bubble';button.setAttribute('role','option');button.dataset.value=s.id;button.tabIndex=-1;button.disabled=Boolean(s.disabled);button.setAttribute('aria-disabled',String(button.disabled));button.title=s.disabled?'尚无库存，需先安装对应模型':s.subtitle;button.style.setProperty('--phase',`${-i*.7}s`);const symbol=document.createElement('span');symbol.className='bubble-symbol';symbol.textContent=symbols[i];const label=document.createElement('strong');label.textContent=s.name;const sub=document.createElement('small');sub.textContent=s.disabled?'模型未就绪':s.subtitle.split(' · ')[0];button.append(symbol,label,sub);orbit.append(button);panel.append(orbit);buttons.push(button);button.onclick=()=>{setValue(s.id);close(true);onChange(s.id);};});
 function position(){const a=trigger.getBoundingClientRect(),width=Math.min(566,innerWidth-28),height=263,left=Math.max(14,Math.min(innerWidth-width-14,a.left-26)),top=Math.max(14,a.top-height-14);panel.style.width=`${width}px`;panel.style.height=`${height}px`;panel.style.left=`${left}px`;panel.style.top=`${top}px`;
  buttons.forEach((b,i)=>{const row=Math.floor(i/5),col=i%5,step=width/5,x=step*(col+.5),y=50+row*108+(col%2?12:0),orbit=b.parentElement;orbit.style.left=`${x-46}px`;orbit.style.top=`${y-42}px`;orbit.style.setProperty('--launch-x',`${a.left+a.width*.45-left-x}px`);orbit.style.setProperty('--launch-y',`${a.top+a.height*.4-top-y}px`);});
 }
 function focus(i){for(let n=0;n<buttons.length;n++){const b=buttons[((i+n)%buttons.length+buttons.length)%buttons.length];if(!b.disabled){b.focus({preventScroll:true});return;}}}
 function open(){position();panel.showPopover();trigger.setAttribute('aria-expanded','true');focus(Math.max(0,styles.findIndex(s=>s.id===value)));}
 function close(returnFocus=false){restore=returnFocus;panel.hidePopover();}
 function setValue(next){value=next;buttons.forEach(b=>b.setAttribute('aria-selected',String(b.dataset.value===value)));}
 trigger.onclick=()=>panel.matches(':popover-open')?close(true):open();trigger.onkeydown=e=>{if(['ArrowDown','ArrowUp'].includes(e.key)){e.preventDefault();open();}};
 panel.addEventListener('toggle',e=>{const open=e.newState==='open';trigger.setAttribute('aria-expanded',String(open));if(!open&&restore){restore=false;trigger.focus({preventScroll:true});}});
 panel.addEventListener('click',e=>{if(e.target===panel)close(true);});
 panel.addEventListener('keydown',e=>{const i=buttons.indexOf(document.activeElement);if(e.key==='Escape'){e.preventDefault();e.stopPropagation();close(true);}else if(['ArrowRight','ArrowLeft','ArrowDown','ArrowUp','Home','End'].includes(e.key)){e.preventDefault();focus(e.key==='Home'?0:e.key==='End'?buttons.length-1:i+({ArrowRight:1,ArrowLeft:-1,ArrowDown:5,ArrowUp:-5}[e.key]));}else if(e.key==='Tab')close();});
 const onResize=()=>{if(panel.matches(':popover-open'))position();};window.addEventListener('resize',onResize);
 return {setValue,get value(){return value;},close,destroy(){panel.remove();window.removeEventListener('resize',onResize);}};
}
