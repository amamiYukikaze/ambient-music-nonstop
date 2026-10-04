/** Separate digits keep the time still while only the colon gently breathes. */
export function roomClock(host){
 let hours,colon,minutes;
 function update(){
  const now=new Date(),hh=String(now.getHours()).padStart(2,'0'),mm=String(now.getMinutes()).padStart(2,'0');
  if(!hours?.isConnected||hours.parentElement!==host){
   hours=document.createElement('span');colon=document.createElement('span');minutes=document.createElement('span');
   hours.className=minutes.className='clock-digits';colon.className='clock-colon';colon.textContent=':';
   for(const el of [hours,colon,minutes])el.setAttribute('aria-hidden','true');
   colon.style.animationDelay=`${-(now.getTime()%2000)}ms`;
   host.replaceChildren(hours,colon,minutes);
  }
  if(hours.textContent!==hh)hours.textContent=hh;if(minutes.textContent!==mm)minutes.textContent=mm;
  const value=`${hh}:${mm}`;if(host.getAttribute('datetime')!==value){host.setAttribute('datetime',value);host.setAttribute('aria-label',`当前时间 ${hh} 点 ${mm} 分`);}
 }
 update();return update;
}
