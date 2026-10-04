export const generationFields={duration:['生成时长','秒',30,180,1],capacity_gb:['曲库上限','GB',1,150,1],crossfade:['跨曲渐变','秒',0,15,1],plays_before_retire:['播放后退休','次',1,100,1],generation_interval:['补库间隔','秒',5,3600,1],minimum_free_gb:['磁盘留白','GB',5,200,1],vram_gb:['显存预算','GiB',2,80,.1]};
const copy=value=>structuredClone(value),equal=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
export class SettingsDraft{
 constructor(response){this.load(response);}
 load(response){this.revision=response.revision;const c=response.config;this.base={styles:copy(c.styles),settings:Object.fromEntries([...Object.keys(generationFields),'style_weights','style_pins'].map(k=>[k,copy(c.settings[k]??(k==='style_pins'?[]:null))])),paths:{images:c.paths.images,ambience:c.paths.ambience}};this.value=copy(this.base);}
 get dirty(){return !equal(this.base,this.value);}
 get payload(){return {revision:this.revision,settings:Object.fromEntries(Object.entries(this.value.settings).filter(([k,v])=>!equal(v,this.base.settings[k]))),styles:equal(this.base.styles,this.value.styles)?null:copy(this.value.styles),paths:Object.fromEntries(Object.entries(this.value.paths).filter(([k,v])=>v!==this.base.paths[k]))};}
}
