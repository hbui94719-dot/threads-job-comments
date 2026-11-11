const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const {test} = require('node:test');

function rig(options={}) {
  let stored;
  const tab={id:1,windowId:2,active:true,status:'complete',url:'https://www.threads.com/'};
  const calls=[]; let listener; let context;
  const clone=x=>x===undefined?undefined:JSON.parse(JSON.stringify(x));
  const chrome={
    storage:{local:{get:async()=>({threadsLocalBotV1:clone(stored)}),set:async x=>{stored=clone(x.threadsLocalBotV1);}}},
    alarms:{create:async()=>{},clear:async()=>{},onAlarm:{addListener:()=>{}}},
    tabs:{get:async()=>clone(tab),update:async(id,args)=>Object.assign(tab,args),captureVisibleTab:async()=>{calls.push('capture');return 'data:image/png;base64,test';}},
    scripting:{executeScript:async({args:[action,args]})=>{
      calls.push(action);
      if(action==='collect')return [{result:{posts:[{url:'https://www.threads.com/@seeker/post/ABC',text:'Tìm việc online'}]}}];
      if(action==='prepare'){
        assert.equal(stored.history[args.postUrl].status,'reserved');
        if(options.stopDuringPrepare)await message({action:'stop'});
        return [{result:{prepared:true}}];
      }
      if(action==='submit'){assert.equal(stored.history[args.postUrl].status,'uncertain');return [{result:{clicked:true}}];}
      if(action==='proof'){if(options.proofFails)throw new Error('Uncertain publication');return [{result:{verified:true,replyUrl:'https://www.threads.com/@owner/post/REPLY'}}];}
    }},
    downloads:{download:async()=>1,search:async()=>[{state:options.downloadFails?'interrupted':'complete'}]},
    runtime:{id:'test',getURL:p=>'chrome-extension://test/'+p,onMessage:{addListener:fn=>listener=fn}}
  };
  context=vm.createContext({chrome,URL,Uint8Array,Date,console,Error,Number,Object,JSON,Set,Promise,
    importScripts:()=>{},threadsPageTask:()=>{},fetch:async()=>({ok:true,arrayBuffer:async()=>new Uint8Array([1,2]).buffer}),btoa:s=>Buffer.from(s,'binary').toString('base64'),
    setTimeout:(fn,ms)=>{if(ms===50)return 0;return setTimeout(fn,1);}});
  vm.runInContext(fs.readFileSync(__dirname+'/background.js','utf8'),context);
  async function message(m){return new Promise(resolve=>listener(m,{id:'test'},resolve));}
  return {message,calls,state:()=>clone(stored),tick:()=>vm.runInContext('tick()',context),
    start:(goal=1)=>message({action:'start',tabId:1,username:'owner',text:'Nội dung đã chuẩn bị',goal})};
}
test('persists before submitting and only counts a completed screenshot',async()=>{
  const r=rig();assert.equal((await r.start()).active,true);await r.tick();
  assert.equal(r.state().count,1);assert.equal(r.state().active,false);
  assert.equal(Object.values(r.state().history)[0].status,'captured');
  assert.equal(r.calls.filter(x=>x==='submit').length,1);assert.ok(r.calls.includes('capture'));
});
test('unknown publication stops and cannot be started again',async()=>{
  const r=rig({proofFails:true});await r.start();await r.tick();await r.tick();
  assert.equal(r.state().active,false);assert.equal(r.calls.filter(x=>x==='submit').length,1);
  assert.match((await r.start()).error,/chưa rõ kết quả/);
});
test('stop during draft preparation never clicks send',async()=>{
  const r=rig({stopDuringPrepare:true});await r.start();await r.tick();
  assert.equal(r.state().active,false);assert.ok(!r.calls.includes('submit'));
});
test('failed screenshot keeps posted result blocked without reposting',async()=>{
  const r=rig({downloadFails:true});await r.start();await r.tick();
  assert.equal(Object.values(r.state().history)[0].status,'proof_pending');assert.equal(r.state().count,0);
  assert.match((await r.start()).error,/chưa rõ kết quả/);assert.equal(r.calls.filter(x=>x==='submit').length,1);
});
test('invalid quantity and account are rejected before any page action',async()=>{
  const r=rig();assert.ok((await r.start(501)).error);assert.equal(r.calls.length,0);
  assert.ok((await r.message({action:'start',username:'@owner',goal:1,text:'x',tabId:1})).error);
});
