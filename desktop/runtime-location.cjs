const fs=require('node:fs'),path=require('node:path');

// A historical development pointer is not permission to overwrite a checkout.
// Deliberate external runtimes remain available via AMBIENT_RUNTIME_DIR.
exports.runtimeRoot=({packaged,localRoot,dataRoot,override})=>
 path.resolve(override||(!packaged?localRoot:path.join(dataRoot,'runtime')));

exports.claimSetupIntro=userData=>{
 const file=path.join(userData,'setup-intro-seen');
 try{fs.mkdirSync(userData,{recursive:true});fs.writeFileSync(file,'1\n',{flag:'wx'});return true;}
 catch{return false;}
};
