import {SCENES,coverPoint} from './scenes.js';
const palette={amber:'255,191,99',sun:'255,224,162',ice:'166,209,243',mint:'201,234,163',steam:'243,242,237',shade:'0,0,0'};
function sprite(color){const c=document.createElement('canvas');c.width=c.height=96;const x=c.getContext('2d'),g=x.createRadialGradient(48,48,0,48,48,48);g.addColorStop(0,`rgba(${color},.9)`);g.addColorStop(.25,`rgba(${color},.46)`);g.addColorStop(.6,`rgba(${color},.09)`);g.addColorStop(1,`rgba(${color},0)`);x.fillStyle=g;x.fillRect(0,0,96,96);return c;}
/** Pre-rendered soft sprites; one capped-resolution canvas, no video or WebGL. */
export class RoomAtmosphere{
 constructor(canvas,getScene,getEnabled){this.canvas=canvas;this.ctx=canvas.getContext('2d');this.getScene=getScene;this.getEnabled=getEnabled;this.sprites=Object.fromEntries(Object.entries(palette).map(([k,v])=>[k,sprite(v)]));this.weights={};this.last=0;this.frames=0;this.totalMs=0;this.maxMs=0;this.lastAnchors={};this.time=0;}
 clear(){this.ctx.clearRect(0,0,this.canvas.width,this.canvas.height);}
 draw(t,dt){
  if(!this.getEnabled()){if(this.wasEnabled!==false)this.clear();this.wasEnabled=false;return;}this.wasEnabled=true;if(t-this.last<1000/18)return;
  const elapsed=Math.min((t-(this.previousDraw||t))/1000,.12);this.previousDraw=t;this.last=t-((t-this.last)%(1000/18));this.time+=elapsed;const start=performance.now(),ctx=this.ctx,w=this.canvas.width,h=this.canvas.height,scene=this.getScene()||'rain';
  this.clear();if(!Object.keys(this.weights).length)this.weights[scene]=1;
  for(const id of Object.keys(SCENES)){this.weights[id]??=0;this.weights[id]+=((scene===id?1:0)-this.weights[id])*(1-Math.exp(-1.7*elapsed));if(this.weights[id]<.002)continue;this.paint(SCENES[id],this.time,this.weights[id],w,h);}
  ctx.globalAlpha=1;ctx.globalCompositeOperation='source-over';this.frames++;const ms=performance.now()-start;this.totalMs+=ms;this.maxMs=Math.max(this.maxMs,ms);
 }
 paint(scene,t,opacity,w,h){
  if(scene.custom)return;
  const c=this.ctx,unit=Math.max(w/1672,h/941)*1672,P=(x,y)=>coverPoint(x,y,w,h,1672,941,scene.focus),draw=(key,x,y,rx,ry,a,angle=0)=>{c.save();c.translate(x,y);c.rotate(angle);c.globalAlpha=opacity*a;c.drawImage(this.sprites[key],-rx,-ry,rx*2,ry*2);c.restore();};
  c.globalCompositeOperation='screen';
  scene.glows.forEach(([x,y,r,color,strength,kind],i)=>{const fire=kind==='flame'||kind==='hearth',sway=fire?.0025:.0012,p=P(x+sway*Math.sin(t*(fire?1.5:.29)+i*2),y+.0015*Math.sin(t*(fire?1.9:.36)+i));const pulse=fire?Math.max(.28,.66+.20*Math.sin(t*3.1+i)+.11*Math.sin(t*5.3+i*.4)+.06*Math.sin(t*8.1+i*.7)):.88+.1*Math.sin(t*.5+i*2)+.02*Math.sin(t*.9+i);
   if(fire){c.globalCompositeOperation='source-over';draw('shade',...p,r*unit,r*unit*.85,(1-pulse)*.22);c.globalCompositeOperation='screen';}
   draw(color,...p,r*unit,r*unit*.8,strength*pulse);
   if(kind==='flame')draw('sun',...p,unit*.006,unit*(.014+.007*pulse),.45*pulse,Math.sin(t*1.4+i)*.14);
  });
  const cup=P(...scene.cup);this.lastAnchors[scene.asset]={cup,viewport:[w,h]};
  // Steam disperses and meanders upward; never covers the girl's face.
  for(let i=0;i<20;i++){const age=(t/(6.3+i%3*.9)+i*.618)%1,drift=Math.sin(t*.57+i*1.6)*.011+Math.sin(age*6+i)*.004;const p=P(scene.cup[0]+drift*age,scene.cup[1]-.01-age*.17);const alpha=Math.sin(Math.PI*age)*(.20+(i%3)*.025);draw('steam',...p,unit*(.005+age*.013),unit*(.013+age*.025),alpha,Math.sin(t*.5+i)*.4);}
  const [wx,wy,ww,wh]=scene.window;c.save();const upper=P(wx,wy),lower=P(wx+ww,wy+wh);c.beginPath();c.rect(upper[0],upper[1],lower[0]-upper[0],lower[1]-upper[1]);c.clip();
  for(let i=0;i<30;i++){let x=(i*.618033+t*(scene.kind==='train'?.009:.0013))%1,y=(i*.414214+t*.0018)%1;const p=P(wx+x*ww,wy+y*wh);const firefly=scene.kind==='forest',alpha=(.4+.6*(.5+.5*Math.sin(t*(firefly?1.1:.5)+i*1.7)))*(firefly?.80:.48);draw(firefly?'mint':scene.kind==='snow'?'ice':'sun',...p,unit*(firefly?.0044:.0024),unit*(firefly?.0044:.0024),alpha);}
  (scene.lights||[]).forEach(([x,y,r],i)=>{const p=P(x+.0006*Math.sin(t*.7+i),y+.0008*Math.sin(t*.9+i));draw('amber',...p,unit*r,unit*r*.9,.38+.15*Math.sin(t*.8+i*2));});
  (scene.reflections||[]).forEach(([x,y],i)=>{for(let j=0;j<5;j++){const p=P(x+.002*Math.sin(t*1.1+j+i),y+j*.006);draw('amber',...p,unit*(.004+j*.0012),unit*.0018,(.27+.18*Math.sin(t*1.3+i+j))*(1-j*.12));}});
  if(scene.kind==='sun'){const p=P(.22,.28);draw('sun',...p,unit*.04,unit*.30,.075+.025*Math.sin(t*.4),-.55);}
  if(scene.kind==='sea'){const [center,top,span,width,color]=scene.water||[.234,.478,.212,.08,'sun'];for(let i=0;i<56;i++){const depth=(i*.618)%1,y=top+depth*span,spread=.012+depth*width,x=center+Math.sin(i*12.3)*spread+.0025*Math.sin(t*.8+i),p=P(x,y+.0015*Math.sin(t*1.2+i));const shimmer=Math.pow(.5+.5*Math.sin(t*(1.1+i%4*.15)+i*1.7),2);draw(color,...p,unit*(.002+depth*.014)*(1+.3*Math.sin(t*.6+i)),unit*(.0008+depth*.0012),.20+.72*shimmer);}}
  c.restore();
  if(scene.kind==='hearth'){const [hx,hy]=scene.glows[0];for(let i=0;i<14;i++){const age=(t/(3.8+i%3)+i*.19)%1,p=P(hx+Math.sin(i*7+age*4)*.036,hy+.02-age*.11);draw('amber',...p,unit*.0025,unit*.004,.85*Math.sin(Math.PI*age));}}
 }
 get stats(){return {frames:this.frames,averageDrawMs:this.frames?this.totalMs/this.frames:0,maxDrawMs:this.maxMs,resolution:[this.canvas.width,this.canvas.height],fpsCap:18,anchors:this.lastAnchors};}
}
