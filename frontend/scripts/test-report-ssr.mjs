/** HTML-contract checks only: no browser, network, microphone or provider calls. */
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
globalThis.location=new URL('http://127.0.0.1:5199/');
const server=await createServer({server:{middlewareMode:true}});
try{
 const {FinanceModule,EnergyModule,ChargingModule,OptionsModule,StaticAsk}=await server.ssrLoadModule('/src/components/ReportModules.tsx');
 const {reportDemoModules}=await server.ssrLoadModule('/src/mocks/reportFixtures.ts');
 const modules=reportDemoModules('capture-a',32150000,[]);
 const finance=renderToStaticMarkup(React.createElement(FinanceModule,{module:modules[0],options:[]}));
 assert.match(finance,/¥4,025/);assert.match(finance,/Mock/);assert.match(finance,/预算未知/);assert.doesNotMatch(finance,/¥402,500/);
 const energy=renderToStaticMarkup(React.createElement(EnergyModule,{module:modules[1]}));
 assert.match(energy,/¥46,000/);assert.match(energy,/仅能源成本/);assert.match(energy,/Mock 演示假设/);assert.match(energy,/<svg/);assert.match(energy,/20,000 km/);
 const missing=renderToStaticMarkup(React.createElement(ChargingModule,{module:{type:'charging',status:'ready',source_refs:[],data:{state:'no_results',region:'望京',city:'北京',radius_m:5000,stations:[],map_asset_id:null,map_status:'missing',warnings:[],observed_at:'2026-09-20T00:00:00Z'}},owner:'r',preview:false}));
 assert.match(missing,/地图暂不可用/);assert.doesNotMatch(missing,/<img/);assert.doesNotMatch(missing,/uri.amap.com/);
 const partial=renderToStaticMarkup(React.createElement(ChargingModule,{module:{type:'charging',status:'missing',source_refs:[],data:{state:'ready',region:'望京',city:'北京',radius_m:5000,stations:[{number:1,id:'verified-station',name:'已查询到的真实站点',center_distance_m:1800,driving_distance_m:null,driving_duration_seconds:null,distance_basis:'高德中心点距离',route_status:'missing'}],map_asset_id:null,map_status:'missing',warnings:['静态地图获取失败'],observed_at:'2026-09-20T00:00:00Z'}},owner:'r',preview:false}));
 assert.match(partial,/已查询到的真实站点/);assert.match(partial,/1.8/);assert.match(partial,/地图暂不可用/);assert.doesNotMatch(partial,/<img/);

 const disabled=renderToStaticMarkup(React.createElement(StaticAsk,null,'继续问 Tess'));assert.match(disabled,/disabled/);
 const options=renderToStaticMarkup(React.createElement(OptionsModule,{options:[{capture_id:'a',validity:'incomplete',fields:[],issues:[],preference:null,captured_at:'2026-09-20T00:00:00Z'}],modules:[]}));
 assert.match(options,/待获取/);assert.match(options,/当前配置未提供可核实车辆图片/);assert.doesNotMatch(options,/¥0/);
 console.log('PASS report SSR: finance fen, energy assumptions/46000, no fabricated map/zero, disabled business buttons');
}finally{await server.close();}
