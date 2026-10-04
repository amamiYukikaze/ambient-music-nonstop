/** Recovery is available before ordinary setup, settings or playback bootstrap. */
function migrationView(){
 const dialog=document.createElement('dialog');dialog.id='startup-migration';dialog.className='transfer-page';dialog.setAttribute('aria-label','恢复曲库迁移');
 const title=document.createElement('h2'),detail=document.createElement('p'),progress=document.createElement('progress');progress.max=100;progress.setAttribute('aria-label','恢复进度');
 dialog.append(title,detail,progress);document.body.append(dialog);dialog.addEventListener('cancel',e=>e.preventDefault());dialog.showModal();
 return {render(state){title.textContent=state.active?'正在恢复曲库迁移…':state.phase==='done'?'曲库迁移已完成':'迁移已暂停';detail.textContent=state.error||'正在检查与清理已验证的文件，请保持窗口开启。';progress.value=state.progress||0;},
  async finish(state){if(['failed','interrupted'].includes(state.phase)){const button=document.createElement('button');button.className='glass';button.textContent='继续，在曲库设置中重试';dialog.append(button);await new Promise(resolve=>button.onclick=resolve);}dialog.close();dialog.remove();}};
}
export async function recoverStartup(api,options={}){
 const health=await api('GET','/health');let state=health.library_migration;
 if(state?.active||['failed','interrupted'].includes(state?.phase)){
  const view=options.renderMigration?null:migrationView();
  const render=options.renderMigration||(s=>view.render(s)),finish=options.finishMigration||(s=>view.finish(s));
  const pause=options.pause||(()=>new Promise(resolve=>setTimeout(resolve,500)));
  render(state);
  while(state.active){await pause();try{state=await api('GET','/library-move');}catch{state={...state,error:'正在重新连接迁移服务，请稍候…'};}render(state);}
  await finish(state);
 }
 await (options.showConfig||showConfigRecovery)(health);
}
export async function showConfigRecovery(health){
 const recovery=health.config_recovery;if(recovery?.status!=='recovered')return;
 const dialog=document.createElement('dialog');dialog.id='config-recovery';dialog.className='draft-dialog';dialog.setAttribute('aria-label','配置恢复');
 const title=document.createElement('h2');title.textContent='配置已安全恢复';
 const message=document.createElement('p');message.textContent=recovery.message;
 const original=document.createElement('p');original.className='fine';original.textContent=`原配置备份：${recovery.original}`;
 const paths=document.createElement('p');paths.className='fine';paths.textContent=`保留的曲库地址：${(recovery.library_paths||[]).join('；')}`;
 const button=document.createElement('button');button.className='glass';button.textContent='知道了，检查设置';
 dialog.append(title,message,original,paths,button);document.body.append(dialog);dialog.addEventListener('cancel',e=>e.preventDefault());
 await new Promise(resolve=>{button.onclick=()=>{dialog.close();dialog.remove();resolve();};dialog.showModal();});
}
