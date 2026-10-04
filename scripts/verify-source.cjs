const path=require('node:path');
const {verifySource}=require('./release-source.cjs');
const root=path.resolve(process.argv[2]||path.join(__dirname,'..'));
const result=verifySource(root,{allowBuildArtifacts:process.argv.includes('--allow-build-artifacts')});
console.log(JSON.stringify({version:result.version,files:result.files.length,bytes:result.files.reduce((n,f)=>n+f.bytes,0),verified:true}));
