const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {progressDecoder}=require('../desktop/runtime-progress.cjs');
const {runtimeRoot,claimSetupIntro}=require('../desktop/runtime-location.cjs');
const {deviceSupport}=require('../desktop/runtime-device.cjs');

test('runtime install requires ACE floor on CUDA device 0; SA3 has a separate hard floor',()=>{
 const device={platform:'win32',arch:'x64',ram:32,vram:8};
 assert.equal(deviceSupport(device).sa3,true);
 for(const values of [{vram:0},{vram:3.7},{ram:15},{platform:'linux'},{arch:'arm64'},{vram:NaN}])assert.equal(deviceSupport({...device,...values}).allowed,false);
 assert.deepEqual(deviceSupport({...device,ram:16,vram:4}),{allowed:true,sa3:false,ram:16,vram:4});
 assert.equal(deviceSupport({...device,ram:23,vram:8}).sa3,false);
 assert.equal(deviceSupport({...device,ram:32,vram:5.7}).sa3,false);
});

test('structured progress and UTF-8 survive every byte split, CR and final unterminated log',()=>{
 const events=[],decoder=progressDecoder(e=>events.push(e));
 const progress={stage:'uv',phase:'downloading',downloaded:42,total:100};
 const bytes=Buffer.from('开始校验\r\nAMBIENT_PROGRESS '+JSON.stringify(progress)+'\n\u001b[32mDownloaded python\u001b[0m\r末行');
 for(const byte of bytes)decoder.write(Buffer.from([byte]));decoder.end();
 assert.deepEqual(events,[{type:'log',text:'开始校验'},{type:'progress',...progress},{type:'log',text:'Downloaded python'},{type:'log',text:'末行'}]);
});
test('malformed progress stays visible in logs and never becomes completion',()=>{
 const events=[],decoder=progressDecoder(e=>events.push(e));decoder.write(Buffer.from('AMBIENT_PROGRESS {bad}\nAMBIENT_PROGRESS {"ok":true}\n'));decoder.end();
 assert.equal(events.length,2);assert(events.every(e=>e.type==='log'));
});
test('packaged app ignores a legacy checkout pointer while explicit overrides still work',()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'ambient-location-'));
 try{const dataRoot=path.join(root,'data'),localRoot=path.join(root,'checkout');fs.mkdirSync(dataRoot);
  fs.writeFileSync(path.join(dataRoot,'runtime-location.json'),JSON.stringify({root:localRoot}));
  assert.equal(runtimeRoot({packaged:true,localRoot,dataRoot}),path.join(dataRoot,'runtime'));
  assert.equal(runtimeRoot({packaged:false,localRoot,dataRoot}),localRoot);
  assert.equal(runtimeRoot({packaged:true,localRoot,dataRoot,override:localRoot}),localRoot);
  assert.equal(JSON.parse(fs.readFileSync(path.join(dataRoot,'runtime-location.json'))).root,localRoot);
  assert.equal(claimSetupIntro(root),true);assert.equal(claimSetupIntro(root),false);
 }finally{fs.rmSync(root,{recursive:true,force:true});}
});
