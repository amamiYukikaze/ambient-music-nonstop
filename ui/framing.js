/** One cover transform for the image AND its image-space effects. */
export function coverLayout(w,h,iw=1672,ih=941,focus=[.74,.43]){
 const scale=Math.max(w/iw,h/ih),width=iw*scale,height=ih*scale;
 const portrait=Math.max(0,Math.min(1,(iw/ih-w/h)/(iw/ih-.72)));
 const targetX=.77-.12*portrait;
 const left=Math.min(0,Math.max(w-width,targetX*w-focus[0]*width));
 const top=Math.min(0,Math.max(h-height,.43*h-focus[1]*height));
 return {width,height,left,top,x:Math.abs(w-width)<.01?50:100*left/(w-width),y:Math.abs(h-height)<.01?50:100*top/(h-height)};
}
export function initializeFraming(scenes){
 function update(){document.querySelectorAll('.wallpaper').forEach(img=>{
  const scene=scenes[img.dataset.scene],r=coverLayout(innerWidth,innerHeight,img.naturalWidth||1672,img.naturalHeight||941,scene?.focus);
  img.style.objectPosition=`${r.x}% ${r.y}%`;
 });}
 const stack=document.getElementById('wallpaper-stack');new MutationObserver(update).observe(stack,{childList:true});stack.addEventListener('load',update,true);window.addEventListener('resize',update);update();
}
