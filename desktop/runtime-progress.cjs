const {StringDecoder}=require('node:string_decoder');
const PREFIX='AMBIENT_PROGRESS ';

// stdout/stderr chunks may split UTF-8, JSON and CRLF at any byte boundary.
exports.progressDecoder=emit=>{
 const decoder=new StringDecoder('utf8');let pending='';
 function line(value){
  value=value.replace(/\x1b\[[0-9;]*[A-Za-z]/g,'');if(!value)return;
  if(value.startsWith(PREFIX)){
   try{const event=JSON.parse(value.slice(PREFIX.length));
    if(typeof event.phase==='string'&&typeof event.stage==='string'){emit({type:'progress',...event});return;}
   }catch{}
  }
  emit({type:'log',text:value});
 }
 function consume(value){pending+=value;const lines=pending.split(/\r\n|[\r\n]/);pending=lines.pop();for(const value of lines)line(value);if(pending.length>65536){line(pending.slice(0,65536));pending='';}}
 return {write:chunk=>consume(decoder.write(chunk)),end:()=>{consume(decoder.end());line(pending);pending='';}};
};
