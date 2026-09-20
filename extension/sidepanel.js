/* Spike-only local persistence. Payloads are append-only; removal changes active membership. */
const $ = id => document.getElementById(id);
const KEY = 'tess-capture-spike-v1';
let state = { identity: null, sessions: {}, snapshots: [] }, latest = null, busy = false;
const labels = { model:'车型',variant:'版本',paint:'外观',wheels:'轮毂',interior:'内饰',seats:'座位',autopilot:'辅助驾驶',accessories:'配件',vehicle_price:'车辆价格',price_basis:'价格口径',finance_product:'金融产品',down_payment:'首付',principal:'贷款本金',term_months:'期限',monthly_payment:'月供',rate_value:'利率',rate_basis:'利率口径',range_cltc:'CLTC 续航',top_speed:'最高车速',zero_to_hundred:'百公里加速',delivery:'交付'};
const node = (tag, value, cls) => {const el=document.createElement(tag); if(value!==undefined)el.textContent=value;if(cls)el.className=cls;return el;};
const save = () => chrome.storage.local.set({ [KEY]: state });
const sessionKey = identity => JSON.stringify([identity.nickname, identity.contact, identity.session]);
function render() {
  $('identity').hidden = !!state.identity; $('workspace').hidden = !state.identity;
  if (!state.identity) return;
  const key = sessionKey(state.identity), ids = state.sessions[key] || [];
  $('owner').textContent = `${state.identity.nickname} · ${state.identity.session} · ${ids.length}/3 个候选`;
  $('capture').disabled = busy || ids.length >= 3; $('change').disabled = busy;
  $('snapshots').replaceChildren();
  for (const id of ids) {
    const s = state.snapshots.find(x => x.id === id); if (!s) continue;
    const article=node('article'); article.append(node('h2',s.capture.fields.find(f=>f.key==='variant')?.value || '版本尚未读取'));
    article.append(node('p', `${s.capture.completeness==='complete'?'字段完整':'字段缺失，需核对'} · ${new Date(s.capture.captured_at).toLocaleTimeString()}`, 'hint'));
    const dl=node('dl'); for(const f of s.capture.fields){dl.append(node('dt',labels[f.key]||f.key),node('dd',f.unit==='CNY_fen'?`¥${(f.value/100).toLocaleString('zh-CN')}`:Array.isArray(f.value)?(f.value.length?f.value.join('、'):'无额外选配'):`${f.value}${f.unit?' '+f.unit:''}`));}article.append(dl);
    for(const issue of s.capture.issues) article.append(node('p',issue.message,issue.severity==='error'?'warning error':'warning'));
    const inspect=node('button','查看此快照证据','secondary small');inspect.onclick=()=>show(s.capture);article.append(inspect);
    const remove=node('button','移除此候选（保留原始快照）','secondary small');remove.disabled=busy;remove.onclick=async()=>{state.sessions[key]=ids.filter(x=>x!==id);await save();render();};article.append(remove);$('snapshots').append(article);
  }
}
function show(capture){latest=capture;$('json').textContent=JSON.stringify(capture,null,2);$('download').disabled=false;}
$('identity').onsubmit=async event=>{event.preventDefault();const identity={nickname:$('nickname').value.trim(),contact:$('contact').value.trim(),session:$('session').value.trim()};if(!identity.nickname||!identity.session||!identity.contact)return;if(!/^\+?[\d\s()-]{6,20}$/.test(identity.contact)&&!/^\S+@\S+\.\S+$/.test(identity.contact)){ $('contact').setCustomValidity('请输入手机号或邮箱');$('contact').reportValidity();return; }state.identity=identity;await save();render();};
$('contact').oninput=()=> $('contact').setCustomValidity('');
$('change').onclick=async()=>{state.identity=null;latest=null;$('json').textContent='';$('download').disabled=true;$('status').textContent='';await save();render();};
$('capture').onclick=async()=>{
  if(busy||!state.identity)return;
  // Freeze ownership before the async bridge call; never read current selection on completion.
  const owner=structuredClone(state.identity), key=sessionKey(owner);
  if((state.sessions[key]||[]).length>=3){$('status').textContent='已有 3 个候选，请先移除一个。';return;}
  busy=true;render();$('status').textContent='正在读取当前选中配置，并检查 500 ms 稳定窗口…';
  try {
    const response=await chrome.runtime.sendMessage({type:'CAPTURE_CURRENT_CONFIGURATION'});
    if(!response?.ok)throw new Error(response?.error||'插件未收到页面结果，请重新打开侧栏。');
    show(response.capture);
    if(response.capture.readiness!=='ready')throw new Error('页面未稳定，本次未保存。等待官网更新完成后重试；可展开诊断查看原因。');
    const ids=state.sessions[key]||[];if(ids.length>=3)throw new Error('已达到 3 个候选，本次未保存。');
    const id=crypto.randomUUID();state.snapshots.push({id,session_key:key,capture:response.capture});state.sessions[key]=[...ids,id];await save();
    $('status').textContent=response.capture.completeness==='complete'?'已保存当前官网快照。':'已保存部分真实字段；缺失和冲突已列出，不作为完整方案。';
  }catch(error){$('status').textContent=error.message;}finally{busy=false;render();}
};
$('download').onclick=()=>{if(!latest)return;const url=URL.createObjectURL(new Blob([JSON.stringify(latest,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`tess-capture-${latest.captured_at.replaceAll(':','-')}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
chrome.storage.local.get(KEY).then(data=>{if(data[KEY])state=data[KEY];render();}).catch(error=>{$('status').textContent=error.message;});
