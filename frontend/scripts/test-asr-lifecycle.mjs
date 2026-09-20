/** Deterministic hook lifecycle tests with mocked browser/media/transport, not a real microphone test. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const code = ts.transpileModule(fs.readFileSync('src/hooks/useRealtimeAsr.ts','utf8'), {
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}
}).outputText;
const deferred=()=>{let resolve; const promise=new Promise(r=>{resolve=r});return {promise,resolve};};
function setup({permission,worklet,create}={}) {
  let calls=0,stops=0,closes=0,cleanups=[],states=[],cursor=0,text='手工文字';
  const canceled=[], sockets=[];
  const stream={getTracks:()=>[{stop:()=>stops++}]};
  class Audio {constructor(){this.audioWorklet={addModule:async()=>{if(worklet)await worklet();}};this.destination={};} close(){closes++;return Promise.resolve();} createGain(){return {gain:{},connect(){}};} }
  class Socket {static OPEN=1;constructor(){this.readyState=0;sockets.push(this);}close(){this.readyState=3;} }
  const exports={};
  vm.runInNewContext(code, {exports,require:(id)=> {
    if(id==='react')return {useCallback:fn=>fn,useEffect:fn=>{const f=fn();if(f)cleanups.push(f);},useRef:value=>{const i=cursor++;return states[i]??=( {current:value});},useState:value=>{const i=cursor++;if(!(i in states))states[i]=value;return [states[i],v=>{states[i]=v}];}};
    if(id.includes('pcm-worklet'))return {default:'/worklet.js'};
    if(id.includes('transcript'))return {TranscriptBuffer:class{freeze(){}},};
    if(id.includes('services/audio'))return {createAudio:async(...args)=>{calls++;if(create)return await create(...args);return {session_id:'s',asr_session_id:'a',ws_path:'/ws/a'};},audioSocketUrl:p=>p,cancelAudioReservation:async(...args)=>{canceled.push(args);}};
    throw Error(id);
  },navigator:{mediaDevices:{getUserMedia:async()=>permission?await permission(stream):stream}},
  AudioContext:Audio,AudioWorkletNode:class{port={};connect(){}disconnect(){}},WebSocket:Socket,
  window:{addEventListener(){},removeEventListener(){}},setTimeout,clearTimeout,setInterval,clearInterval});
  const render=()=>{cursor=0;return exports.useRealtimeAsr({sessionId:'s',revision:1,text,onText:v=>text=v});};
  return {render,stream,canceled,sockets,get calls(){return calls},get stops(){return stops},get closes(){return closes},get text(){return text}};
}
{
 const h=setup({permission:()=>{throw Object.assign(Error('blocked'),{name:'NotAllowedError'});}});
 await h.render().start();assert.equal(h.calls,0);assert.equal(h.render().permissionDenied,true);assert.equal(h.render().phase,'failed');assert.equal(h.text,'手工文字');
}
{
 const h=setup({worklet:()=>{throw Error('worklet failed')}});await h.render().start();assert.equal(h.calls,0);assert.equal(h.stops,1);assert.equal(h.closes,1);assert.match(h.render().notice,/音频处理模块/);
}
{
 const gate=deferred();const h=setup({permission:()=>gate.promise});const run=h.render().start();await Promise.resolve();h.render().finish();gate.resolve(h.stream);await run;assert.equal(h.calls,0);assert.equal(h.stops,1);assert.equal(h.render().phase,'finished');
}
{
 const gate=deferred(),entered=deferred();const h=setup({create:()=>{entered.resolve();return gate.promise;}});const run=h.render().start();await entered.promise;h.render().finish();gate.resolve({session_id:'s',asr_session_id:'late-a',ws_path:'/ws/a'});await run;assert.deepEqual(h.canceled,[['s','late-a']]);assert.equal(h.sockets.length,0);assert.equal(h.stops,1);assert.equal(h.text,'手工文字');
}
{
 const h=setup();await h.render().start();await h.render().start();assert.equal(h.calls,1);h.sockets[0].onerror();await Promise.resolve();assert.deepEqual(h.canceled,[['s','a']]);assert.equal(h.render().phase,'failed');assert.equal(h.stops,1);assert.equal(h.text,'手工文字');await h.render().start();assert.equal(h.calls,2);h.render().finish();
}
console.log('PASS 5 ASR lifecycle cases: permissions/worklet fail, late permission/create, duplicate start, WS failure/retry; no auto-send.');
