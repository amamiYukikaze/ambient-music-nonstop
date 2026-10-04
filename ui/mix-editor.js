/** Integer percentages, proportional redistribution, exact pin preservation. */
export function apportion(weights,total=100){
 const entries=Object.entries(weights),sum=entries.reduce((n,[,v])=>n+Math.max(0,Number(v)||0),0);
 if(!entries.length)return {};
 const parts=entries.map(([id,v],i)=>{const exact=total*(sum?Math.max(0,Number(v)||0)/sum:1/entries.length);return {id,i,value:Math.floor(exact),rest:exact%1};});
 const left=total-parts.reduce((n,p)=>n+p.value,0);[...parts].sort((a,b)=>b.rest-a.rest||a.i-b.i).slice(0,left).forEach(p=>p.value++);
 return Object.fromEntries(parts.map(p=>[p.id,p.value]));
}
export function redistribute(weights,id,wanted,pins=[]){
 if(!(id in weights)||pins.includes(id))return {...weights};
 const locked=Object.entries(weights).filter(([k])=>k!==id&&pins.includes(k)).reduce((n,[,v])=>n+v,0);
 const others=Object.fromEntries(Object.entries(weights).filter(([k])=>k!==id&&!pins.includes(k)));
 const target=Object.keys(others).length?Math.max(0,Math.min(100-locked,Math.round(Number(wanted)||0))):100-locked;
 return {...weights,...apportion(others,100-locked-target),[id]:target};
}
export function mixEditor(container,styles,initial,{pins:initialPins=[],changed=()=>{}}={}){
 let values=apportion(Object.fromEntries(styles.map(s=>[s.id,initial[s.id]||0]))),pins=new Set(initialPins.filter(x=>x in values));
 const preview=document.createElement('div');preview.className='mix-preview';const controls=document.createElement('div');controls.className='mix-controls';container.replaceChildren(preview,controls);const rows=new Map();
 function draw(){for(const s of styles){const r=rows.get(s.id);r.slider.value=r.number.value=values[s.id];r.slider.disabled=r.number.disabled=r.minus.disabled=r.plus.disabled=pins.has(s.id);r.pin.setAttribute('aria-pressed',String(pins.has(s.id)));r.pin.title=pins.has(s.id)?'解除固定':'固定此占比';r.segment.style.flexGrow=values[s.id];r.segment.title=`${s.name} ${values[s.id]}%`;r.out.textContent=`${values[s.id]}%`;}}
 function update(id,value){values=redistribute(values,id,value,[...pins]);draw();changed({...values},[...pins]);}
 styles.forEach((s,i)=>{
  const row=document.createElement('div');row.className='mix-row';row.dataset.style=s.id;
  const title=document.createElement('span');title.textContent=s.name;
  const pin=document.createElement('button');pin.type='button';pin.className='pin-toggle';pin.setAttribute('aria-label',`固定${s.name}占比`);pin.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m8 3 8 0-1 6 4 4v2H5v-2l4-4-1-6Zm4 12v7"/></svg>';
  const slider=document.createElement('input');slider.type='range';slider.min=0;slider.max=100;slider.step=1;slider.setAttribute('aria-label',`${s.name}占比`);
  const out=document.createElement('output');const number=document.createElement('input');number.type='number';number.min=0;number.max=100;number.step=1;number.setAttribute('aria-label',`${s.name}百分比`);
  const minus=document.createElement('button'),plus=document.createElement('button');minus.type=plus.type='button';minus.textContent='−1';plus.textContent='+1';minus.setAttribute('aria-label',`${s.name}减少1%`);plus.setAttribute('aria-label',`${s.name}增加1%`);
  const stepper=document.createElement('div');stepper.className='mix-stepper';stepper.append(minus,number,plus);
  pin.onclick=()=>{pins.has(s.id)?pins.delete(s.id):pins.add(s.id);draw();changed({...values},[...pins]);};slider.oninput=()=>update(s.id,slider.value);number.onchange=()=>update(s.id,number.value);minus.onclick=()=>update(s.id,values[s.id]-1);plus.onclick=()=>update(s.id,values[s.id]+1);
  row.append(title,pin,out,slider,stepper);controls.append(row);const segment=document.createElement('i');segment.style.background=['#dfba91','#a9b6df','#e6d19b','#edb7c8','#c8b5e4','#a2d6c6','#c8b095','#8fc7e2'][i%8];preview.append(segment);rows.set(s.id,{slider,number,minus,plus,pin,out,segment});
 });draw();return {get values(){return {...values};},get pins(){return [...pins];},reset(initial){values=apportion(initial);pins.clear();draw();changed({...values},[]);}};
}
