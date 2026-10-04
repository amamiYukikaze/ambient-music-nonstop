/** Electron rendering + real IPC/PowerShell fixture; no model/dependency installation. */
const { _electron:electron }=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const root=path.resolve(__dirname,'..'),out=path.resolve(process.argv[2]||path.join(root,'artifacts/onboarding-1.0.1'));
const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'ambient-onboarding-'));
fs.mkdirSync(out,{recursive:true});fs.mkdirSync(path.join(tmp,'scripts'));
fs.writeFileSync(path.join(tmp,'scripts/install-runtime.ps1'),`
param($RuntimeRoot)
[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false)
Write-Output 'AMBIENT_PROGRESS {"stage":"uv","phase":"downloading","completed":0,"stages":9,"downloaded":25,"total":100,"file":"uv.zip"}'
Start-Sleep -Seconds 2
Write-Output 'AMBIENT_PROGRESS {"stage":"uv","phase":"downloading","completed":0,"stages":9,"downloaded":75,"total":100,"file":"uv.zip"}'
Start-Sleep -Seconds 2
Write-Output 'fixture detailed log'
Write-Output 'warning: Original English diagnostic remains unchanged.'
if(-not (Test-Path (Join-Path $RuntimeRoot 'retry'))) {Set-Content (Join-Path $RuntimeRoot 'retry') '1';exit 1}
exit 0
`);
fs.writeFileSync(path.join(tmp,'runtime-main.cjs'),`
const {app}=require('electron');const path=require('node:path');
const root=process.env.AMBIENT_UI_SOURCE;
app.setPath('userData',path.join(__dirname,'profile'));
require(path.join(root,'desktop/runtime-health.cjs')).checkRuntime=async()=>({ok:true,errors:[]});
const {ensureRuntime}=require(path.join(root,'desktop/runtime.cjs'));
const {claimSetupIntro}=require(path.join(root,'desktop/runtime-location.cjs'));
app.whenReady().then(()=>ensureRuntime({root:__dirname,localRoot:root,specPath:'fixture',initialCheck:async()=>({ok:false,errors:['Isolated installer fixture']}),claimIntro:()=>claimSetupIntro(app.getPath('userData'))}).then(()=>app.quit()).catch(()=>app.quit()));
`);
const report={scope:'isolated UI/IPC fixtures; real archive downloads tested separately',errors:[]};
(async()=>{
 let app=await electron.launch({args:[path.join(tmp,'runtime-main.cjs')],env:{...process.env,AMBIENT_UI_SOURCE:root}});
 try{
  const page=await app.firstWindow();page.on('pageerror',e=>report.errors.push(e.message));
  await page.waitForSelector('#install-options:not([hidden])');
  assert.equal(await page.locator('#runtime-setup').getAttribute('data-intro-played'),'true');
  await page.waitForFunction(()=>!document.querySelector('.setup-intro'));
  assert.equal(await page.locator('.setup-logs').evaluate(n=>n.open),false);
  await page.screenshot({path:path.join(out,'runtime-ready.png')});
  await page.getByRole('button',{name:'允许检查设备'}).click();
  await page.waitForFunction(()=>!document.querySelector('#install').disabled);
  await page.locator('#install').click();
  await page.waitForFunction(()=>document.querySelector('#runtime-meter').getAttribute('aria-valuenow')==='25.0');
  assert.match(await page.locator('.setup-metrics').innerText(),/25 B.*100 B/);
  await page.locator('.setup-logs summary').click();
  await page.waitForFunction(()=>document.querySelector('#runtime-meter').getAttribute('aria-valuenow')==='75.0');
  await page.waitForTimeout(220);
  await page.screenshot({path:path.join(out,'runtime-downloading.png')});
  await page.waitForFunction(()=>document.querySelector('#install').textContent.includes('重试'));
  assert((await page.locator('.setup-log-scroll').innerText()).includes('warning: Original English diagnostic remains unchanged.'));
  const toggle=page.locator('.setup-logs summary');
  await toggle.click();await page.waitForTimeout(60);await toggle.click();await page.waitForTimeout(230);
  assert.equal(await page.locator('.setup-logs').evaluate(n=>n.open),true);
  assert.equal(await toggle.getAttribute('aria-expanded'),'true');
  await toggle.click();await page.waitForTimeout(230);assert.equal(await page.locator('.setup-logs').evaluate(n=>n.open),false);
  await toggle.click();await page.waitForTimeout(230);report.disclosureInterrupt=true;report.originalLogText=true;
  assert.equal(await page.locator('#install').isEnabled(),true);
  await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setSize(640,560));
  const surface=await page.evaluate(()=>{const s=getComputedStyle(document.body,'::before');return {position:s.position,repeat:s.backgroundRepeat,width:s.width,height:s.height,overflow:document.documentElement.scrollWidth>innerWidth};});
  assert.equal(surface.position,'fixed');assert(surface.repeat.split(', ').every(value=>value==='no-repeat'));assert.equal(surface.overflow,false);
  await page.screenshot({path:path.join(out,'runtime-small-expanded.png')});report.runtime={actualIPC:true,download25to75:true,retry:true,resize:surface};
  await page.emulateMedia({reducedMotion:'reduce'});
  const animations=await page.evaluate(async()=>{const {playSetupIntro}=await import('./onboarding.js');delete document.querySelector('main').dataset.introPlayed;playSetupIntro(document.querySelector('main'));return getComputedStyle(document.querySelector('.setup-intro')).animationDuration;});
  assert.equal(animations,'0.18s');report.reducedMotion=true;
  const exited=new Promise(resolve=>app.process().once('exit',resolve));await page.locator('#install').click();await exited;
 }finally{await app.close().catch(()=>{});}
 // Same profile proves the entrance is consumed across process restarts.
 app=await electron.launch({args:[path.join(tmp,'runtime-main.cjs')],env:{...process.env,AMBIENT_UI_SOURCE:root}});
 try{const page=await app.firstWindow();await page.waitForSelector('#install-options:not([hidden])');assert.equal(await page.locator('#runtime-setup').getAttribute('data-intro-played'),null);report.introOnce=true;}
 finally{await app.close();}
 // Model and first-track states are controlled fixtures, rendered by production setup.js.
 const css=['style.css','advanced.css','settings-room.css','room-interactions.css','typography.css','onboarding.css'];
 fs.writeFileSync(path.join(tmp,'setup.html'),`<!doctype html><html><head><meta charset="utf-8"><base href="${pathToFileURL(path.join(root,'ui')).href}/">${css.map(name=>'<link rel="stylesheet" href="'+pathToFileURL(path.join(root,'ui',name)).href+'">').join('')}</head><body class="setup-pending" data-view="home"><script type="module" src="${pathToFileURL(path.join(tmp,'setup-fixture.js')).href}"></script></body></html>`);
 fs.writeFileSync(path.join(tmp,'setup-fixture.js'),`
 import {ensureSetup} from ${JSON.stringify(pathToFileURL(path.join(root,'ui/setup.js')).href)};
 const styles=${JSON.stringify(JSON.parse(fs.readFileSync(path.join(root,'server/styles.json'))))};
 const fixture=window.fixture={setup:{complete:false},download:{active:false,phase:'idle'},first_job:null};
 const config={setup:fixture.setup,paths:{models:'C:/Models'},styles,settings:{library_path:'C:/Music',enabled_styles:['lofi'],style_weights:Object.fromEntries(styles.map(s=>[s.id,s.id==='lofi'?100:0])),style_pins:[]}};
 window.ambient={claimSetupIntro:async()=>true,chooseFolder:async()=>null,hfHelp:async()=>{}};
 ensureSetup(async(method,route)=>{
  if(route==='/health')return {};
  if(route==='/setup')return structuredClone(fixture);
  if(route==='/configuration')return {config};
  if(route==='/setup/scan'){fixture.setup.hardware={ace:true,sa3:true,ram_gb:32,gpus:[{name:'NVIDIA fixture',vram_gb:8}]};return fixture.setup.hardware;}
  if(route==='/setup/models'){fixture.download={active:true,phase:'manifest',downloaded:0,total:0};return {};}
  if(route==='/setup/first'){fixture.first_job={status:'queued'};return {};}
  throw Error(route);
 });
 `);
 fs.writeFileSync(path.join(tmp,'setup-main.cjs'),`const {app,BrowserWindow}=require('electron');app.setPath('userData',require('node:path').join(__dirname,'model-profile'));app.whenReady().then(()=>new BrowserWindow({width:1100,height:780,webPreferences:{sandbox:true,contextIsolation:true,nodeIntegration:false}}).loadFile(require('node:path').join(__dirname,'setup.html')));app.on('window-all-closed',()=>app.quit());`);
 app=await electron.launch({args:[path.join(tmp,'setup-main.cjs')]});
 try{
  const page=await app.firstWindow();page.on('pageerror',e=>report.errors.push(e.message));
  await page.waitForSelector('#first-setup[open]');await page.getByRole('button',{name:'允许扫描设备'}).click();
  await page.getByRole('button',{name:'继续选择模型 →'}).click();await page.getByRole('button',{name:'下载 / 验证模型',exact:true}).click();
  assert.match(await page.locator('#setup-message').innerText(),/确认已获得访问权限/);
  assert.equal(await page.evaluate(()=>fixture.download.phase),'idle');
  await page.locator('#setup-sa3-authorized').check();await page.getByRole('button',{name:'下载 / 验证模型',exact:true}).click();
  await page.evaluate(()=>fixture.download={active:true,phase:'downloading',downloaded:500,total:1000,file:'OriginalModel.bin',eta_seconds:30});
  await page.waitForFunction(()=>document.querySelector('#model-meter')?.getAttribute('aria-valuenow')==='50.0');
  assert.equal(await page.locator('#setup-sa3').isDisabled(),true);
  await page.locator('.setup-logs summary').click();await page.waitForTimeout(230);
  await page.screenshot({path:path.join(out,'model-downloading.png')});
  await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setSize(980,650));
  const bounds=await page.locator('#first-setup').evaluate(n=>{const r=n.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,viewport:[innerWidth,innerHeight]};});
  assert.equal(bounds.x,0);assert.equal(bounds.y,0);assert(Math.abs(bounds.width-bounds.viewport[0])<1);assert(Math.abs(bounds.height-bounds.viewport[1])<1);
  await page.evaluate(()=>fixture.download={active:false,phase:'failed',downloaded:500,total:1000,error:'Original model error'});
  await page.waitForFunction(()=>!document.querySelector('#setup-sa3').disabled);
  assert.match(await page.locator('.setup-log-scroll').innerText(),/Original model error/);
  await page.getByRole('button',{name:'下载 / 验证模型',exact:true}).click();
  await page.evaluate(()=>{fixture.download={active:false,phase:'done',downloaded:1000,total:1000};fixture.setup.models=['stable-audio-3-medium'];});
  await page.getByRole('button',{name:'模型已就绪，继续 →'}).click();
  await page.getByRole('button',{name:'生成第一首 →'}).click();
  await page.evaluate(()=>fixture.first_job={status:'processing'});
  await page.waitForFunction(()=>document.querySelector('.setup-summary').textContent.includes('响度'));
  await page.evaluate(()=>{fixture.first_job={status:'done'};fixture.setup.complete=true;});
  await page.getByRole('button',{name:'走进声音里 →'}).click();
  assert.equal(await page.locator('#first-setup').evaluate(n=>n.open),false);
  report.models={progress:true,lockedDuringDownload:true,retry:true,firstTrack:true,resize:bounds};
 }finally{await app.close();}
 assert.deepEqual(report.errors,[]);report.ok=true;fs.writeFileSync(path.join(out,'onboarding-check.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
})().catch(error=>{console.error(error);process.exitCode=1;});
