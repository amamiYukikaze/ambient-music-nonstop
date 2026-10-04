/** One sink for the existing music + ambience graph. Never requests microphone capture. */
export class OutputDevices {
  constructor(context,{media=navigator.mediaDevices,saved='',changed=()=>{},notify=()=>{}}={}){
    this.context=context;this.media=media;this.saved=saved==='default'?'':saved;
    this.changed=changed;this.notify=notify;this.value='';this.busy=false;
    this.supported=typeof context.setSinkId==='function'&&typeof media?.enumerateDevices==='function';
    this.options=[{value:'',label:'跟随系统默认设备'}];this.pending=Promise.resolve();
    this.deviceChanged=()=>this.refresh().catch(()=>this.notify('暂时无法刷新输出设备，请稍后重试。'));
  }
  emit(){this.changed({options:this.options,value:this.value,busy:this.busy,supported:this.supported});}
  run(action){
    const task=this.pending.catch(()=>{}).then(async()=>{this.busy=true;this.emit();try{return await action();}finally{this.busy=false;this.emit();}});
    this.pending=task;return task;
  }
  async init(){this.media?.addEventListener('devicechange',this.deviceChanged);return this.refresh(true);}
  dispose(){this.media?.removeEventListener('devicechange',this.deviceChanged);}
  refresh(restore=false){return this.run(async()=>{
    if(!this.supported){this.emit();return;}
    const devices=await this.media.enumerateDevices(),seen=new Set(['','default','communications']);
    this.options=[{value:'',label:'跟随系统默认设备'}];
    for(const d of devices)if(d.kind==='audiooutput'&&!seen.has(d.deviceId)){
      seen.add(d.deviceId);this.options.push({value:d.deviceId,label:d.label||`音频输出设备 ${this.options.length}`});
    }
    const desired=restore?this.saved:this.value;
    const available=this.options.some(o=>o.value===desired);
    const target=available?desired:'';
    try{await this.context.setSinkId(target);this.value=target;}
    catch(error){
      if(!target)throw error;
      await this.context.setSinkId('');this.value='';
      this.notify('所选输出设备暂时不可用，已回到系统默认设备。');return;
    }
    if(desired&&!available)this.notify('所选输出设备已断开，已回到系统默认设备。');
  });}
  choose(id){return this.run(async()=>{
    if(!this.supported)throw new Error('当前环境不支持切换音频输出设备。');
    if(!this.options.some(o=>o.value===id))throw new Error('这个输出设备已不可用，请刷新列表。');
    // Update the saved selection only after the real switch succeeds.
    await this.context.setSinkId(id);this.value=id;
  });}
}
