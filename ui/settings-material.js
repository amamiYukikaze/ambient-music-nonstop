export const reduced=()=>document.body.classList.contains('reduced')||matchMedia('(prefers-reduced-motion: reduce)').matches;
const paths={mix:'M5 5v14M12 5v14M19 5v14M2 9h6M9 15h6M16 8h6',storage:'M3 7h7l2 2h9v10H3V7Zm0 0V5h7l2 2',recipes:'M9 17V5l11-2v12M9 8l11-2M9 17c0 2-5 3-5 0s5-3 5 0m11-2c0 2-5 3-5 0s5-3 5 0',generation:'M3 4h18v13H3V4Zm5 17h8M12 17v4',models:'M6 6h12v12H6V6Zm3 3h6v6H9V9M9 2v4m6-4v4M9 18v4m6-4v4M2 9h4m-4 6h4m12-6h4m-4 6h4',assets:'M3 4h18v16H3V4Zm0 12 6-6 5 5 3-3 4 4M16 8h.01',save:'m5 12 4 4L20 5',up:'m6 14 6-6 6 6'};
export function mark(name){return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.45" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[name]||paths.mix}"/></svg>`;}
export function switches(root){for(const input of root.querySelectorAll('input[type=checkbox]')){if(input.nextElementSibling?.classList.contains('liquid-switch'))continue;input.setAttribute('role','switch');input.classList.add('switch-input');const track=document.createElement('span');track.className='liquid-switch';track.setAttribute('aria-hidden','true');track.innerHTML='<span></span>';input.after(track);input.closest('label')?.classList.add('liquid-choice');}}
export function paneTransition(previous,next,direction=1){
 const duration=reduced()?150:700;
 for(const panel of [previous,next].filter(Boolean)){
  const entering=panel===next,wasVisible=!panel.hidden,style=wasVisible?getComputedStyle(panel):null;
  const from={opacity:wasVisible?style.opacity:'0',transform:wasVisible?style.transform:`translate3d(${direction*32}px,18px,0) scale(.98)`};
  panel.getAnimations().forEach(a=>a.cancel());panel.hidden=false;panel.inert=!entering;panel.dataset.active=String(entering);
  if(reduced())from.transform='none';
  const animation=panel.animate([from,{opacity:entering?1:0,transform:reduced()?'none':entering?'translate3d(0,0,0) scale(1)':`translate3d(${-direction*24}px,-8px,0) scale(.985)`}],{duration:entering?duration:Math.min(duration,350),easing:'cubic-bezier(.22,1,.36,1)',fill:'both'});
  animation.finished.then(()=>{if(panel.dataset.active===String(entering)){if(!entering)panel.hidden=true;animation.cancel();}}).catch(()=>{});
 }
 if(!reduced())[...next.querySelectorAll('.settings-card,.mix-row')].slice(0,10).forEach((el,i)=>{el.getAnimations().filter(a=>a.id==='card-enter').forEach(a=>a.cancel());const a=el.animate([{opacity:0,transform:'translate3d(0,20px,0) scale(.97)'},{opacity:1,transform:'translate3d(0,0,0) scale(1)'}],{duration:800,delay:i*45,easing:'cubic-bezier(.22,1,.36,1)'});a.id='card-enter';});
}
