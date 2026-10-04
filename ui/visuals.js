import {RoomAtmosphere} from './room-atmosphere.js';
import {SCENES,coverPoint} from './scenes.js';
/** Spectrum at 24 fps, room sprites at 18 fps; no refresh while hidden. */
export function visuals(audio, getWeather, getScene, getEffects) {
  const spectrum=document.querySelector('#spectrum'), weather=document.querySelector('#weather');
  const sc=spectrum.getContext('2d'), wc=weather.getContext('2d');
  const roomCanvas=document.querySelector('#scene-fx'),room=new RoomAtmosphere(roomCanvas,getScene,getEffects);
  const bins=new Uint8Array(audio.analyser.frequencyBinCount), levels=new Float32Array(64);
  let visible=true, reduced=matchMedia('(prefers-reduced-motion: reduce)').matches, last=0, lastDraw=0, frame=null;
  const weights={rain:0,snow:0,fireflies:0};
  const particles=Object.fromEntries(Object.keys(weights).map(mode=>[mode,Array.from({length:55},()=>({x:Math.random(),y:Math.random(),z:.2+Math.random()*.8}))]));
  const resize=()=>{
    for(const canvas of [spectrum,weather,roomCanvas]){const r=canvas.getBoundingClientRect(),scale=Math.min(1,1440/r.width);canvas.width=Math.round(r.width*scale);canvas.height=Math.round(r.height*scale);}
  };new ResizeObserver(resize).observe(spectrum);window.addEventListener('resize',resize);resize();
  function schedule(){
    if(frame!==null)cancelAnimationFrame(frame);
    frame=null;
    if(visible&&!reduced)frame=requestAnimationFrame(draw);
    else {sc.clearRect(0,0,spectrum.width,spectrum.height);wc.clearRect(0,0,weather.width,weather.height);room.clear();}
  }
  window.ambient.onVisibility(value=>{visible=value;document.body.classList.toggle('low-power',!value);schedule();});
  matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change',e=>{reduced=e.matches;document.body.classList.toggle('reduced',reduced);schedule();});
  function draw(t) {
    frame=requestAnimationFrame(draw);
    if(!visible || reduced)return;
    room.draw(t,0);
    if(t-last<1000/24)return;
    const dt=Math.min((t-lastDraw)/1000,.07);lastDraw=t;last=t-((t-last)%(1000/24));
    const w=spectrum.width,h=spectrum.height;sc.clearRect(0,0,w,h);
    audio.analyser.getByteFrequencyData(bins);
    for(let i=0;i<64;i++){
      const k=Math.round(2*Math.pow(220,i/63));const target=audio.playing ? bins[Math.min(k,bins.length-1)]/255 : 0;
      const rate=target>levels[i]?10:5;levels[i]+=(target-levels[i])*(1-Math.exp(-rate*dt));
      const height=1+levels[i]**2*(h-3), x=i*w/64;
      sc.fillStyle=`rgba(215,223,220,${.22+levels[i]*.6})`;sc.beginPath();sc.roundRect(x,h-height,Math.max(2,w/64-6),height,2);sc.fill();
    }
    const targetMode=getWeather();wc.clearRect(0,0,weather.width,weather.height);
    const scene=SCENES[getScene()]||SCENES.rain,[x,y,rw,rh]=scene.window;
    const a=coverPoint(x,y,weather.width,weather.height,1672,941,scene.focus),b=coverPoint(x+rw,y+rh,weather.width,weather.height,1672,941,scene.focus);
    wc.save();wc.beginPath();wc.rect(a[0],a[1],b[0]-a[0],b[1]-a[1]);wc.clip();
    for(const mode of Object.keys(weights)){
    weights[mode]+=((mode===targetMode?1:0)-weights[mode])*(1-Math.exp(-2.3*dt));
    if(weights[mode]<.002)continue;
    wc.globalAlpha=weights[mode];
    for(const p of particles[mode]){
      const speed=mode==='rain'?.25:mode==='snow'?.025:.004;
      p.y=(p.y+dt*speed*p.z)%1;p.x=(p.x+dt*(mode==='rain'?-.02:.005)+1)%1;
      const x=p.x*weather.width,y=p.y*weather.height;
      if(mode==='rain'){wc.strokeStyle=`rgba(197,220,232,${.10*p.z})`;wc.lineWidth=.8;wc.beginPath();wc.moveTo(x,y);wc.lineTo(x-4,y+18*p.z);wc.stroke();}
      else {wc.fillStyle=mode==='snow'?`rgba(241,243,235,${p.z*.42})`:`rgba(233,225,153,${(.5+.5*Math.sin(t/1200+p.x*50))*.52})`;wc.beginPath();wc.arc(x,y,mode==='snow'?2*p.z:1.5,0,Math.PI*2);wc.fill();}
    }}wc.restore();wc.globalAlpha=1;
  }schedule();
  return {reduce(value){reduced=value;document.body.classList.toggle('reduced',value);schedule();},get reduced(){return reduced;},get stats(){return room.stats;}};
}
