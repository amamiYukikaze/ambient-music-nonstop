/** Real packaged restart checks using disposable library state; no user data or model generation. */
const {_electron:electron}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),assert=require('node:assert/strict'),{execFileSync}=require('node:child_process');
const args=Object.fromEntries(process.argv.slice(2).reduce((rows,value,i,all)=>i%2===0?[...rows,[value,all[i+1]]]:rows,[]));
if(!args['--runtime']||!args['--package']||!args['--output'])throw Error('Usage: node scripts/startup-check.cjs --runtime RUNTIME --package PACKAGE --output REPORT');
const root=path.resolve(__dirname,'..'),runtime=path.resolve(args['--runtime']),output=path.resolve(args['--output']);
const report={runs:[],errors:[]};fs.mkdirSync(path.dirname(output),{recursive:true});
(async()=>{
 const data=execFileSync(path.join(runtime,'vendor/ACE-Step-1.5/.venv/Scripts/python.exe'),[path.join(__dirname,'smoke-fixture.py'),'--runtime',runtime,'--mode','player'],{encoding:'utf8',windowsHide:true}).trim();
 for(let run=0;run<3;run++){
  const windows=[];const app=await electron.launch({executablePath:path.join(path.resolve(args['--package']),'Ambient Music Nonstop.exe'),args:[],env:{...process.env,AMBIENT_NO_WORKER:'1',AMBIENT_DATA_DIR:data,AMBIENT_RUNTIME_DIR:runtime,AMBIENT_USER_DATA:path.join(data,'profile')},timeout:240000});
  app.on('window',page=>{page.on('pageerror',e=>report.errors.push(e.message));page.on('domcontentloaded',()=>windows.push(page.url()));});
  let main;
  try{
   const deadline=Date.now()+240000;
   while(!main&&Date.now()<deadline){for(const page of app.windows()){if(page.url()&&!windows.includes(page.url()))windows.push(page.url());if(/\/ui\/index\.html$/.test(page.url().replaceAll('\\','/')))main=page;}if(!main)await new Promise(r=>setTimeout(r,100));}
   assert(main,'main window opens');await main.waitForSelector('#pool-status');
   await main.waitForFunction(()=>document.getElementById('pool-status')?.textContent.includes('2 段声音'));
   assert(!windows.some(url=>url.includes('/runtime.html')),'normal launch never opens the installer');
   assert.equal(await main.locator('#first-setup[open]').count(),0);
   const timing=JSON.parse(fs.readFileSync(path.join(data,'.log/startup-last.json')));
   if(run>0)assert.equal(timing.health_mode,'cached');
   report.runs.push({...timing,windows});
  }finally{if(main&&!main.isClosed())await main.evaluate(()=>window.ambient?.setUnsaved(false)).catch(()=>{});await app.close();}
 }
 // Exercise long-check progress and cancellation in the real startup window.
 const temp=fs.mkdtempSync(path.join(os.tmpdir(),'ambient-startup-ui-'));
 fs.writeFileSync(path.join(temp,'main.cjs'),`const {app}=require('electron');app.setPath('userData',require('node:path').join(__dirname,'profile'));app.whenReady().then(()=>{const startup=require(${JSON.stringify(path.join(root,'desktop/startup.cjs'))}).createStartup(${JSON.stringify(root)});startup.update({phase:'deep',stage:'environment-base',completed:2,stages:7});});`);
 const app=await electron.launch({args:[path.join(temp,'main.cjs')]});
 try{const page=await app.firstWindow();await page.waitForFunction(()=>document.getElementById('startup-progress')?.value===2);assert.match(await page.locator('#startup-detail').innerText(),/2 \/ 7/);assert.equal(await page.locator('#install').count(),0);await page.screenshot({path:output.replace(/\.json$/,'.png')});const exited=new Promise(resolve=>app.process().once('exit',resolve));await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].close());await exited;report.closeCancels=true;}
 finally{await app.close().catch(()=>{});}
 assert.deepEqual(report.errors,[]);report.ok=true;fs.writeFileSync(output,JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
})().catch(error=>{fs.writeFileSync(output,JSON.stringify({...report,error:String(error)},null,2));console.error(error);process.exitCode=1;});
