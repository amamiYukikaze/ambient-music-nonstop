const {test}=require('node:test');
const assert=require('node:assert/strict');
test('migration is rendered and finishes before setup is queried',async()=>{
 const {recoverStartup}=await import('../ui/startup-recovery.js');
 const events=[];let count=0;
 const api=async(method,route)=>{
  events.push(route);
  if(route==='/health')return {library_migration:{active:true,phase:'cleaning'}};
  if(route==='/library-move')return {active:++count<2,phase:count<2?'cleaning':'done'};
  throw Error('Setup must not start while recovery is active');
 };
 await recoverStartup(api,{renderMigration:s=>events.push('render:'+s.phase),finishMigration:async()=>events.push('finished'),showConfig:async()=>{},pause:async()=>{}});
 events.push('/setup');
 assert.deepEqual(events,['/health','render:cleaning','/library-move','render:cleaning','/library-move','render:done','finished','/setup']);
});

test('damaged or interrupted migration remains visible even when no transfer is running',async()=>{
 const {recoverStartup}=await import('../ui/startup-recovery.js');const events=[];
 await recoverStartup(async()=>({library_migration:{active:false,phase:'failed',error:'journal preserved'}}),{
  renderMigration:s=>events.push(s.error),finishMigration:()=>events.push('acknowledged'),showConfig:()=>events.push('config')
 });
 assert.deepEqual(events,['journal preserved','acknowledged','config']);
});
