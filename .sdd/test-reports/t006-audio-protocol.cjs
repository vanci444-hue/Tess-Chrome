// Independent protocol test: actual hook source with deterministic React/WebAudio/WS doubles.
// This validates callbacks and cleanup; it is not a real browser or microphone test.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const ts=require(path.resolve('node_modules/typescript'));
const transpile=f=>ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
function load(f,requireFn,globals={}){const exports={};vm.runInNewContext(transpile(f),{exports,require:requireFn,...globals},{filename:f});return exports;}
const transcript=load('src/audio/transcript.ts',()=>{throw Error('unexpected import')});
function setup(){
 const effects=[], states=[], changes=[], sockets=[], nodes=[], tracks=[], timers=[];let audioCalls=0;
 const react={useRef:v=>({current:v}),useCallback:f=>f,useEffect:f=>effects.push(f()),useState:v=>{const i=states.length;states.push(v);return[v,x=>{states[i]=typeof x==='function'?x(states[i]):x}];}};
 class WS{static OPEN=1;readyState=1;bufferedAmount=0;sent=[];closed=false;constructor(){sockets.push(this)}send(v){this.sent.push(v)}close(){this.closed=true;this.readyState=3}event(e){this.onmessage?.({data:JSON.stringify({asr_session_id:'a',...e})})}}
 class AC{audioWorklet={addModule:async()=>{}};destination={};closed=false;createGain(){return{gain:{},connect(){}}}createMediaStreamSource(){return{connect(){},disconnect(){}}}resume(){return Promise.resolve()}close(){this.closed=true;return Promise.resolve()}}
 class AW{port={onmessage:null,posted:[],postMessage(v){this.posted.push(v)}};constructor(){nodes.push(this)}connect(){}disconnect(){this.disconnected=true}}
 const track={stopped:false,stop(){this.stopped=true}};tracks.push(track);
 const navigator={mediaDevices:{getUserMedia:async()=>({getTracks:()=>tracks})}};
 const window={addEventListener(){},removeEventListener(){}};
 const api={createAudio:async()=>{audioCalls++;return{session_id:'s',asr_session_id:'a',ws_path:'/ws/sessions/s/audio/a'}},audioSocketUrl:p=>'ws://127.0.0.1'+p};
 const modules={'react':react,'../audio/pcm-worklet.ts?worker&url':{default:'local-worklet'},'../audio/transcript':transcript,'../services/audio':api};
 const hook=load('src/hooks/useRealtimeAsr.ts',name=>{assert.ok(name in modules,name);return modules[name]}, {WebSocket:WS,AudioContext:AC,AudioWorkletNode:AW,navigator,window,ArrayBuffer,setTimeout:f=>{timers.push(f);return f},clearTimeout(){},setInterval:f=>f,clearInterval(){},Date});
 const h=hook.useRealtimeAsr({sessionId:'s',revision:1,text:'base',onText:t=>changes.push(t)});
 return{h,effects,states,changes,sockets,nodes,tracks,timers,get audioCalls(){return audioCalls}};
}
(async()=>{
 const a=setup();await a.h.start();assert.equal(a.audioCalls,1);const ws=a.sockets[0],node=a.nodes[0];
 node.port.onmessage({data:new ArrayBuffer(3200)});assert.equal(ws.sent.length,0,'no PCM before ready');
 ws.event({type:'ready'});assert.equal(a.states[0],'recording');
 node.port.onmessage({data:new ArrayBuffer(3200)});assert.equal(ws.sent.length,1);
 ws.event({type:'partial',seq:1,item_id:'i',text:'first',stash:'part'});assert.equal(a.changes.at(-1),'base\nfirstpart');
 a.h.finish();assert.equal(a.states[0],'finishing');assert.equal(node.port.posted[0],'finish');assert.ok(a.tracks[0].stopped);
 node.port.onmessage({data:new ArrayBuffer(100)});node.port.onmessage({data:'flushed'});
 assert.equal(ws.sent.at(-1),'{"type":"finish"}');assert.equal(ws.sent.length,3);
 node.port.onmessage({data:new ArrayBuffer(3200)});assert.equal(ws.sent.length,3,'no frames after finish');
 ws.event({type:'final',seq:2,item_id:'i',transcript:'final'});ws.event({type:'finished',seq:3,complete:true});
 assert.equal(a.changes.at(-1),'base\nfinal');assert.equal(a.states[0],'finished');assert.ok(ws.closed);assert.equal(a.audioCalls,1,'finish never creates another API call');
 const b=setup();await b.h.start();b.sockets[0].event({type:'ready'});b.sockets[0].event({type:'partial',seq:1,item_id:'i',text:'wrong',stash:''});
 b.h.edit('manual correction');b.nodes[0].port.onmessage({data:'flushed'});b.sockets[0].event({type:'final',seq:2,item_id:'i',transcript:'late wrong'});assert.equal(b.changes.at(-1),'manual correction');
 b.h.discard();assert.equal(b.changes.at(-1),'manual correction');assert.ok(b.sockets[0].closed);
 const c=setup();await c.h.start();c.sockets[0].event({type:'ready'});c.sockets[0].event({type:'partial',seq:1,item_id:'i',text:'text',stash:''});c.nodes[0].port.onmessage({data:new ArrayBuffer(3200)});
 c.sockets[0].event({type:'error',seq:2,code:'ASR_DURATION_LIMIT',message:'limit',incomplete:false});assert.equal(c.states[0],'finishing');assert.equal(c.sockets[0].closed,false);
 c.nodes[0].port.onmessage({data:'flushed'});c.sockets[0].event({type:'final',seq:3,item_id:'i',transcript:'drained final'});c.sockets[0].event({type:'finished',seq:4,complete:true});assert.equal(c.changes.at(-1),'base\ndrained final');
 c.h.markSent();c.sockets[0].event({type:'final',seq:5,item_id:'x',transcript:'late'});assert.equal(c.changes.at(-1),'base\ndrained final');
 const d=setup();await d.h.start();d.sockets[0].event({type:'ready'});for(const dispose of d.effects)dispose?.();assert.ok(d.tracks[0].stopped);assert.ok(d.sockets[0].closed);d.sockets[0].event({type:'final',seq:1,item_id:'x',transcript:'after unmount'});assert.equal(d.changes.length,0);
 console.log('PASS independent actual-hook protocol: ready gate, PCM order, flush/finish, retained final, no business send, edit/discard protection, duration drain, sent generation, unmount release');
})().catch(e=>{console.error(e);process.exitCode=1});
