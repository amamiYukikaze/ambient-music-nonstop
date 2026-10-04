export const AMBIENCE_MEMORY_BUDGET=192*1024**2;
const bufferBytes=buffer=>buffer.length*buffer.numberOfChannels*4;
/** Legacy archives keep their files; trim only a decoded copy until they rotate out. */
export function trimLegacy(context,buffer,track){
  if(track.metadata?.qc?.edge_edit)return {buffer,head:0,tail:0};
  const sr=buffer.sampleRate,hop=Math.round(sr*.01),blocks=Math.floor(buffer.length/hop),levels=[];
  for(let b=0;b<blocks;b++){let sum=0;for(let c=0;c<buffer.numberOfChannels;c++){const y=buffer.getChannelData(c);for(let j=b*hop;j<(b+1)*hop;j+=8)sum+=y[j]*y[j];}levels.push(Math.sqrt(sum/(hop/8*buffer.numberOfChannels)));}
  const middle=levels.slice(Math.floor(blocks/5),Math.floor(blocks*4/5)).sort((a,b)=>a-b),threshold=Math.max(10**(-50/20),(middle[Math.floor(middle.length/2)]||0)*.28);
  function scan(values){let run=0;for(let i=0;i<Math.min(312,values.length);i++){run=values[i]>=threshold?run+1:0;if(run>=12)return Math.max(0,Math.min(3,(i-11)*.01-.06));}return 3;}
  const cap=Math.min(3,buffer.duration*.05),head=Math.min(cap,scan(levels)),tail=Math.min(cap,scan([...levels].reverse()));
  if(head+tail<.02)return {buffer,head:0,tail:0};
  const begin=Math.round(head*sr),end=buffer.length-Math.round(tail*sr),edited=context.createBuffer(buffer.numberOfChannels,end-begin,sr);
  for(let c=0;c<buffer.numberOfChannels;c++){const y=edited.getChannelData(c);y.set(buffer.getChannelData(c).subarray(begin,end));const fade=Math.round(sr*.025);for(let i=0;i<fade;i++){y[i]*=i/fade;y[y.length-1-i]*=i/fade;}}
  return {buffer:edited,head,tail};
}
/** Actual decoded-buffer playback. Generation never runs on this clock. */
export class RoomAudio {
  constructor(api, notify, changed) {
    this.api=api; this.notify=notify; this.changed=changed;
    this.context=new AudioContext({latencyHint:'playback'});
    this.music=this.context.createGain(); this.music.gain.value=.5;
    this.analyser=this.context.createAnalyser(); this.analyser.fftSize=2048; this.analyser.smoothingTimeConstant=.7;
    this.limiter=this.context.createDynamicsCompressor(); this.limiter.threshold.value=-3; this.limiter.knee.value=3; this.limiter.ratio.value=12; this.limiter.attack.value=.004; this.limiter.release.value=.2;
    this.music.connect(this.analyser); this.analyser.connect(this.limiter); this.limiter.connect(this.context.destination);
    this.voices=new Set(); this.layers=new Map(); this.buffers=new Map(); this.current=null; this.playing=false; this.busy=false; this.style='lofi'; this.nextAttempt=0;
    setInterval(()=>this.tick(),400);
    setInterval(()=>{ for(const voice of this.voices) this.ping(voice,{playing:this.playing}).catch(e=>this.notify(e.message)); },5000);
  }
  async decode(kind,id) {
    if(kind==='ambience'){
      const info=await this.api('GET',`/ambience/${id}/info`),reserved=info.decoded_bytes;
      const used=()=>[...this.buffers.values()].reduce((sum,buffer)=>sum+bufferBytes(buffer),0);
      if(!Number.isSafeInteger(reserved)||reserved<=0||reserved>AMBIENCE_MEMORY_BUDGET||used()+(this.reservedAmbienceBytes||0)+reserved>AMBIENCE_MEMORY_BUDGET)throw Error('同时开启的环境声已达到内存上限，请先关闭一层声音再试。');
      this.reservedAmbienceBytes=(this.reservedAmbienceBytes||0)+reserved;const epoch=this.ambienceEpoch;
      try{
        const data=await window.ambient.audio(kind,id),decoder=new OfflineAudioContext(2,1,24000);
        const buffer=await decoder.decodeAudioData(data.buffer.slice(data.byteOffset,data.byteOffset+data.byteLength));
        if(buffer.numberOfChannels>2||buffer.duration>180.25||buffer.sampleRate!==24000||used()+this.reservedAmbienceBytes-reserved+bufferBytes(buffer)>AMBIENCE_MEMORY_BUDGET)throw Error('环境声超过内存或时长限制，请裁剪后重新导入。');
        if(!this.blocked&&epoch===this.ambienceEpoch&&this.desiredLayers?.get(id)>0)this.buffers.set(id,buffer);
        return buffer;
      }finally{this.reservedAmbienceBytes-=reserved;}
    }
    const data=await window.ambient.audio(kind,id);
    return this.context.decodeAudioData(data.buffer.slice(data.byteOffset,data.byteOffset+data.byteLength));
  }
  async ping(voice,body) {
    if(voice.finished)return;
    if(body.finish)voice.finished=true;
    try { await this.api('POST',`/plays/${voice.session}`,body); }
    catch(e) { if(body.finish)voice.finished=false; throw e; }
  }
  elapsed(voice=this.current) { return voice ? Math.max(0,this.context.currentTime-voice.start) : 0; }
  async prepare() {
    if(this.blocked)return null;
    const old=this.current;
    if(this.prepared && this.prepared.from===old?.session && this.prepared.style===this.style)return this.prepared.promise;
    const style=this.style,from=old?.session;
    const promise=(async()=>{const response=await this.api('GET',`/next?style=${style}${old?`&exclude=${old.track.id}`:''}`);if(!response.track)return null;const edit=trimLegacy(this.context,await this.decode('audio',response.track.id),response.track);return {track:response.track,...edit};})();
    this.prepared={from,style,promise};
    promise.catch(()=>{if(this.prepared?.promise===promise)this.prepared=null;});
    return promise;
  }
  async add(prepared,manual=false) {
    if(this.blocked)return;
    const {track,buffer}=prepared;
    if(!this.playing)return;
    const session=(await this.api('POST','/plays',{track_id:track.id})).session_id;
    if(!this.playing){await this.api('POST',`/plays/${session}`,{playing:false,finish:true,reason:'pause'});return;}
    const source=this.context.createBufferSource(),gain=this.context.createGain(); source.buffer=buffer;
    const start=this.context.currentTime, previous=this.current;
    const crossfade=previous?Math.min(manual?1.2:(this.crossfade??6),Math.max(0,previous.buffer.duration-this.elapsed(previous))):.025;
    gain.gain.setValueAtTime(crossfade ? 0 : 1,start);
    if(crossfade)gain.gain.linearRampToValueAtTime(1,start+crossfade);
    source.connect(gain); gain.connect(this.music);
    const voice={source,gain,track,session,start,buffer,edgeEdit:{head:prepared.head,tail:prepared.tail},finished:false};
    if(previous && crossfade) {
      previous.gain.gain.cancelScheduledValues(start);
      previous.gain.gain.setValueAtTime(previous.gain.gain.value,start);
      previous.gain.gain.linearRampToValueAtTime(0,start+crossfade);
    }
    if(manual)for(const old of this.voices){old.endReason='skip';this.ping(old,{playing:this.playing,finish:true,reason:'skip'}).catch(e=>this.notify(e.message));old.gain.gain.cancelScheduledValues(start);old.gain.gain.setValueAtTime(old.gain.gain.value,start);old.gain.gain.linearRampToValueAtTime(0,start+crossfade);old.source.stop(start+crossfade);}
    this.current=voice;this.voices.add(voice);
    source.onended=()=>{
      this.voices.delete(voice); source.disconnect(); gain.disconnect();
      if(!voice.finished)this.ping(voice,{playing:this.playing,finish:true,reason:voice.endReason||'ended'}).then(()=>this.changed()).catch(e=>this.notify(e.message));
      if(this.current===voice){this.current=null;this.nextAttempt=0;this.changed();}
    };
    source.start(start); this.changed();
  }
  async next(manual=false) {
    if(this.busy||this.blocked)return;
    this.busy=true;
    try {
      this.playing=true;
      await this.context.resume();
      const response=await this.prepare();
      this.prepared=null;
      if(!this.playing)return;
      if(response && response.track.style!==this.style){queueMicrotask(()=>this.next(manual));return;}
      if(response) {
        this.waitingNotified=false;
        this.playing=true;
        await this.add(response,manual);
      } else {
        this.nextAttempt=Date.now()+5000;
        if(manual || !this.current && !this.waitingNotified){this.notify('这个风格还没有新的曲目，正在等待声音库。');this.waitingNotified=true;}
      }
    } catch(e) {this.nextAttempt=Date.now()+10000;this.notify(`播放未完成：${e.message}`);}
    finally {this.busy=false;this.changed();}
  }
  async toggle() {
    if(this.blocked)return;
    if(this.playing) {
      const updates=[...this.voices].map(v=>this.ping(v,{playing:true}));
      this.playing=false;await this.context.suspend();
      Promise.all(updates).catch(e=>this.notify(e.message));
    } else {
      this.playing=true;await this.context.resume();
      Promise.all([...this.voices].map(v=>this.ping(v,{playing:false}))).catch(e=>this.notify(e.message));
      if(!this.current)await this.next();
    }
    this.changed();
  }
  tick() {
    if(this.blocked||!this.playing || this.busy || Date.now()<this.nextAttempt)return;
    if(this.current && this.current.buffer.duration-this.elapsed()<18 && !this.prepared)this.prepare().catch(e=>{this.nextAttempt=Date.now()+5000;this.notify(e.message);});
    if(!this.current || this.current.buffer.duration-this.elapsed()<Math.max(.1,this.crossfade??6))this.next();
  }
  async removeCurrent() {
    if(!this.current)return;
    const id=this.current.track.id;
    this.prepared=null;
    for(const v of [...this.voices]) {v.endReason='delete';await this.ping(v,{playing:this.playing,finish:true,reason:'delete'});v.source.stop();}
    this.current=null;await this.api('DELETE',`/tracks/${id}`);await this.next(true);
  }
  setVolume(value) { this.music.gain.setTargetAtTime(value,this.context.currentTime,.12); }
  async layer(id,level) {
    if(this.blocked)return;
    const epoch=this.ambienceEpoch;
    this.desiredLayers ??= new Map();this.desiredLayers.set(id,level);
    const existing=this.layers.get(id);
    if(existing) {
      clearTimeout(existing.releaseTimer);existing.gain.gain.setTargetAtTime(level*.6,this.context.currentTime,.4);
      if(!level)existing.releaseTimer=setTimeout(()=>{
        if(this.layers.get(id)!==existing||this.desiredLayers.get(id)>0)return;
        existing.source.stop();existing.source.disconnect();existing.gain.disconnect();existing.source.buffer=null;
        this.layers.delete(id);this.buffers.delete(id);this.desiredLayers.delete(id);
      },1600);
      return;
    }
    if(!level){this.buffers.delete(id);return;}
    let buffer=this.buffers.get(id);
    if(!buffer){
      this.bufferLoads??=new Map();
      let pending=this.bufferLoads.get(id);
      if(!pending){pending=this.decode('ambience',id);this.bufferLoads.set(id,pending);}
      try{buffer=await pending;}
      finally{if(this.bufferLoads.get(id)===pending)this.bufferLoads.delete(id);}
    }
    // Re-check after asynchronous loading to avoid duplicate nodes from rapid slider events.
    if(this.blocked||epoch!==this.ambienceEpoch)return;
    if(!this.desiredLayers.get(id)){this.buffers.delete(id);return;}
    if(this.layers.has(id))return this.layer(id,this.desiredLayers.get(id)||0);
    const source=this.context.createBufferSource(),gain=this.context.createGain();
    source.buffer=buffer;source.loop=true;gain.gain.value=0;source.connect(gain);gain.connect(this.limiter);
    source.start();gain.gain.setTargetAtTime((this.desiredLayers.get(id)||0)*.6,this.context.currentTime,.4);
    this.layers.set(id,{source,gain});
  }
  async suspendForMigration(){
    this.blocked=true;this.playing=false;this.prepared=null;this.ambienceEpoch=(this.ambienceEpoch||0)+1;
    const voices=[...this.voices];
    await Promise.allSettled(voices.map(v=>this.ping(v,{playing:false,finish:true,reason:'close'})));
    for(const voice of voices){voice.source.onended=null;voice.source.stop();voice.source.disconnect();voice.gain.disconnect();}
    this.voices.clear();this.current=null;
    for(const layer of this.layers.values()){clearTimeout(layer.releaseTimer);layer.source.stop();layer.source.disconnect();layer.gain.disconnect();layer.source.buffer=null;}
    this.layers.clear();this.buffers.clear();this.bufferLoads?.clear();await this.context.suspend();this.changed();
  }
}
