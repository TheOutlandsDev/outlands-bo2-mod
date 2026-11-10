/* Offline DOM/data tests. Actual layout and native BO2 input need real renderers. */
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ROOT=path.resolve(__dirname,'..');
const model=require('../accounts/web/career.js').OutlandsCareer;
const challenge=(progress=12)=>({challenge:'outlands_dusk_an94_headshots',weapon:'an94_mp',camo:'outlands_dusk',scope:'outlands_account',revision:1,target:25,progress,completed:progress===25,reward_ready:false});
const account=(progress=12)=>({id:'synthetic_account_001',display_name:'SyntheticPlayer',revision:1,profiles:[{server:'synthetic_server_001',live:true,observed_at:12345,stats:{rank_xp:123}}],custom_challenges:[challenge(progress)]});
function element(tag='div'){
  return {tag,hidden:false,textContent:'',value:'',className:'',disabled:false,children:[],handlers:{},
    append(...values){this.children.push(...values);},replaceChildren(...values){this.children=values;},
    addEventListener(name,handler){this.handlers[name]=handler;},querySelectorAll(){return [];}};
}
function harness(initial){
  const elements=new Map();const calls=[];
  const get=id=>{if(!elements.has(id))elements.set(id,element());return elements.get(id);};
  get('member').hidden=true;get('guest').hidden=true;
  const document={hidden:false,activeElement:null,handlers:{},getElementById:get,createElement:element,
    querySelectorAll(){return [];},addEventListener(name,handler){this.handlers[name]=handler;}};
  let responder=async()=>({status:200,value:initial});
  const context=vm.createContext({document,OutlandsCareer:model,AbortController,AbortSignal:{timeout:()=>undefined},Date,
    setTimeout:()=>1,clearTimeout:()=>{},setInterval:()=>1,
    fetch:async(url,options)=>{calls.push({url,options});const result=await responder(url,options);return {ok:result.status===200,status:result.status,json:async()=>result.value};}});
  vm.runInContext(fs.readFileSync(path.join(ROOT,'accounts/web/account.js'),'utf8'),context);
  return {get,context,document,calls,respond:value=>{responder=value;}};
}
const flush=async()=>{for(let i=0;i<20;i++)await Promise.resolve();};
async function run(){
  let checks=0;
  for(const progress of [0,12,25]){
    const value=model.view(account(progress));assert.equal(value.progress,progress);assert.equal(value.available,true);
    assert.equal(value.completed,progress===25);assert.equal(value.equip,false);checks++;
  }
  for(const row of [null,challenge(-1),challenge(26),{...challenge(),progress:NaN},{...challenge(),target:0},{...challenge(),completed:true},{...challenge(),scope:'local'},{...challenge(),weapon:'other_mp'}]){
    const value=model.view({...account(),custom_challenges:[row]});assert.equal(value.available,false);assert.equal(value.progress,null);assert.equal(value.equip,false);checks++;
  }
  assert.equal(model.view({...account(25),custom_challenges:[{...challenge(25),reward_ready:true}]}).equip,false);checks++;
  assert.equal(model.view({profiles:[]}).pairing,'unlinked');assert.equal(model.view({profiles:[{live:false}]}).pairing,'confirm_again');assert.equal(model.view(account()).pairing,'confirmed');checks++;
  const ui=harness(account());await flush();
  assert.equal(ui.get('challenge-count').textContent,'12');assert.equal(ui.get('member').hidden,false);
  assert.equal(ui.get('equip-camo').disabled,true);assert.equal(ui.get('challenge-progress').hidden,false);checks++;
  ui.respond(async()=>({status:503,value:{error:'Unavailable'}}));await ui.context.refresh();
  assert.equal(ui.get('challenge-count').textContent,'—');assert.equal(ui.get('challenge-progress').hidden,true);assert.equal(ui.get('challenge-state').textContent,'PROGRESS UNAVAILABLE');checks++;
  ui.respond(async()=>({status:200,value:account(25)}));await ui.context.refresh();
  assert.equal(ui.get('challenge-state').textContent,'CHALLENGE COMPLETE');assert.equal(ui.get('equip-camo').disabled,true);checks++;
  ui.get('pair-code').value='SYNTHETIC-CODE';ui.respond(async()=>({status:401,value:{error:'Sign-in required'}}));await ui.context.refresh();
  assert.equal(ui.get('member').hidden,true);assert.equal(ui.get('profiles').children.length,0);assert.equal(ui.get('display-name').value,'');assert.equal(ui.get('pair-code').value,'');assert.equal(ui.get('challenge-count').textContent,'—');checks++;
  ui.respond(async()=>({status:200,value:account(3)}));await ui.context.refresh();assert.equal(ui.get('challenge-count').textContent,'3');checks++;
  ui.document.activeElement=ui.get('display-name');ui.get('display-name').value='Previous account edit';ui.get('pair-code').value='OLD-PRIVATE-CODE';
  ui.respond(async()=>({status:200,value:{...account(2),id:'synthetic_account_002',display_name:'PlayerTwo'}}));await ui.context.refresh();
  assert.equal(ui.get('display-name').value,'PlayerTwo');assert.equal(ui.get('pair-code').value,'');assert.equal(ui.get('challenge-count').textContent,'2');checks++;
  let resolveOld;ui.respond(url=>url==='/api/me'?new Promise(resolve=>{resolveOld=resolve;}):Promise.resolve({status:200,value:{signed_out:true}}));
  const oldRefresh=ui.context.refresh();await flush();await ui.get('logout').handlers.click();
  resolveOld({status:200,value:account(19)});await oldRefresh;
  assert.equal(ui.get('member').hidden,true);assert.equal(ui.get('challenge-count').textContent,'—');assert.equal(ui.get('profiles').children.length,0);checks++;
  assert.equal(ui.calls.some(call=>call.url.includes('challenges')),false);checks++;
  return {passed:true,checks,scope:'offline_data_and_dom',real_browser_layout:false,native_bo2_menu:false};
}
module.exports={run};
if(require.main===module)run().then(value=>console.log(JSON.stringify(value))).catch(error=>{console.error(error);process.exitCode=1;});
