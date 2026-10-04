/** Actual Electron + backend; all state and audio fixtures live in a new temp folder. */
const {_electron:electron}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{execFileSync}=require('node:child_process');
const args=Object.fromEntries(process.argv.slice(2).reduce((rows,value,i,all)=>i%2===0?[...rows,[value,all[i+1]]]:rows,[]));
const runtime=path.resolve(args['--runtime']||''),mode=args['--mode']||'player';
if(!args['--runtime']||!args['--output']||!['fresh','player','corrupt','partial'].includes(mode))throw Error('Usage: node scripts/smoke-desktop.cjs --runtime RUNTIME --output REPORT_JSON [--package PACKAGE_DIR] [--mode player|fresh|corrupt|partial]');
 const source=path.resolve(__dirname,'..'),report={mode,errors:[]};
(async()=>{
 const data=execFileSync(path.join(runtime,'vendor/ACE-Step-1.5/.venv/Scripts/python.exe'),[path.join(__dirname,'smoke-fixture.py'),'--runtime',runtime,'--mode',mode],{encoding:'utf8',windowsHide:true}).trim();
 const launch=args['--package']?{executablePath:path.join(path.resolve(args['--package']),'Ambient Music Nonstop.exe'),args:[]}:{args:[source]};
 const app=await electron.launch({...launch,env:{...process.env,AMBIENT_NO_WORKER:'1',AMBIENT_DATA_DIR:data,AMBIENT_RUNTIME_DIR:runtime,AMBIENT_USER_DATA:path.join(data,'profile')},timeout:240000});
 let page;
 try{
  // Startup now has a visible runtime-health window before the player window.
  const deadline=Date.now()+240000;
  while(!page&&Date.now()<deadline){page=app.windows().find(p=>/\/ui\/index\.html$/.test(p.url().replaceAll('\\','/')));if(!page)await new Promise(r=>setTimeout(r,200));}
  if(!page)throw Error('Main application window did not open after runtime checks');
  page.setDefaultTimeout(30000);page.on('pageerror',e=>report.errors.push(e.message));
  if(['corrupt','partial'].includes(mode)){await page.waitForSelector('#config-recovery[open]');report.configRecoveryVisible=true;await page.locator('#config-recovery button').click();}
  if(mode!=='player'){await page.waitForSelector('#first-setup[open]');report.firstSetupVisible=true;}
  else{
   await page.waitForFunction(()=>document.getElementById('pool-status')?.textContent.includes('2 段声音'));
   await page.evaluate(async()=>{window.qa=await import('./app.js');});
   report.audio=await page.evaluate(async()=>{
    await qa.audio.next();await qa.audio.layer('rain',.2);
    const buffer=qa.audio.buffers.get('rain');return {playing:qa.audio.playing,current:!!qa.audio.current,state:qa.audio.context.state,ambienceRate:buffer.sampleRate,ambienceBytes:buffer.length*buffer.numberOfChannels*4};
   });
   assert.equal(report.audio.playing,true);assert.equal(report.audio.current,true);assert.equal(report.audio.state,'running');assert.equal(report.audio.ambienceRate,24000);
   await page.evaluate(()=>qa.audio.layer('rain',0));await page.waitForTimeout(1800);
   report.ambienceReleased=await page.evaluate(()=>!qa.audio.layers.has('rain')&&!qa.audio.buffers.has('rain'));assert.equal(report.ambienceReleased,true);
   const before=page.url();await page.evaluate(()=>{location.href='https://example.com/';});await page.waitForTimeout(500);assert.equal(page.url(),before);report.navigationBlocked=true;
   report.outputFallback=await page.evaluate(async()=>{qa.outputDevices.value='disconnected-test-device';await qa.outputDevices.refresh();return qa.outputDevices.value==='';});assert.equal(report.outputFallback,true);
   await page.evaluate(()=>qa.audio.toggle());
  }
  report.application=await app.evaluate(({app})=>({name:app.getName(),version:app.getVersion()}));
  assert.deepEqual(report.errors,[]);report.ok=true;
  fs.mkdirSync(path.dirname(path.resolve(args['--output'])),{recursive:true});await page.screenshot({path:args['--output'].replace(/\.json$/,'.png')});
 }finally{
  if(page&&!page.isClosed())await page.evaluate(()=>window.ambient?.setUnsaved(false)).catch(()=>{});
  await app.close();fs.mkdirSync(path.dirname(path.resolve(args['--output'])),{recursive:true});fs.writeFileSync(args['--output'],JSON.stringify({...report,data},null,2)+'\n');
 }
 console.log(JSON.stringify(report));
})().catch(error=>{console.error(error);process.exitCode=1;});
