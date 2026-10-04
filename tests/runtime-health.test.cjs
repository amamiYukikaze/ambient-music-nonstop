const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
test('present but broken Python enters repair instead of backend startup',async()=>{
 const {checkRuntime}=require('../desktop/runtime-health.cjs');
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'ambient-runtime-broken-'));
 const python=path.join(root,'vendor/ACE-Step-1.5/.venv/Scripts/python.exe');
 fs.mkdirSync(path.dirname(python),{recursive:true});fs.writeFileSync(python,'broken executable');
 const result=await checkRuntime({root,specPath:path.resolve('scripts/runtime-spec.json'),managed:true});
 assert.equal(result.ok,false);assert.match(result.errors.join(' '),/Python|runtime/i);
});
test('both startup and install completion use the same health gate',()=>{
 const main=fs.readFileSync(path.join(__dirname,'../desktop/main.cjs'),'utf8');
 const runtime=fs.readFileSync(path.join(__dirname,'../desktop/runtime.cjs'),'utf8');
 assert.match(main,/await checkRuntime\(/);assert.match(runtime,/await checkRuntime\(/);
});
test('closing setup can cancel a health check before Python is launched',async()=>{
 const {checkRuntime}=require('../desktop/runtime-health.cjs');const controller=new AbortController();controller.abort();
 const result=await checkRuntime({root:os.tmpdir(),specPath:'unused',signal:controller.signal});
 assert.equal(result.ok,false);assert.match(result.errors[0],/cancelled/);
});
