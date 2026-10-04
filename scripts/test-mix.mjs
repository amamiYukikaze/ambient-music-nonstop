import assert from 'node:assert/strict';
import {apportion,redistribute} from '../ui/mix-editor.js';
assert.deepEqual(redistribute({a:50,b:25,c:25},'c',35),{a:43,b:22,c:35});
assert.deepEqual(redistribute({a:50,b:25,c:25},'c',35,['a']),{a:50,b:15,c:35});
assert.deepEqual(redistribute({a:50,b:25,c:25},'c',95,['a']),{a:50,b:0,c:50});
assert.deepEqual(redistribute({a:50,b:25,c:25},'c',0,['a','b']),{a:50,b:25,c:25});
assert.deepEqual(redistribute({a:50,b:25,c:25},'a',1,['a']),{a:50,b:25,c:25});
let values=apportion({a:2,b:3,c:7,d:0});
for(let i=0;i<1000;i++){const before=values.a;values=redistribute(values,['b','c','d'][i%3],(i*17)%101,['a']);assert.equal(values.a,before);assert.equal(Object.values(values).reduce((a,b)=>a+b,0),100);assert(Object.values(values).every(v=>Number.isInteger(v)&&v>=0&&v<=100));}
console.log('mix invariants: example, pins, saturation, zero weights and 1000 edits passed');
