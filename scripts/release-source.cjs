/** Public source is an explicit list plus hash-checked, provenance-approved media. */
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {execFileSync}=require('node:child_process');
const MANIFEST='public-source-manifest.json';
const sha=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const readJSON=file=>JSON.parse(fs.readFileSync(file,'utf8'));
const writeJSON=(file,value)=>fs.writeFileSync(file,JSON.stringify(value,null,2)+'\n');
const isText=file=>/\.(?:md|txt|json|py|js|mjs|cjs|html|css|ps1|svg|lock|ini)$/.test(file)||['LICENSE','.gitignore','.gitattributes'].includes(file);
function safeFile(root,relative){
 if(typeof relative!=='string'||!relative||relative.includes('\\')||relative.split('/').some(p=>!p||p==='.'||p==='..')||path.isAbsolute(relative)||relative.includes(':'))throw Error('Invalid source path');
 let current=root;
 for(const part of relative.split('/')){current=path.join(current,part);if(fs.existsSync(current)&&fs.lstatSync(current).isSymbolicLink())throw Error('Symlink in source: '+relative);}
 return current;
}
function filesIn(root,ignoreBuild=false){
 const result=[];
 function visit(folder,prefix=''){
  for(const entry of fs.readdirSync(folder,{withFileTypes:true}).sort((a,b)=>a.name.localeCompare(b.name))){
   const name=prefix+entry.name;
   if(ignoreBuild&&(/^(node_modules|dist|release|\.git|\.pytest_cache)(\/|$)/.test(name)||/(^|\/)__pycache__(\/|$)|\.pyc$/.test(name)))continue;
   if(entry.isSymbolicLink())throw Error('Symlink in export: '+name);
   if(entry.isDirectory())visit(path.join(folder,entry.name),name+'/');else if(entry.isFile())result.push(name);else throw Error('Non-file in export: '+name);
  }
 }
 visit(root);return result.sort();
}
function scanText(file,text){
 const rules={
  'personal-path':/[A-Z]:[\\/]+Users[\\/]+(?![<$%])[A-Za-z0-9_\u3400-\u9fff.-]+[\\/]/i,
  'credential':/\b(?:hf_[A-Za-z0-9]{30,}|gh[pousr]_[A-Za-z0-9]{30,}|sk-(?:proj-)?[A-Za-z0-9_-]{40,})\b|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----/,
 };
 for(const [rule,pattern] of Object.entries(rules))if(pattern.test(text))throw Error(`${rule} in ${file}`);
}
function releaseAmbience(manifest,catalog){
 if(catalog.schema_version!==1||!catalog.sources)throw Error('Invalid ambience provenance');
 const selected=[];
 for(const item of manifest){
  if(!/^[a-z][a-z0-9_-]*$/.test(item.id)||item.file!==item.id+'.opus'||!/^[a-f0-9]{64}$/.test(item.sha256))throw Error('Invalid ambience filename or hash');
  if(!Array.isArray(item.sources)||!item.sources.length)throw Error('Missing ambience provenance: '+item.id);
  let permitted=true;
  for(const source of item.sources){
   const record=catalog.sources[source.source_id];if(!record)throw Error('Missing ambience provenance: '+item.id);
   if(record.status==='MANUAL LEGAL/PROVENANCE VERIFICATION REQUIRED'){permitted=false;continue;}
   if(record.status!=='verified')throw Error('Unrecognized provenance status: '+item.id);
   for(const key of ['source_title','author','original_url','license_name','license_url','modification_status','attribution_text','evidence_url'])if(typeof record[key]!=='string'||!record[key].trim())throw Error(`Missing ${key}: ${item.id}`);
   if(record.license_name!==source.license||record.original_url!==source.url)throw Error('Conflicting provenance: '+item.id);
  }
  if(permitted)selected.push(item);
 }
 return selected;
}
function exportSource(root,out){
 root=path.resolve(root);out=path.resolve(out);
 if(fs.existsSync(out))throw Error('Export already exists: '+out);
 const policy=readJSON(path.join(root,'scripts/public-files.json'));
 if(policy.schema_version!==1||!Array.isArray(policy.files)||new Set(policy.files).size!==policy.files.length)throw Error('Invalid public allowlist');
 const ambience=releaseAmbience(readJSON(path.join(root,'builtin-ambience/manifest.json')),readJSON(path.join(root,'builtin-ambience/provenance.json')));
 const selected=[...policy.files,...ambience.map(x=>'builtin-ambience/'+x.file)].sort();
 for(const relative of selected){const file=safeFile(root,relative);if(!fs.statSync(file).isFile())throw Error('Not a source file: '+relative);if(isText(relative))scanText(relative,fs.readFileSync(file,'utf8'));}
 if(selected.some(f=>safeFile(root,f)===out))throw Error('Output conflicts with source');
 fs.mkdirSync(out,{recursive:true});fs.writeFileSync(path.join(out,'.incomplete'),'Export validation has not completed.');
 for(const relative of selected){const destination=safeFile(out,relative);fs.mkdirSync(path.dirname(destination),{recursive:true});if(relative==='server/style_reference_v5.npz')continue;if(isText(relative))fs.writeFileSync(destination,fs.readFileSync(safeFile(root,relative),'utf8').replace(/\r\n/g,'\n'));else fs.copyFileSync(safeFile(root,relative),destination);}
 writeJSON(path.join(out,'builtin-ambience/manifest.json'),ambience);
 for(const item of ambience)if(sha(fs.readFileSync(path.join(out,'builtin-ambience',item.file)))!==item.sha256)throw Error('Ambience hash mismatch: '+item.id);
 execFileSync(process.env.AMBIENT_BUILD_PYTHON||'python',[path.join(root,'scripts/export-style-bank.py'),path.join(root,'server/style_reference_v5.npz'),path.join(out,'server/style_reference_v5.npz')],{stdio:'pipe',windowsHide:true});
 const pkg=readJSON(path.join(out,'package.json'));
 pkg.scripts={start:'electron .',package:'node scripts/package.cjs',icons:'electron scripts/render-brand.cjs','test:mix':'node scripts/test-mix.mjs','test:release':'node --test tests/*.test.cjs','export:github':'node scripts/export-github.cjs','verify:source':'node scripts/verify-source.cjs'};
 writeJSON(path.join(out,'package.json'),pkg);
 fs.writeFileSync(path.join(out,'.gitignore'),['node_modules/','vendor/','.venv*/','dist/','release/','release-artifacts*/','artifacts/','__pycache__/','.pytest_cache/','.cache/','.downloads/','tools/','*.pyc','*.log','*.sqlite3*','.env*','config*.json','runtime-location.json','runtime.json','runtime.json.part','.runtime-backups/','setup-download.json','.runtime-installing',''].join('\n'));
 const entries=selected.map(file=>{const bytes=fs.readFileSync(path.join(out,file));if(isText(file))scanText(file,bytes.toString('utf8'));return {path:file,bytes:bytes.length,sha256:sha(bytes)};});
 writeJSON(path.join(out,MANIFEST),{schema_version:1,version:pkg.version,files:entries});
 fs.unlinkSync(path.join(out,'.incomplete'));
 verifySource(out);return out;
}
function verifySource(root,{allowBuildArtifacts=false}={}){
 const manifest=readJSON(path.join(root,MANIFEST));
 if(manifest.schema_version!==1||manifest.version!==readJSON(path.join(root,'package.json')).version)throw Error('Source version mismatch');
 const listed=manifest.files.map(x=>x.path).sort(),actual=filesIn(root,allowBuildArtifacts).filter(f=>f!==MANIFEST);
 if(new Set(listed).size!==listed.length||JSON.stringify(listed)!==JSON.stringify(actual))throw Error('Unexpected or missing public source files');
 for(const entry of manifest.files){const bytes=fs.readFileSync(safeFile(root,entry.path));if(bytes.length!==entry.bytes||sha(bytes)!==entry.sha256)throw Error('Source hash/size mismatch: '+entry.path);if(isText(entry.path))scanText(entry.path,bytes.toString('utf8'));}
 const ambience=readJSON(path.join(root,'builtin-ambience/manifest.json'));
 if(releaseAmbience(ambience,readJSON(path.join(root,'builtin-ambience/provenance.json'))).length!==ambience.length)throw Error('Unverified ambience in export');
 return manifest;
}
module.exports={exportSource,verifySource,releaseAmbience,scanText,filesIn,safeFile};
