/** Runtime test for every dashboard renderer in a minimal DOM shim. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source = fs.readFileSync(new URL('../web/app.js', import.meta.url),'utf8');
const code = source.split('\ninitialize();\n')[0];
assert.notEqual(code, source, 'app bootstrap delimiter not found');
const nodes = new Map();
function node(id){if(!nodes.has(id))nodes.set(id,{
  id, textContent:'', innerHTML:'', hidden:false, style:{},dataset:{},
  classList:{add(){},remove(){},toggle(){}},
  addEventListener(){}, querySelector(){return node('nested')},
  showModal(){this.open=true},close(){this.open=false}
});return nodes.get(id)}
const context={
 document:{querySelector:node,querySelectorAll(){return[]},addEventListener(){}},
 setTimeout(){},clearTimeout(){},setInterval(){},console,Date,Number,String,JSON,Math,
 window:{},navigator:{clipboard:{writeText(){}}},confirm(){return true}
};
vm.createContext(context);
vm.runInContext(code,context,{filename:'app.js'});
const data={
  company:{id:'cmp_001',name:'Northstar Labs',monthly_budget_usd:10,spent_usd:0.4},
  agents:[{id:'a1',name:'CEO',role:'CEO',enabled:1},{id:'a2',name:'Engineering Agent',role:'Engineering',enabled:1}],
  goals:[{id:'g1',title:'Build safe product',description:'Prepare a tested release plan',status:'active',created_at:'2026-11-04T00:00:00Z'}],
  tasks:[{id:'t1',goal_id:'g1',agent_id:'a2',title:'Define API',description:'Design an API',status:'queued',risk:'low',agent_name:'Engineering Agent',estimated_cost_usd:.04,output:null,created_at:'2026-11-04T00:00:00Z'}],
  approvals:[{id:'ap1',goal_id:'g1',status:'approved',summary:'Design a secure product',payload:JSON.stringify({tasks:[{title:'Define API',description:'Deliver a detailed testable API specification',role:'Engineering',risk:'low',estimated_usd:0.04}]})}],
  runs:[],audit:[{id:1,at:'2026-11-04T00:00:00Z',actor:'owner',event:'goal.created',entity_id:'g1',entry_hash:'d'.repeat(64)}],
  model:{ready:true,name:'test-model'}
};
const scripts=['overview','goals','agents','approvals','activity','settings'];
for(const view of scripts){
 const html=vm.runInContext(`state=${JSON.stringify(data)};currentView='${view}';render();document.querySelector('#content').innerHTML`,context);
 assert.ok(html.length>300,`${view} did not render`);
 assert.ok(!html.includes('undefined'),`${view} contains undefined`);
 assert.ok(html.includes('page-heading'),`${view} did not render its heading`);
}
const escaped=vm.runInContext(`escapeHTML('<script>alert(1)</script>')`,context);
assert.equal(escaped,'&lt;script&gt;alert(1)&lt;/script&gt;');
console.log('PASS: 6 dashboard views render with live data and HTML escaping works');
