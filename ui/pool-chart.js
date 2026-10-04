const COLORS=['#dfba91','#a9b6df','#e6d19b','#edb7c8','#c8b5e4','#a2d6c6','#c8b095','#8fc7e2'];
export function distribution(styles,pool){
 const counts=new Map(pool.map(p=>[p.style,Math.max(0,Number(p.count)||0)]));
 const total=styles.reduce((n,s)=>n+(counts.get(s.id)||0),0);
 let offset=0;
 return {total,items:styles.map((s,i)=>{const count=counts.get(s.id)||0,share=total?count/total:0,start=offset;offset+=share;return {...s,count,share,start,color:COLORS[i%COLORS.length]};})};
}
export function renderDistribution(bar,legend,styles,pool){
 const {total,items}=distribution(styles,pool);
 bar.setAttribute('aria-label',total?`可播放曲库共 ${total} 首。${items.map(s=>`${s.name} ${s.count} 首，占 ${(s.share*100).toFixed(1)}%`).join('；')}`:'可播放曲库暂无曲目');
 bar.classList.toggle('empty',!total);
 for(const s of items){
  let segment=bar.querySelector(`[data-style="${s.id}"]`),label=legend.querySelector(`[data-style="${s.id}"]`);
  if(!segment){segment=document.createElement('span');segment.dataset.style=s.id;segment.className='pool-segment';segment.setAttribute('aria-hidden','true');bar.append(segment);}
  segment.style.background=s.color;segment.style.transform=`translateX(${s.start*100}%) scaleX(${s.share})`;
  if(!label){label=document.createElement('div');label.dataset.style=s.id;label.className='pool-legend-item';label.append(document.createElement('i'),document.createElement('span'),document.createElement('small'));legend.append(label);}
  label.children[0].style.background=s.color;label.children[1].textContent=s.name;label.children[2].textContent=`${s.count} 首 · ${(s.share*100).toFixed(1)}%`;
 }
}
