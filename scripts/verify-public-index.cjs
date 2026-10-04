/** Prove the fresh public Git index contains exactly the exported bytes. */
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),{execFileSync}=require('node:child_process');
const {verifySource}=require('./release-source.cjs');
const root=path.resolve(process.argv[2]||'.');
verifySource(root,{allowBuildArtifacts:true});
const manifest=JSON.parse(fs.readFileSync(path.join(root,'public-source-manifest.json')));
const expected=[...manifest.files.map(e=>e.path),'public-source-manifest.json'].sort();
const entries=execFileSync('git',['ls-files','--stage','-z'],{cwd:root,encoding:'utf8'}).split('\0').filter(Boolean).map(row=>{
 const [header,name]=row.split('\t');const [mode,oid,stage]=header.split(' ');
 if(stage!=='0'||mode!=='100644')throw Error('Unexpected index stage or file mode: '+name);
 return {name,oid};
});
if(JSON.stringify(entries.map(e=>e.name).sort())!==JSON.stringify(expected))throw Error('Public Git index file list differs from export');
for(const entry of entries){
 const bytes=fs.readFileSync(path.join(root,entry.name));
 const oid=crypto.createHash('sha1').update(Buffer.from('blob '+bytes.length+'\0')).update(bytes).digest('hex');
 if(oid!==entry.oid)throw Error('Staged bytes differ from export (check line endings): '+entry.name);
}
console.log(JSON.stringify({ok:true,staged_files:entries.length,all_blob_hashes_match:true}));
