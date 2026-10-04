import {coverLayout} from './framing.js';
/** Image-space anchors: normalized coordinates in the 1672 × 941 source artwork. */
export const SCENES={
 rain:{name:'雨夜书房',asset:'rainy-jk-v3',quotes:['把雨声，留在窗外。','今晚，让旋律轻一点。','一盏灯，等一页书翻过。'],window:[.01,.01,.59,.72],cup:[.602,.704],glows:[[.667,.179,.13,'amber',.30],[.145,.77,.055,'amber',.32],[.91,.31,.038,'amber',.22]],kind:'rain'},
 morning:{name:'日光咖啡',asset:'morning-jk-v3',quotes:['让日子，慢慢发光。','晨光落下，音乐刚好。','把今天，过得柔软一点。'],window:[.01,.01,.59,.72],cup:[.602,.704],glows:[[.15,.13,.30,'sun',.14],[.44,.82,.20,'sun',.15],[.664,.18,.06,'sun',.08]],kind:'sun'},
 snow:{name:'雪落无声',asset:'snow-jk-v3',quotes:['雪落无声，心事渐轻。','窗外是冬天，手边是温暖。','这一刻，不必匆忙。'],window:[.01,.01,.59,.72],cup:[.602,.704],glows:[[.667,.179,.135,'amber',.32],[.145,.77,.055,'amber',.35],[.37,.30,.24,'ice',.09]],kind:'snow'},
 forest:{name:'林间小憩',asset:'forest-jk-v3',quotes:['听风经过，树影轻摇。','把片刻，借给森林。','心事有回声，林间有微光。'],window:[.01,.01,.59,.70],cup:[.602,.704],glows:[[.667,.179,.13,'amber',.29],[.47,.22,.19,'sun',.13],[.44,.63,.08,'mint',.11]],kind:'forest'},
 seaside:{name:'海风书页',asset:'seaside-jk-v3',quotes:['让海风，替时间翻页。','远方很蓝，今天很慢。','潮汐往返，思绪靠岸。'],window:[.12,.01,.48,.70],cup:[.602,.704],glows:[[.233,.425,.14,'sun',.21],[.24,.60,.17,'sun',.12],[.68,.20,.07,'sun',.08]],kind:'sea'},
 fireplace:{name:'炉边晚信',asset:'fireplace-jk-v3',quotes:['炉火暖着，夜色慢着。','把世界，调成温暖的音量。','一页书，一炉好时光。'],window:[.005,.005,.145,.55],cup:[.599,.703],glows:[[.356,.608,.145,'amber',.35],[.672,.176,.11,'amber',.27],[.104,.77,.05,'amber',.27],[.921,.451,.037,'amber',.18]],kind:'hearth'},
 train:{name:'晚风列车',asset:'train-jk-v3',quotes:['窗外在远行，心在休息。','下一站，慢一点。','把旅途，听成一首温柔的歌。'],window:[.005,.005,.545,.605],cup:[.586,.692],glows:[[.722,.176,.11,'amber',.28],[.511,.20,.067,'amber',.10],[.078,.766,.04,'amber',.22],[.33,.45,.14,'ice',.09]],kind:'train'}
};
// Reviewed against each source illustration: flame lights must not flicker like electric bulbs.
SCENES.rain.glows=[[.667,.179,.13,'amber',.38],[.145,.768,.058,'amber',.78,'flame'],[.91,.31,.043,'amber',.65,'flame']];
SCENES.snow.glows=[[.667,.179,.135,'amber',.40],[.145,.768,.06,'amber',.80,'flame'],[.91,.31,.043,'amber',.62,'flame'],[.37,.30,.24,'ice',.13]];
SCENES.forest.glows.push([.145,.768,.058,'amber',.76,'flame'],[.91,.31,.04,'amber',.60,'flame']);
SCENES.morning.glows.push([.145,.768,.035,'amber',.25,'flame']);
SCENES.seaside.glows.push([.91,.31,.035,'amber',.38,'flame']);
SCENES.fireplace.glows=[[.356,.608,.16,'amber',.90,'hearth'],[.672,.176,.11,'amber',.38],[.104,.764,.062,'amber',.85,'flame'],[.249,.205,.047,'amber',.68,'flame'],[.832,.205,.045,'amber',.60,'flame'],[.866,.40,.045,'amber',.62,'flame'],[.921,.451,.042,'amber',.65,'flame']];
SCENES.train.glows=[[.722,.176,.11,'amber',.37],[.511,.20,.067,'amber',.16],[.078,.766,.048,'amber',.85,'flame'],[.33,.45,.14,'ice',.13]];
const cityLights=[[.065,.398,.009],[.103,.398,.012],[.14,.398,.01],[.24,.397,.01],[.274,.396,.01],[.315,.396,.01],[.482,.266,.011],[.428,.502,.012],[.469,.59,.014],[.55,.593,.012]];
SCENES.rain.lights=cityLights;SCENES.snow.lights=cityLights;
SCENES.train.lights=[[.165,.45,.008],[.207,.456,.009],[.25,.46,.01],[.351,.462,.01],[.434,.462,.01]];
SCENES.rain.reflections=[[.065,.448],[.103,.438],[.14,.446],[.24,.448],[.274,.44]];
SCENES.snow.reflections=SCENES.rain.reflections;
SCENES.train.reflections=[[.20,.52],[.217,.516],[.25,.517],[.302,.515],[.428,.512]];
// v5 companion art: anchors inspected per image, not copied from the prompt coordinates.
Object.assign(SCENES,{
 'pavilion-rain':{name:'茶亭听雨',asset:'pavilion-rain-jk-v5',quotes:['一檐雨，半盏茶。','山水有声，坐听就好。'],window:[.005,.005,.58,.665],cup:[.552,.727],glows:[[.39,.25,.24,'ice',.14],[.24,.55,.13,'ice',.12]],kind:'rain'},
 garden:{name:'青叶庭园',asset:'garden-jk-v5',quotes:['树影在动，心慢下来。','把午后，写进一页绿意。'],window:[.005,.005,.565,.66],cup:[.59,.684],glows:[[.19,.19,.26,'sun',.22],[.30,.65,.16,'mint',.12],[.91,.065,.07,'amber',.20]],kind:'sun'},
 'coast-night':{name:'月光潮汐',asset:'coast-night-jk-v5',quotes:['月色落海，潮声入梦。','今晚，把思绪交给海风。'],window:[.005,.005,.59,.69],cup:[.604,.679],glows:[[.264,.146,.095,'ice',.25],[.66,.167,.12,'amber',.38],[.258,.50,.18,'ice',.18]],kind:'sea',water:[.257,.468,.20,.065,'ice'],lights:[[.465,.385,.012],[.398,.395,.009],[.573,.32,.009]]},
 'campfire-night':{name:'星湖营火',asset:'campfire-night-jk-v5',quotes:['星光很远，炉火很近。','湖水收下了整片星空。'],window:[.005,.005,.60,.70],cup:[.601,.705],glows:[[.236,.54,.13,'amber',.88,'hearth'],[.102,.439,.055,'amber',.5,'flame'],[.42,.18,.20,'ice',.13]],kind:'hearth',reflections:[[.43,.473],[.547,.468]],lights:[[.43,.427,.008],[.547,.422,.009]]},
 'train-day':{name:'晴光旅途',asset:'train-day-jk-v5',quotes:['沿着河流，向晴天出发。','山色经过，故事还很长。'],window:[.005,.005,.55,.58],cup:[.559,.66],glows:[[.29,.22,.26,'sun',.20],[.445,.77,.16,'sun',.17]],kind:'train'},
 'snow-day':{name:'雪后晴窗',asset:'snow-day-jk-v5',quotes:['雪停之后，日子闪着光。','让一杯温暖，陪雪慢慢融化。'],window:[.005,.005,.57,.71],cup:[.594,.703],glows:[[.169,.14,.16,'sun',.35],[.665,.177,.115,'amber',.3],[.909,.32,.04,'amber',.5,'flame']],kind:'snow'},
 'hearth-day':{name:'日暖木屋',asset:'hearth-day-jk-v5',quotes:['阳光和炉火，各暖一半。','在木香里，停留一会儿。'],window:[.005,.005,.158,.60],cup:[.594,.700],glows:[[.375,.565,.16,'amber',.88,'hearth'],[.07,.23,.15,'sun',.25]],kind:'hearth'},
 'city-night':{name:'晴夜月窗',asset:'city-night-jk-v5',quotes:['月亮替城市，留了一盏灯。','夜很清澈，旋律很轻。'],window:[.005,.005,.58,.71],cup:[.6,.708],glows:[[.262,.118,.10,'sun',.23],[.665,.18,.125,'amber',.38],[.907,.313,.04,'amber',.6,'flame']],kind:'night',lights:cityLights,reflections:[[.26,.486],[.37,.481],[.49,.489]]}
});
// 21 independently illustrated compositions. Coordinates were reviewed against
// the actual art; focus is the face, steam is anchored to each individual cup.
const rooms={
 train:{name:'山河列车',kind:'train',quotes:['山河经过，心慢慢抵达。','把旅途，听成一首温柔的歌。']},
 ocean:{name:'潮声书屋',kind:'sea',quotes:['让海风，替时间翻页。','潮汐往返，思绪靠岸。']},
 forest:{name:'深林小屋',kind:'forest',quotes:['听风经过，树影轻摇。','把片刻，借给森林。']},
 fireplace:{name:'暖炉木屋',kind:'hearth',quotes:['把世界，调成温暖的音量。','一页书，一炉好时光。']},
 city:{name:'城市晴窗',kind:'night',quotes:['让日子，慢慢发光。','远处是城市，手边是好时光。']},
 stream:{name:'山涧茶亭',kind:'forest',quotes:['山水有声，坐听就好。','一盏茶，半日闲。']},
 snow:{name:'雪山暖窗',kind:'snow',quotes:['窗外是冬天，手边是温暖。','雪落无声，心事渐轻。']}
};
// environment, period, face, cup, window, glows, optional water shimmer
const compositions=[
 ['train','day',[.672,.378],[.51,.725],[0,0,.55,.69],[[.647,.03,.10,'amber',.2]]],
 ['train','night',[.655,.435],[.485,.745],[.01,0,.52,.66],[[.66,.06,.12,'amber',.35],[.096,.52,.04,'amber',.3]]],
 ['train','twilight',[.655,.48],[.475,.79],[0,0,.55,.70],[[.65,.05,.11,'amber',.32],[.114,.634,.04,'amber',.35]]],
 ['ocean','day',[.66,.44],[.46,.755],[.045,0,.50,.68],[[.23,.40,.17,'sun',.22]],[.23,.40,.20,.08,'sun']],
 ['ocean','night',[.667,.455],[.508,.766],[.025,0,.51,.69],[[.22,.17,.09,'ice',.23],[.94,.10,.08,'amber',.34]],[.22,.38,.26,.07,'ice']],
 ['ocean','twilight',[.66,.44],[.469,.756],[.02,0,.515,.69],[[.255,.345,.12,'sun',.28],[.894,.898,.04,'amber',.7,'flame']],[.255,.38,.24,.08,'sun']],
 ['forest','day',[.685,.375],[.477,.794],[.005,0,.56,.735],[[.20,.30,.24,'sun',.19],[.20,.675,.04,'amber',.55,'flame']]],
 ['forest','night',[.696,.369],[.487,.773],[.01,0,.575,.70],[[.295,.103,.08,'ice',.22],[.818,.15,.10,'amber',.33],[.423,.727,.04,'amber',.65,'flame']]],
 ['forest','twilight',[.622,.40],[.477,.742],[0,0,.535,.725],[[.18,.32,.15,'sun',.22],[.07,.70,.04,'amber',.65,'flame']]],
 ['fireplace','day',[.692,.43],[.482,.77],[.005,.005,.277,.72],[[.46,.585,.14,'amber',.88,'hearth'],[.13,.26,.19,'sun',.16]]],
 ['fireplace','night',[.68,.434],[.495,.772],[.005,0,.295,.555],[[.46,.53,.15,'amber',.9,'hearth'],[.202,.69,.045,'amber',.7,'flame'],[.505,.175,.035,'amber',.6,'flame']]],
 ['fireplace','twilight',[.671,.405],[.477,.758],[.005,.005,.32,.56],[[.51,.56,.14,'amber',.9,'hearth'],[.959,.828,.045,'amber',.65,'flame']]],
 ['city','day',[.68,.404],[.53,.745],[.01,.005,.53,.69],[[.22,.30,.22,'sun',.19],[.902,.08,.085,'amber',.2]]],
 ['city','night',[.676,.424],[.475,.79],[0,0,.535,.69],[[.53,.472,.08,'amber',.34],[.12,.807,.04,'amber',.65,'flame']]],
 ['city','twilight',[.66,.455],[.516,.756],[.005,.005,.52,.75],[[.171,.33,.13,'sun',.26],[.086,.508,.08,'amber',.25],[.728,.075,.08,'amber',.3]]],
 ['stream','day',[.665,.36],[.529,.70],[0,0,.53,.80],[[.18,.22,.24,'sun',.18]]],
 ['stream','night',[.691,.432],[.514,.77],[0,0,.55,.78],[[.27,.095,.08,'ice',.23],[.905,.124,.10,'amber',.34]]],
 ['stream','twilight',[.67,.425],[.503,.738],[0,0,.548,.84],[[.219,.335,.13,'sun',.26]]],
 ['snow','day',[.666,.416],[.484,.76],[0,0,.54,.70],[[.23,.27,.18,'sun',.2],[.856,.389,.08,'amber',.25]]],
 ['snow','night',[.66,.423],[.453,.792],[0,0,.495,.68],[[.207,.086,.08,'ice',.23],[.986,.425,.12,'amber',.7,'hearth'],[.085,.78,.045,'amber',.75,'flame']]],
 ['snow','twilight',[.66,.412],[.478,.783],[0,0,.53,.735],[[.22,.27,.13,'sun',.25],[.984,.472,.12,'amber',.7,'hearth'],[.94,.888,.035,'amber',.65,'flame']]]
];
for(const [env,period,focus,cup,window,glows,water] of compositions){
 const id=`${env}-${period}-v10`;
 SCENES[id]={...rooms[env],name:`${rooms[env].name} · ${{day:'日光',night:'夜色',twilight:'晨昏'}[period]}`,asset:id,environment:env,period,focus,cup,window,glows,water};
}
for(const scene of Object.values(SCENES))scene.focus??=[.75,.43];
export function timePeriod(hour){return hour>=8&&hour<17?'day':hour>=20||hour<5?'night':'twilight';}
export const STYLE_ENVIRONMENTS={lofi:'city',ambient:'ocean',daily_piano:'city',anime_daily:'train',orchestral:'forest',guzheng:'stream',guitar:'fireplace',artcore:'city'};
export function chooseScene({hour,dominant,weather='none',style='lofi'}){
 const period=timePeriod(hour);
 let env={beach:'ocean',ocean:'ocean',birds:'forest',forest:'forest',stream:'stream',fireflies:'forest',campfire:'fireplace',fireplace:'fireplace',train:'train',snow:'snow',city:'city'}[dominant]||STYLE_ENVIRONMENTS[style]||'city';
 if(weather==='snow')env='snow';
 const custom=Object.entries(SCENES).filter(([,s])=>s.custom&&(s.environment==='any'||s.environment===env)&&(s.period==='any'||s.period===period)&&(!s.styles?.length||s.styles.includes(style)));
 if(custom.length)return custom[Math.floor(hour/2)%custom.length][0];
 // Rain can fall on any environment; only use the original rain-specific art
 // for city/pavilion contexts, never replace an ocean/train scene with a city.
 if(weather==='rain'||dominant==='rain'||dominant==='thunder'){
  if(env==='city'&&period==='night')return 'rain';
  if(env==='stream'&&period==='day')return 'pavilion-rain';
 }
 // A few compatible companion compositions retain the musical character.
 if(env==='city'&&style==='lofi'&&period==='day')return 'morning';
 if(env==='forest'&&style==='orchestral'&&period==='day')return 'garden';
 if(dominant==='campfire'&&period==='night')return 'campfire-night';
 return `${env}-${period}-v10`;
}
export const SCENE_OPTIONS=[{value:'auto',label:'跟随音乐、环境声与时间'},...Object.entries(SCENES).map(([value,s])=>({value,label:s.name,thumbnail:`assets/${s.asset}.png`}))];
export function coverPoint(x,y,w,h,iw=1672,ih=941,focus){const r=coverLayout(w,h,iw,ih,focus);return [r.left+x*r.width,r.top+y*r.height];}
