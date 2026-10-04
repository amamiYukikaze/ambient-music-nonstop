/** Audit the actual Windows distribution against the public source used to build it. */
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {verifySource,filesIn,scanText}=require('./release-source.cjs');
const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const backendScripts=['generate_worker.py','generate_sa3_worker.py','qc_worker.py','worker_watchdog.py','sa3_audition.py','source_revision.py','window_visibility.py','install-runtime.ps1','runtime_health.py','runtime-spec.json','runtime-backend.lock','runtime-sa3.lock'];
async function verifyPackage(directory,source){
 directory=path.resolve(directory);source=path.resolve(source);
 verifySource(source,{allowBuildArtifacts:true});
 const asar=await import('@electron/asar'),archive=path.join(directory,'resources/app.asar');
 const entries=asar.listPackage(archive).map(p=>p.replaceAll('\\','/').replace(/^\//,''));
 const sourceManifest=JSON.parse(fs.readFileSync(path.join(source,'public-source-manifest.json')));
 const expected=new Map(sourceManifest.files.map(e=>[e.path,e]));
 const asarFiles=[];
 for(const name of entries){
  const native=name.split('/').join(path.sep),entry=asar.statFile(archive,native);
  if(entry.files)continue;
  if(!expected.has(name)&&name!=='public-source-manifest.json')throw Error('Unexpected ASAR file: '+name);
  if(/^(tests|docs|server|scripts|builtin-ambience)\//.test(name)||/(^|\/)(\.pytest_cache|__pycache__|node_modules)(\/|$)/.test(name))throw Error('Excluded directory in ASAR: '+name);
  const bytes=asar.extractFile(archive,native);asarFiles.push(name);
  if(name!=='package.json'&&hash(bytes)!==hash(fs.readFileSync(path.join(source,name))))throw Error('ASAR source mismatch: '+name);
  if(/\.(json|js|cjs|mjs|html|css|md|txt|svg)$/.test(name))scanText(name,bytes.toString('utf8'));
 }
 const appPackage=JSON.parse(asar.extractFile(archive,'package.json'));
 const sourcePackage=JSON.parse(fs.readFileSync(path.join(source,'package.json')));
 const expectedPackage={...sourcePackage};for(const key of ['private','scripts','devDependencies'])delete expectedPackage[key];
 if(JSON.stringify(appPackage)!==JSON.stringify(expectedPackage))throw Error('Packaged package.json differs beyond documented packager pruning');
 const expectedAsar=sourceManifest.files.map(e=>e.path).filter(n=>!/^((tests|docs|server|scripts|builtin-ambience)\/|\.git)/.test(n)&&n!=='package-lock.json');
 // Packager may omit Git housekeeping files, but must retain every product asset.
 for(const name of expectedAsar)if(!asarFiles.includes(name))throw Error('Missing ASAR file: '+name);
 const backend=path.join(directory,'resources/backend');
 const actualBackend=filesIn(backend);
 const expectedBackend=sourceManifest.files.map(e=>e.path).filter(n=>/^(server|builtin-ambience)\//.test(n)||n==='package.json'||backendScripts.some(f=>n==='scripts/'+f)).sort();
 if(JSON.stringify(actualBackend)!==JSON.stringify(expectedBackend))throw Error('Backend file list mismatch');
 for(const name of actualBackend)if(hash(fs.readFileSync(path.join(backend,name)))!==hash(fs.readFileSync(path.join(source,name))))throw Error('Backend source mismatch: '+name);
 if(hash(fs.readFileSync(path.join(directory,'resources/runtime.json')))!==hash(fs.readFileSync(path.join(source,'scripts/runtime-spec.json'))))throw Error('Runtime specification mismatch');
 for(const name of ['Ambient Music Nonstop.exe','LICENSE','LICENSE.electron.txt','LICENSES.chromium.html','AMBIENCE_ATTRIBUTION.md','THIRD_PARTY_NOTICES.md','resources/app.asar'])if(!fs.statSync(path.join(directory,name)).isFile())throw Error('Missing release file: '+name);
 for(const name of ['LICENSE','AMBIENCE_ATTRIBUTION.md','THIRD_PARTY_NOTICES.md','docs/RECOVERY_AND_UPGRADE.md','docs/CLEAN_WINDOWS_ACCEPTANCE.md','docs/RELEASE_NOTES_1.0.md','builtin-ambience/manifest.json','builtin-ambience/provenance.json'])if(hash(fs.readFileSync(path.join(directory,name)))!==hash(fs.readFileSync(path.join(source,name))))throw Error('Release notice mismatch: '+name);
 for(const name of filesIn(directory))if(/(^|\/)(\.git|\.pytest_cache|__pycache__|\.venv|\.env|artifacts|reference-music|MusicLib|staging|models)(\/|$)|\.(sqlite3|pyc)$/.test(name))throw Error('Private/development file in package: '+name);
 return {ok:true,version:sourcePackage.version,asar_files:asarFiles.length,backend_files:actualBackend.length,distribution_files:filesIn(directory).length,source_manifest_sha256:hash(fs.readFileSync(path.join(source,'public-source-manifest.json'))),asar_sha256:hash(fs.readFileSync(archive))};
}
module.exports={verifyPackage};
if(require.main===module){if(process.argv.length!==4)throw Error('Usage: node scripts/verify-package.cjs PACKAGE_DIR PUBLIC_SOURCE_DIR');verifyPackage(process.argv[2],process.argv[3]).then(result=>console.log(JSON.stringify(result,null,2))).catch(error=>{console.error(error);process.exitCode=1;});}
