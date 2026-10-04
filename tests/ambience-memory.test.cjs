const {test}=require('node:test');
const assert=require('node:assert/strict');

test('closing a layer stops its nodes and releases the decoded buffer after fading',async()=>{
 const {RoomAudio}=await import('../ui/audio.js');
 const timers=[];const original=global.setTimeout;global.setTimeout=fn=>{timers.push(fn);return timers.length;};
 try{
  let stopped=false,disconnected=false;
  const layer={source:{buffer:{},stop(){stopped=true;},disconnect(){disconnected=true;}},gain:{gain:{setTargetAtTime(){}},disconnect(){}}};
  const audio=Object.assign(Object.create(RoomAudio.prototype),{context:{currentTime:0},layers:new Map([['rain',layer]]),buffers:new Map([['rain',{length:500,numberOfChannels:2}]]),desiredLayers:new Map()});
  await audio.layer('rain',0);for(const timer of timers)timer();
  assert(stopped&&disconnected);assert.equal(audio.layers.size,0);assert.equal(audio.buffers.size,0);assert.equal(layer.source.buffer,null);
 }finally{global.setTimeout=original;}
});

test('ambience budget refuses overcommit before fetching encoded audio',async()=>{
 const {RoomAudio,AMBIENCE_MEMORY_BUDGET}=await import('../ui/audio.js');
 const old=global.window;let fetched=false;global.window={ambient:{audio:async()=>{fetched=true;return new Uint8Array(1);}}};
 try{
  const audio=Object.assign(Object.create(RoomAudio.prototype),{buffers:new Map([['existing',{length:AMBIENCE_MEMORY_BUDGET/4-10,numberOfChannels:1}]]),api:async()=>({decoded_bytes:1024,decode_sample_rate:24000,channels:2,duration:3}),reservedAmbienceBytes:0});
  await assert.rejects(()=>audio.decode('ambience','more'),/关闭|内存/);assert.equal(fetched,false);
 }finally{global.window=old;}
});

test('turning off during asynchronous decoding never retains a silent loop',async()=>{
 const {RoomAudio}=await import('../ui/audio.js');
 const oldWindow=global.window,oldDecoder=global.OfflineAudioContext;let finish;
 global.window={ambient:{audio:async()=>new Uint8Array(10)}};
 global.OfflineAudioContext=class{decodeAudioData(){return new Promise(resolve=>finish=resolve);}};
 try{
  const audio=Object.assign(Object.create(RoomAudio.prototype),{buffers:new Map(),layers:new Map(),api:async()=>({decoded_bytes:700000}),context:{createBufferSource(){assert.fail('silent node must not be created');}}});
  const pending=audio.layer('rain',.3);await new Promise(resolve=>setImmediate(resolve));
  await audio.layer('rain',0);
  finish({length:72000,numberOfChannels:2,duration:3,sampleRate:24000});await pending;
  assert.equal(audio.buffers.size,0);assert.equal(audio.layers.size,0);assert.equal(audio.reservedAmbienceBytes,0);
 }finally{global.window=oldWindow;global.OfflineAudioContext=oldDecoder;}
});
