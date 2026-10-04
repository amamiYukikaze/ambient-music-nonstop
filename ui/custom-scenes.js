import {SCENES,SCENE_OPTIONS} from './scenes.js';
export function registerCustomScenes(items){
 for(const item of items){SCENES[item.id]={...item,asset:item.id,kind:'custom',glows:[],cup:[0,0],window:[0,0,0,0],quotes:['让喜欢的风景，陪着声音。'],focus:item.focus||[.5,.5]};if(!SCENE_OPTIONS.some(o=>o.value===item.id))SCENE_OPTIONS.push({value:item.id,label:item.name+' · 我的风景'});}
}
