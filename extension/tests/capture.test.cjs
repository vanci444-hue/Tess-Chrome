// Pure parser regression tests; fixtures are deliberately labelled and are not live-site evidence.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const context = vm.createContext({});
vm.runInContext(fs.readFileSync(require('node:path').join(__dirname, '../capture.js'), 'utf8'), context);
const {parse, money} = context.TessCapture;
const fixture = () => ({ selected: [
  {name:'trim-category-COMBINED_TRIMS',label:'Model Y 后轮驱动版 ¥263,500'},
  {name:'PAINT',label:'星空灰车漆 包括',aria:'星空灰车漆 - 包括'},
  {name:'WHEELS',label:'19 英寸交互风暴轮毂 包括'},
  {name:'PREMIUM_PACKAGE',label:'深色高级内饰 包括'},
  {name:'OptionGroup:AUTOPILOT_PACKAGE',id:'AUTOPILOT_PACKAGE:group:base:radio',label:'基础辅助驾驶 包括'}
],footer:'¥3,060 /月 车辆价格 ¥263,500',groups:[{class_name:'group-REAR_SEATS group--selected_$STY5S',text:'座位布局 五座'}],parameter_lines:[],finance:null});
const get = (capture,key) => capture.fields.find(x=>x.key===key)?.value;
test('vehicle total is anchored instead of interpreting leading monthly payment as price',()=>{
  const result=parse(fixture(),'2026-09-20T00:00:00Z');
  assert.equal(get(result,'vehicle_price'),26350000);
  assert.equal(get(result,'seats'),'五座');
  assert.equal(get(result,'interior'),'深色高级内饰 包括');
  assert.equal(get(result,'autopilot'),'基础辅助驾驶 包括');
  assert(result.issues.some(x=>x.field==='accessories'));
});
test('changed selected configuration produces new values without mutating old projection',()=>{
  const original=fixture(), before=JSON.stringify(original), resultA=parse(original,'A');
  const next=fixture();next.selected[1].label='珍珠白车漆 ¥8,000';next.selected[1].aria='珍珠白车漆 - ¥8,000';next.footer='车辆价格 ¥271,500';
  const resultB=parse(next,'B');
  assert.equal(get(resultA,'vehicle_price'),26350000);assert.equal(get(resultB,'vehicle_price'),27150000);
  assert.match(get(resultB,'paint'),/珍珠白/);assert.equal(JSON.stringify(original),before);
});
test('finance is read only from supplied visible loan projection; absent values remain absent',()=>{
  const p=fixture();p.finance={text:'限时 0 息贷款方案 60 个月 贷款金额 ¥183,600 月供 ¥3,060 年化费率 0.00%',inputs:[{id:'downPaymentAmountInput',value:'¥79,900',label:'首付'},{type:'select-one',value:'限时 0 息贷款方案'}]};
  const result=parse(p,'time');
  assert.equal(get(result,'down_payment'),7990000);assert.equal(get(result,'principal'),18360000);assert.equal(get(result,'monthly_payment'),306000);assert.equal(get(result,'term_months'),60);assert.equal(get(result,'rate_value'),0);assert(!result.issues.some(x=>x.code==='FINANCE_PRICE_CONFLICT'));
  p.finance.text=p.finance.text.replace('183,600','180,000');assert(parse(p,'time').issues.some(x=>x.code==='FINANCE_PRICE_CONFLICT'));
  assert.equal(get(parse(fixture(),'time'),'principal'),undefined);
});
test('monthly amount alone does not become vehicle price; exact cents preserved',()=>{
  const p=fixture();p.footer='月供 ¥3,060';assert.equal(get(parse(p,'time'),'vehicle_price'),undefined);assert.equal(money('¥123,456.78'),12345678);
});
test('actual Chrome 0.1.0 diagnostic replay fixes /月, Chinese speed, and matched fee basis',()=>{
  const real=JSON.parse(fs.readFileSync(require('node:path').join(__dirname,'../../docs/evidence/capture-spike/raw-0.1.0.json'),'utf8'));
  const result=parse(real.diagnostics,real.captured_at);
  assert.equal(get(result,'vehicle_price'),26350000);assert.equal(get(result,'monthly_payment'),306000);assert.equal(get(result,'top_speed'),201);assert.equal(get(result,'rate_value'),0);assert.equal(get(result,'rate_basis'),'年化费率');
  const changed=structuredClone(real.diagnostics);changed.finance.text=changed.finance.text.replace('年化费率 % 0.00% 折合年化利率 0%','年化费率 % 0.50% 折合年化利率 0.92%');
  const nonzero=parse(changed,'test');assert.equal(get(nonzero,'rate_value'),0.5);assert.equal(get(nonzero,'rate_basis'),'年化费率');
});
test('accessories require explicitly observed unchecked controls; missing section stays missing',()=>{
  const p=fixture();p.accessories={selector:'#RECOMMENDED_ACCESSORIES',options:[{label:'轮胎修理工具包 3.0 ¥779',checked:false}]};
  assert.equal(JSON.stringify(get(parse(p,'test'),'accessories')),'[]');
  p.accessories.options[0].checked=true;assert.equal(get(parse(p,'test'),'accessories').length,1);
  p.accessories.options=[null];assert.equal(get(parse(p,'test'),'accessories'),undefined);
});

// Visible summary may be captured without opening the finance dialog.
test('visible loan summary captures terms while leaving undisclosed product and principal missing',()=>{
 const p=fixture();p.finance_summary='贷款月供 ¥3,477 /月 按首付 ¥79,900, 年化费率 0.00%, 60 期计算';
 const r=parse(p,'summary');
 assert.equal(get(r,'monthly_payment'),347700);assert.equal(get(r,'down_payment'),7990000);
 assert.equal(get(r,'term_months'),60);assert.equal(get(r,'rate_value'),0);
 assert.equal(get(r,'principal'),undefined);assert.equal(get(r,'finance_product'),undefined);
 assert.equal(get(r,'vehicle_price'),26350000);
 p.finance_summary='';p.footer='车辆价格 ¥288,500';
 assert.equal(get(parse(p,'no-loan'),'monthly_payment'),undefined);
});
