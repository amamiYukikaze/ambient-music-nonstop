/** The home slider is a live room control, outside the advanced-settings draft. */
let attached;
export function attachHomeBrightness({navigation,toast=()=>{}}){
 if(attached)return attached;
 const host=document.querySelector('.top-actions'),control=document.createElement('label');
 control.className='home-brightness glass floating';control.hidden=true;
 control.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.4 1.4m11.2 11.2L19 19M5 19l1.4-1.4M17.6 6.4 19 5"/></svg><input id="home-brightness" type="range" min="1" max="100" aria-label="屏幕亮度"><output for="home-brightness"></output>';
 host.insertBefore(control,document.getElementById('motion'));
 const range=control.querySelector('input'),output=control.querySelector('output');
 let monitor,timer,wanted=null,work=null,reading=null,revision=0;
 function show(value){range.value=String(value);output.textContent=value+'%';range.setAttribute('aria-valuetext',value+'%');}
 async function refresh(){
  if(reading)return reading;if(work||wanted!==null)return;
  const ticket=revision;
  reading=(async()=>{try{const state=await window.ambient.brightness();if(work||wanted!==null||ticket!==revision)return;monitor=state.monitors.find(m=>m.id===monitor?.id)||state.monitors[0];control.hidden=!state.supported||!monitor;if(monitor){control.title=monitor.name+' · 拖动立即调节亮度';show(monitor.value);}}catch(e){control.title='暂时无法读取屏幕亮度，可在高级设置重新检测。';}finally{reading=null;}})();return reading;
 }
 async function flush(){
  clearTimeout(timer);if(work)return work;if(wanted===null||!monitor)return;
  work=(async()=>{while(wanted!==null){const value=wanted;wanted=null;try{const result=await window.ambient.brightness({id:monitor.id,value}),actual=result.monitors.find(m=>m.id===monitor.id);if(actual){monitor=actual;if(wanted===null)show(actual.value);}}catch{toast('暂时无法调整屏幕亮度，请在高级设置重新检测。');if(wanted===null)show(monitor.value);}}})().finally(()=>{work=null;});return work;
 }
 range.oninput=()=>{revision++;wanted=Number(range.value);show(wanted);clearTimeout(timer);timer=setTimeout(flush,100);};
 // Finish a hardware write before another page takes its preview baseline.
 navigation.register('home',{leave:async()=>{await flush();return true;}});
 const observer=new MutationObserver(()=>{if(navigation.view==='home')refresh();});observer.observe(document.body,{attributes:true,attributeFilter:['data-view']});
 window.addEventListener('focus',refresh);control.addEventListener('pointerenter',refresh);
 refresh();attached={refresh,settle:flush};return attached;
}
