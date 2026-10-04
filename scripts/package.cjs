const { packager } = require('@electron/packager');
const fs = require('node:fs');
const path = require('node:path');
const {exportSource}=require('./release-source.cjs');
(async()=>{
 const root=path.resolve(__dirname,'..');
 const out=path.resolve(root,process.env.AMBIENT_PACKAGE_OUT||'release');
 const relative=path.relative(root,out);if(!relative||relative.startsWith('..')||path.isAbsolute(relative))throw Error('Package output must be inside the project');
 const cachedElectron=path.join(root,'artifacts/electron');
 const source=exportSource(root,path.join(root,'dist','package-source-'+require('../package.json').version+'-'+Date.now()));
 const dirs=await packager({ dir:source,out,electronVersion:require('../package.json').devDependencies.electron,...(fs.existsSync(cachedElectron)?{electronZipDir:cachedElectron}:{}),name:'Ambient Music Nonstop',icon:path.join(source,'desktop/icon.ico'),platform:'win32',arch:'x64',overwrite:true,asar:true,
   ignore:[/^\/builtin-ambience/,/^\/tests/,/^\/\.git/,/^\/\.pytest_cache/,/^\/docs/,/^\/server/,/^\/scripts/],prune:true });
 for(const dir of dirs){
  const target=path.join(dir,'resources/backend');fs.mkdirSync(target,{recursive:true});
  for(const folder of ['server','builtin-ambience'])fs.cpSync(path.join(source,folder),path.join(target,folder),{recursive:true});
  fs.mkdirSync(path.join(target,'scripts'),{recursive:true});
  for(const file of ['generate_worker.py','generate_sa3_worker.py','qc_worker.py','worker_watchdog.py','sa3_audition.py','source_revision.py','window_visibility.py','install-runtime.ps1','runtime_health.py','runtime-spec.json','runtime-backend.lock','runtime-sa3.lock'])fs.copyFileSync(path.join(source,'scripts',file),path.join(target,'scripts',file));
  fs.copyFileSync(path.join(source,'package.json'),path.join(target,'package.json'));
  fs.copyFileSync(path.join(source,'scripts/runtime-spec.json'),path.join(dir,'resources/runtime.json'));
  fs.renameSync(path.join(dir,'LICENSE'),path.join(dir,'LICENSE.electron.txt'));
  for(const file of ['LICENSE','AMBIENCE_ATTRIBUTION.md','THIRD_PARTY_NOTICES.md'])fs.copyFileSync(path.join(source,file),path.join(dir,file));
  fs.mkdirSync(path.join(dir,'builtin-ambience'),{recursive:true});
  for(const file of ['manifest.json','provenance.json'])fs.copyFileSync(path.join(source,'builtin-ambience',file),path.join(dir,'builtin-ambience',file));
  fs.mkdirSync(path.join(dir,'docs'),{recursive:true});
  for(const file of ['RECOVERY_AND_UPGRADE.md','CLEAN_WINDOWS_ACCEPTANCE.md','RELEASE_NOTES_1.0.md'])fs.copyFileSync(path.join(source,'docs',file),path.join(dir,'docs',file));
 }
 console.log(dirs.join('\n'));
 fs.writeFileSync(path.join(out,'build-source.json'),JSON.stringify({source,directories:dirs},null,2)+'\n');
})();
