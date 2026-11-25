/* SPYDR public sandbox: per-browser localStorage, no shared users, secrets or AI calls. */
(()=>{
'use strict';
const KEY='falvorn-spydr-public-demo-v1';
const roles=['CEO','Engineering','Research','Marketing','Design','Quality','Operations'];
const names={CEO:'CEO',Engineering:'Engineering Agent',Research:'Research Agent',Marketing:'Marketing Agent',Design:'Design Agent',Quality:'Quality Agent',Operations:'Operations Agent'};
const id=p=>p+'_'+(crypto.randomUUID?crypto.randomUUID():Math.random().toString(36).slice(2));
const time=()=>new Date().toISOString();
const err=(status,message)=>Object.assign(new Error(message),{status});
const check=(s,label,min,max)=>{if(typeof s!=='string'||s.trim().length<min||s.trim().length>max)throw err(400,label+' must be '+min+'–'+max+' characters');return s.trim()};
function first(){
 const company_id=id('com'),goal_id=id('gol'),at=time();
 const plan={overview:'Example human review strategy — no AI was used',tasks:[
 {title:'Define product requirements',description:'Write a scoped product requirements brief and identify key constraints.',role:'Engineering',risk:'low',estimated_usd:0},
 {title:'Draft launch positioning',description:'Write product positioning, target audience and launch copy.',role:'Marketing',risk:'low',estimated_usd:0},
 {title:'Prepare QA checklist',description:'List acceptance criteria, edge cases and release checks.',role:'Quality',risk:'low',estimated_usd:0}
 ]};
 return {company:{id:company_id,name:'SPYDR Public Sandbox',monthly_budget_usd:10,spent_usd:0},agents:roles.map(role=>({id:id('agt'),name:names[role],role,enabled:1})),goals:[{id:goal_id,company_id,title:'Sample: Launch a new product',description:'Sample goal used to explore the approval workflow. You can create your own goals.',status:'approval',created_at:at,updated_at:at}],approvals:[{id:id('apr'),company_id,goal_id,type:'strategy',summary:plan.overview,payload:JSON.stringify(plan),status:'pending',decided_at:null,created_at:at}],tasks:[],runs:[],audit:[]};
}
function load(){try{const x=JSON.parse(localStorage.getItem(KEY)||'null');if(x&&x.company&&Array.isArray(x.goals)&&Array.isArray(x.agents))return x;}catch{}const s=first();try{localStorage.setItem(KEY,JSON.stringify(s));}catch{}return s;}
function store(s){try{localStorage.setItem(KEY,JSON.stringify(s));}catch{throw err(507,'Browser storage unavailable or full. Export your work before continuing.');}}
function event(s,name,item){s.audit.unshift({id:id('evt'),at:time(),actor:'Local visitor',event:name,entity_id:item,entry_hash:id('local')});s.audit=s.audit.slice(0,80);}
function change(fn){const s=load(),v=fn(s);store(s);return v;}
const match=(p,r)=>r.exec(p);
function route(p,m,b){
 if(p==='/api/session'&&m==='GET')return {setup_required:false,user:{id:'visitor',email:'Browser-local visitor',csrf:'demo'},model_ready:false};
 if(p==='/api/state'&&m==='GET')return {...load(),model:{ready:false,name:'No live model connected'},features:{manual_plan:true,text_deliverables:true,external_actions:false}};
 if(p==='/api/goals'&&m==='POST')return change(s=>{const title=check(b.title,'Goal title',4,140),description=check(b.description,'Description',10,2500),gid=id('gol'),at=time();s.goals.unshift({id:gid,company_id:s.company.id,title,description,status:'draft',created_at:at,updated_at:at});event(s,'goal.created',gid);return{id:gid}});
 let a;
 if((a=match(p,/^\/api\/goals\/([^/]+)\/manual-plan$/))&&m==='POST')return change(s=>{const g=s.goals.find(x=>x.id===a[1]);if(!g)throw err(404,'Goal not found');if(!['draft','rejected'].includes(g.status))throw err(409,'Goal already submitted');if(!Array.isArray(b.tasks)||b.tasks.length<1||b.tasks.length>3)throw err(400,'Provide 1–3 tasks');const tasks=b.tasks.map(t=>{if(!roles.includes(t.role))throw err(400,'Unrecognized agent');return{title:check(t.title,'Task title',3,100),description:check(t.description,'Instructions',10,1500),role:t.role,risk:'low',estimated_usd:0}});const plan={overview:check(b.overview||'Human-authored delegation strategy','Overview',8,500),tasks},at=time(),aid=id('apr');s.approvals.unshift({id:aid,company_id:s.company.id,goal_id:g.id,type:'strategy',summary:plan.overview,payload:JSON.stringify(plan),status:'pending',decided_at:null,created_at:at});g.status='approval';g.updated_at=at;event(s,'plan.submitted',aid);return{approval_id:aid,plan}});
 if((a=match(p,/^\/api\/approvals\/([^/]+)\/decision$/))&&m==='POST')return change(s=>{const ap=s.approvals.find(x=>x.id===a[1]);if(!ap)throw err(404,'Approval not found');if(ap.status!=='pending')throw err(409,'Already reviewed');if(!['approved','rejected'].includes(b.decision))throw err(400,'Invalid decision');const g=s.goals.find(x=>x.id===ap.goal_id);if(!g||g.status!=='approval')throw err(409,'Goal not pending');const at=time();ap.status=b.decision;ap.decided_at=at;g.status=b.decision==='approved'?'active':'rejected';g.updated_at=at;if(b.decision==='approved')for(const t of JSON.parse(ap.payload).tasks){const agent=s.agents.find(x=>x.role===t.role);s.tasks.unshift({id:id('tsk'),company_id:s.company.id,goal_id:g.id,agent_id:agent.id,agent_name:agent.name,agent_role:agent.role,title:t.title,description:t.description,risk:t.risk,status:'queued',estimated_cost_usd:0,output:null,error:null,created_at:at,updated_at:at})}event(s,'approval.'+b.decision,ap.id);return{ok:true}});
 if((a=match(p,/^\/api\/tasks\/([^/]+)\/complete-manual$/))&&m==='POST')return change(s=>{const t=s.tasks.find(x=>x.id===a[1]);if(!t)throw err(404,'Task not found');if(t.status!=='queued')throw err(409,'Task already completed');t.output=check(b.output,'Deliverable',20,20000);t.status='completed';t.updated_at=time();s.runs.unshift({id:id('run'),task_id:t.id,agent_id:t.agent_id,agent_name:t.agent_name,task_title:t.title,model:'manual',input_tokens:0,output_tokens:0,cost_usd:0,status:'completed',created_at:time()});event(s,'task.manual_completed',t.id);if(s.tasks.filter(x=>x.goal_id===t.goal_id).every(x=>x.status==='completed')){const g=s.goals.find(x=>x.id===t.goal_id);if(g){g.status='completed';g.updated_at=time()}}return{ok:true}});
 if(p==='/api/company'&&m==='PATCH')return change(s=>{const n=Number(b.monthly_budget_usd);if(!Number.isFinite(n)||n<.01||n>100000)throw err(400,'Invalid budget');s.company.monthly_budget_usd=n;event(s,'company.budget_changed',s.company.id);return{ok:true}});
 if(p==='/api/logout'&&m==='POST')return{ok:true};
 throw err(404,'This action requires a secure hosted backend and is not available in the public sandbox');
}
window.SPYDR_PUBLIC_DEMO=true;
window.spydrDemoExport=()=>{const blob=new Blob([JSON.stringify({demo:true,exported_at:time(),data:load()},null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='spydr-demo-workspace.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),2000)};
window.spydrDemoReset=()=>{localStorage.removeItem(KEY);location.reload()};
document.getElementById('demo-export').onclick=window.spydrDemoExport;
document.getElementById('demo-reset').onclick=()=>{if(confirm('Reset browser-local SPYDR workspace?'))window.spydrDemoReset()};
const real=window.fetch.bind(window);
window.fetch=async(input,opts={})=>{
 const address=typeof input==='string'?input:input.url,url=new URL(address,location.href);
 if(url.origin!==location.origin||!url.pathname.startsWith('/api/'))return real(input,opts);
 try{const data=opts.body?JSON.parse(opts.body):{},result=route(url.pathname,(opts.method||'GET').toUpperCase(),data);return new Response(JSON.stringify(result),{status:200,headers:{'Content-Type':'application/json','Cache-Control':'no-store'}})}
 catch(e){return new Response(JSON.stringify({error:e.message||'Operation failed'}),{status:e.status||500,headers:{'Content-Type':'application/json','Cache-Control':'no-store'}})}
};
})();