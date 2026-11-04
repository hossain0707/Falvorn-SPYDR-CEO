const $ = (selector) => document.querySelector(selector);
const escapeHTML = (x = '') => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const amount = value => '$' + Number(value || 0).toLocaleString('en-US',{maximumFractionDigits:4,minimumFractionDigits:2});
const prettyDate = value => value ? new Date(value).toLocaleString(undefined,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}) : '—';
const human = value => String(value || '').replaceAll('_',' ');
const slug = s => (s || 'A').substring(0,1).toUpperCase();
let csrf = null;
let state = null;
let currentView = 'overview';
let isBusy = false;
const roleIcons = {CEO:'◆',Engineering:'⌘',Research:'◈',Marketing:'◉',Design:'◐',Quality:'✓',Operations:'▤'};
const roles = ['CEO','Engineering','Research','Marketing','Design','Quality','Operations'];

async function api(path, options = {}) {
 const init = {credentials:'same-origin',headers:{'Accept':'application/json', ...(options.body ? {'Content-Type':'application/json'}:{}), ...(options.method && options.method !== 'GET' && csrf ? {'X-CSRF-Token':csrf}: {})}, ...options};
 let response;
 try { response = await fetch(path, init); } catch { throw new Error('Cannot connect to the server. Check whether it is running.'); }
 const body = await response.json().catch(() => ({}));
 if(!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
 return body;
}
function toast(message, error=false) {
 const el = $('#toast'); el.textContent = message; el.className = 'toast' + (error ? ' error':''); el.hidden = false;
 clearTimeout(toast.timer);toast.timer = setTimeout(() => {el.hidden=true;},4600);
}
async function task(action) {if(isBusy)return;isBusy=true; try {await action();} catch(error){toast(error.message,true);}finally{isBusy=false;}}

function authScreen(setup) {
 $('#auth').hidden=false;$('#shell').style.filter='blur(6px)';
 $('#auth-eyebrow').textContent=setup?'SECURE WORKSPACE SETUP':'WELCOME BACK';
 $('#auth-title').textContent=setup?'Run a company of AI agents.':'Your command center awaits.';
 $('#auth-subtitle').textContent=setup?'Create your private workspace. Agent execution will require a model key configured on the server.':'Sign in to review your agents, goals, and approvals.';
 $('#company-field').hidden=!setup;$('#company-field input').required=setup;
 $('#auth-submit').textContent=setup?'Create workspace':'Sign in';
 $('#auth-form').dataset.mode=setup?'setup':'login';
 $('#auth-form input[name=password]').autocomplete=setup?'new-password':'current-password';
}
function hideAuth(){ $('#auth').hidden=true;$('#shell').style.filter=''; }
async function initialize() {
 try {
  const session=await api('/api/session');
  csrf=session.user?.csrf||null;
  if(!session.user) {authScreen(session.setup_required);return;}
  $('#owner-email').textContent=session.user.email;
  hideAuth();await refresh();
 } catch(e) {$('#content').innerHTML=`<div class="empty"><strong>Server unavailable</strong><p>${escapeHTML(e.message)}</p></div>`;}
}
async function refresh(){state=await api('/api/state');render();}
function countTasks(status){return state.tasks.filter(x=>x.status===status).length;}
function countGoals(status){return state.goals.filter(x=>x.status===status).length;}
function header(kicker,title,description,extra=''){
 return `<div class="page-heading"><div><div class="eyebrow">${escapeHTML(kicker)}</div><h1>${escapeHTML(title)}</h1><p>${escapeHTML(description)}</p></div>${extra}</div>`;
}
function status(name){return `<span class="chip ${escapeHTML(name)}">${escapeHTML(human(name))}</span>`;}
function blank(icon,title,description,cta,action){return `<div class="empty"><div class="empty-icon">${icon}</div><strong>${escapeHTML(title)}</strong><p>${escapeHTML(description)}</p>${cta?`<button class="secondary" data-action="${escapeHTML(action)}">${escapeHTML(cta)}</button>`:''}</div>`;}
function render(){
 if(!state)return;
 $('#workspace-name').textContent=state.company.name;
 $('#workspace-monogram').textContent=slug(state.company.name);
 const pending=state.approvals.filter(a=>a.status==='pending').length;
 $('#approval-count').hidden=!pending;$('#approval-count').textContent=pending;
 for(const b of document.querySelectorAll('[data-view]'))b.classList.toggle('active',b.dataset.view===currentView);
 $('#view-label').textContent=({overview:'Overview',goals:'Goals & tasks',agents:'Agent workforce',approvals:'Approvals',activity:'Activity log',settings:'Settings & budget'})[currentView];
 $('#content').innerHTML=({overview:renderOverview,goals:renderGoals,agents:renderAgents,approvals:renderApprovals,activity:renderActivity,settings:renderSettings})[currentView]();
 for(const element of document.querySelectorAll('[data-progress]')) {
   element.style.width=`${Math.min(100,Math.max(0,Number(element.dataset.progress)||0))}%`;
 }
 for(const element of document.querySelectorAll('[data-percent]')) {
   element.style.setProperty('--percent',`${Math.min(100,Math.max(0,Number(element.dataset.percent)||0))}%`);
 }
}
function renderOverview(){
 const total=state.tasks.length, completed=countTasks('completed'), active=countTasks('running'), pending=state.approvals.filter(a=>a.status==='pending').length;
 const remaining=Math.max(0,state.company.monthly_budget_usd-state.company.spent_usd);
 const budgetPercent=Math.min(100,Math.max(0,100*state.company.spent_usd/state.company.monthly_budget_usd));
 return `${header('MISSION CONTROL',`Good to see you.`,`Here’s what’s happening across your AI workforce.`,`<span class="heading-meta">${escapeHTML(new Date().toLocaleDateString(undefined,{weekday:'short',month:'long',day:'numeric',year:'numeric'}))}</span>`)}
 <div class="kpi-grid"><div class="kpi highlight"><div class="kpi-title"><i></i> Active goals</div><strong>${countGoals('active')}</strong><div class="kpi-note">${state.goals.length} goals created</div></div>
 <div class="kpi violet"><div class="kpi-title"><i></i> AI tasks completed</div><strong>${completed}</strong><div class="kpi-note">${total} tasks assigned</div></div>
 <div class="kpi gold"><div class="kpi-title"><i></i> Pending approvals</div><strong>${pending}</strong><div class="kpi-note">Human review required</div></div>
 <div class="kpi"><div class="kpi-title"><i></i> Monthly remaining</div><strong>${amount(remaining)}</strong><div class="kpi-note">of ${amount(state.company.monthly_budget_usd)} budget</div></div></div>
 <div class="content-grid"><div><section class="panel"><div class="panel-head"><div><h2>Company missions</h2><p>Your strategic goals and their progress</p></div><button class="ghost" data-view="goals">View all →</button></div><div class="panel-inner">
 ${state.goals.length?state.goals.slice(0,5).map(g=>{const group=state.tasks.filter(t=>t.goal_id===g.id);const done=group.filter(t=>t.status==='completed').length;return `<div class="goal-item"><div class="item-icon">◎</div><div class="item-content"><span class="item-title">${escapeHTML(g.title)}</span><div class="item-sub">${group.length?`${done} / ${group.length} deliverables complete`:'Awaiting plan'}</div>${group.length?`<div class="mini-progress"><b data-progress="${Math.round(100*done/group.length)}"></b></div>`:''}</div><div class="item-right">${status(g.status)}${g.status==='draft'||g.status==='rejected'?`<div><button class="ghost" data-action="plan" data-id="${g.id}">Build plan →</button></div>`:''}</div></div>`}).join(''):blank('◎','Your company is ready','Give your CEO agent a business objective to start planning.','Create your first goal','new-goal')}
 </div></section><section class="panel section-space"><div class="panel-head"><div><h2>Latest agent output</h2><p>Deliverables generated by your AI workforce</p></div><button class="ghost" data-view="goals">All tasks →</button></div><div class="panel-inner">
 ${state.tasks.filter(t=>t.output).length?state.tasks.filter(t=>t.output).slice(0,4).map(t=>`<div class="task-item"><div class="item-icon">✧</div><div class="item-content"><span class="item-title">${escapeHTML(t.title)}</span><div class="item-sub">${escapeHTML(t.agent_name||'Agent')} · ${prettyDate(t.updated_at)}</div></div><button class="secondary" data-action="artifact" data-id="${t.id}">Open</button></div>`).join(''):blank('✧','No deliverables yet','Approved tasks appear here after execution with a configured AI model.')}
 </div></section></div>
 <div class="right-column"><section class="panel"><div class="panel-head"><div><h2>Model connection</h2><p>Real inference, never simulated</p></div>${status(state.model.ready?'completed':'pending')}</div><div class="panel-inner"><div class="model-row"><div><strong>${escapeHTML(state.model.name)}</strong><small>${state.model.ready?'Provider key configured':'Server-side API key required'}</small></div><span class="status-dot ${state.model.ready?'':'off'}"></span></div><div class="divider"></div><div class="model-row"><div><strong>${state.agents.length} specialist agents</strong><small>Assigned by role to your company</small></div><span class="text-muted">⌁</span></div><div class="agent-dots">${state.agents.map(a=>`<span class="agent-dot" title="${escapeHTML(a.role)}">${escapeHTML(roleIcons[a.role]||'✦')}</span>`).join('')}</div>${!state.model.ready?`<p class="status-copy">Set <code>AI_API_KEY</code> in the server environment to enable planning and execution. Manual plans work without a key.</p>`:''}</div></section>
 <section class="panel"><div class="panel-head"><div><h2>Budget monitor</h2><p>Live recorded model consumption</p></div></div><div class="panel-inner"><div class="budget-wrap"><div class="ring" data-percent="${budgetPercent}"><strong>${Math.round(budgetPercent)}%</strong></div><div class="budget-copy"><strong>${amount(state.company.spent_usd)}</strong><p>Spent this month</p><span class="text-muted">${amount(remaining)} available</span></div></div><div class="divider"></div><div class="model-row"><span class="text-muted">Task executions</span><strong>${state.runs.filter(r=>r.task_id&&r.status==='completed').length}</strong></div><div class="model-row"><span class="text-muted">Currently running</span><strong>${active}</strong></div><div class="action-line space-top-14"><button class="ghost" data-view="settings">Manage spending limits →</button></div></div></section>
 <section class="panel"><div class="panel-head"><div><h2>Governance first</h2><p>Nothing executes without oversight</p></div></div><div class="panel-inner"><div class="tips">Plan approval is mandatory. Each AI call is explicitly started by the owner. Generated text is never automatically published or deployed.</div><div class="action-line space-top-12"><button class="ghost" data-view="approvals">Review approvals →</button></div></div></section></div></div>`;
}
function renderGoals(){
 return `${header('WORK MANAGEMENT','Goals & tasks','Define outcomes, approve a strategy, and execute agent deliverables.',`<button class="primary" data-action="new-goal">＋ Create goal</button>`)}
 <section class="panel"><div class="panel-head"><div><h2>Strategic goals</h2><p>${state.goals.length} goals in this workspace</p></div></div><div class="panel-inner">${state.goals.length?state.goals.map(g=>`<div class="goal-item"><div class="item-icon">◎</div><div class="item-content"><span class="item-title">${escapeHTML(g.title)}</span><div class="item-sub">${escapeHTML(g.description.length>190?g.description.slice(0,190)+'…':g.description)}</div></div><div class="item-right">${status(g.status)}${['draft','rejected'].includes(g.status)?`<div><button class="ghost" data-action="plan" data-id="${g.id}">Create plan →</button></div>`:''}</div></div>`).join(''):blank('◎','No goals created','Begin with a clear objective. The CEO can generate a plan once a model is connected.','Create a goal','new-goal')}</div></section>
 <section class="panel section-space"><div class="panel-head"><div><h2>Execution queue</h2><p>Review, run, and inspect each assigned task</p></div></div>
 ${state.tasks.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>Task</th><th>Assigned agent</th><th>Risk</th><th>Status</th><th>Estimated</th><th>Action</th></tr></thead><tbody>${state.tasks.map(t=>`<tr><td>${escapeHTML(t.title)}<span class="subline">${escapeHTML(state.goals.find(g=>g.id===t.goal_id)?.title||'')}</span></td><td>${escapeHTML(t.agent_name||'Unassigned')}</td><td>${status(t.risk)}</td><td>${status(t.status)}</td><td>${amount(t.estimated_cost_usd)}</td><td>${['queued','error'].includes(t.status)?`<button class="secondary" data-action="run" data-id="${t.id}">Run agent</button>`:t.status==='completed'?`<button class="secondary" data-action="artifact" data-id="${t.id}">View output</button>`:t.status==='running'?'<span class="text-muted">Working…</span>':'—'}${t.error?`<span class="subline">${escapeHTML(t.error)}</span>`:''}</td></tr>`).join('')}</tbody></table></div>`:blank('▤','No tasks in the queue','Approve a goal plan first. Delegated tasks will appear here.')}
 </section><p class="foot-note">Agents produce reviewable text deliverables. They do not run shell commands, commit code, send messages, or access external systems.</p>`;
}
function renderAgents(){const tasks=state.tasks;return `${header('YOUR WORKFORCE','Meet the agents','Specialist AI roles with clear boundaries, accountability, and approval-first execution.',`<span class="heading-meta">${state.agents.length} configured roles</span>`)}
 <div class="agent-grid">${state.agents.map(a=>{const owned=tasks.filter(t=>t.agent_id===a.id);const done=owned.filter(t=>t.status==='completed').length;return `<article class="agent-card"><div class="agent-symbol">${escapeHTML(roleIcons[a.role]||'✧')}</div><h3>${escapeHTML(a.name)}</h3><p>${escapeHTML(a.role)} · ${a.role==='CEO'?'Strategy & delegation':a.role==='Engineering'?'Technical delivery':a.role==='Research'?'Evidence & investigation':a.role==='Marketing'?'Growth & positioning':a.role==='Design'?'Experience & interfaces':a.role==='Quality'?'Validation & quality':'Processes & operations'}</p><div class="agent-footer"><span>${owned.length} assigned · ${done} completed</span><span class="chip completed">Available</span></div></article>`;}).join('')}</div>
 <div class="panel section-space"><div class="panel-head"><div><h2>How the workforce operates</h2><p>Designed to keep the owner accountable for consequential decisions</p></div></div><div class="panel-inner"><div class="tips">Your CEO proposes a strategy. You approve the plan. Specialist agents generate task deliverables only when you click Run. Every model request, decision, and result is recorded for review.</div></div></div>`;}
function renderApprovals(){const pending=state.approvals.filter(a=>a.status==='pending'),decided=state.approvals.filter(a=>a.status!=='pending');return `${header('GOVERNANCE DESK','Approval center','No agent strategy can proceed until you review and authorize its scope.',`<span class="heading-meta">${pending.length} awaiting decision</span>`)}
 ${pending.length?pending.map(a=>approvalCard(a,true)).join(''): `<section class="panel">${blank('☑','You are all caught up','Any new strategy proposal will appear here for your approval.')}</section>`}
 ${decided.length?`<section class="panel section-space"><div class="panel-head"><div><h2>Decision history</h2><p>Past approvals and rejections</p></div></div><div class="panel-inner">${decided.map(a=>`<div class="goal-item"><div class="item-content"><strong class="item-title">${escapeHTML(state.goals.find(g=>g.id===a.goal_id)?.title||'Strategy')}</strong><div class="item-sub">${prettyDate(a.decided_at)}</div></div>${status(a.status)}<button class="ghost" data-action="inspect-plan" data-id="${a.id}">Details →</button></div>`).join('')}</div></section>`:''}`;
}
function approvalCard(a, buttons){let plan;try{plan=JSON.parse(a.payload);}catch{plan={tasks:[]}}return `<article class="approve-card"><div class="approve-meta">CEO strategy proposal · ${prettyDate(a.created_at)}</div><h3>${escapeHTML(state.goals.find(g=>g.id===a.goal_id)?.title||'Goal strategy')}</h3><p>${escapeHTML(a.summary)}</p><div class="divider"></div><div class="eyebrow">PROPOSED DELEGATION</div>${plan.tasks.map((t,i)=>`<div class="plan-task"><strong>${i+1}. ${escapeHTML(t.title)}</strong><p>${escapeHTML(t.description)}</p><small>${escapeHTML(t.role)} · ${escapeHTML(t.risk)} risk · ${amount(t.estimated_usd)} estimate</small></div>`).join('')}${buttons?`<div class="actions-bottom"><button class="danger-btn" data-action="decision" data-id="${a.id}" data-choice="rejected">Reject plan</button><button class="primary" data-action="decision" data-id="${a.id}" data-choice="approved">Approve strategy</button></div>`:`<div class="actions-bottom">${status(a.status)}</div>`}</article>`;}
function renderActivity(){return `${header('FULL TRANSPARENCY','Activity & audit log','Actions, approvals, and work events recorded with a chained SHA-256 digest.',`<button class="secondary" data-action="verify">Verify audit chain</button>`)}
 <section class="panel"><div class="panel-head"><div><h2>Workspace events</h2><p>Most recent recorded operations</p></div><span class="chip">Append-only records</span></div><div class="panel-inner">${state.audit.length?state.audit.map(a=>`<div class="activity-item"><div class="timeline-mark">○</div><div class="item-content"><div class="item-title">${escapeHTML(human(a.event))}</div><div class="item-sub">${escapeHTML(a.entity_id)} · ${escapeHTML(a.entry_hash.slice(0,16))}…</div></div><div class="item-right text-muted nowrap">${prettyDate(a.at)}</div></div>`).join(''):blank('≋','No activity recorded','Your actions will appear here.')}</div></section><p class="foot-note">The hash chain detects accidental or unauthorized modification of individual records, but is not a substitute for external anchoring or immutable storage.</p>`;}
function renderSettings(){const c=state.company;return `${header('WORKSPACE CONFIGURATION','Settings & budget','Set cost limits and review the runtime connection for your agents.')}
 <div class="content-grid"><section class="panel"><div class="panel-head"><div><h2>Monthly spend limit</h2><p>Stops task execution when estimated cost exceeds the cap</p></div></div><div class="panel-inner"><div class="budget-wrap"><div class="ring" data-percent="${Math.min(100,100*c.spent_usd/c.monthly_budget_usd)}"><strong>${Math.round(100*c.spent_usd/c.monthly_budget_usd)}%</strong></div><div class="budget-copy"><strong>${amount(c.spent_usd)} used</strong><p>of ${amount(c.monthly_budget_usd)} monthly</p></div></div><div class="divider"></div><form id="budget-form" class="budget-setting"><label>New monthly spending limit (USD)<input name="budget" type="number" step="0.01" min="0.01" max="100000" required value="${Number(c.monthly_budget_usd)}"/></label><p class="modal-hint">Costs are estimated using server-configured model rates; provider invoices may differ. The cap checks before tasks, not during a provider request.</p><button class="secondary" type="submit">Save spending limit</button></form></div></section>
 <aside class="right-column"><section class="panel"><div class="panel-head"><div><h2>Model provider</h2><p>Server-side configuration</p></div></div><div class="panel-inner"><div class="model-row"><div><strong>${escapeHTML(state.model.name)}</strong><small>${state.model.ready?'API key available to server':'API key missing'}</small></div>${status(state.model.ready?'completed':'pending')}</div><div class="divider"></div><p class="modal-hint">Configure <code>AI_API_KEY</code>, <code>AI_MODEL</code>, and optionally <code>AI_BASE_URL</code> in server environment. Credentials are not available in the browser or database.</p></div></section><section class="panel"><div class="panel-head"><div><h2>Execution boundaries</h2><p>Explicit permission before model calls</p></div></div><div class="panel-inner"><p class="inline-msg">Code execution: off<br/>External API actions: off<br/>Automatic publishing: off<br/>Mandatory plan approval: on<br/>Human-initiated tasks: on</p></div></section></aside></div>`;}
function showModal(kicker,title,body){$('#modal-kicker').textContent=kicker;$('#modal-title').textContent=title;$('#modal-body').innerHTML=body;$('#modal').showModal();}
function closeModal(){$('#modal').close();}
function goalDialog(){showModal('NEW MISSION','Create a business goal',`<p class="modal-intro">Be specific about the outcome, audience, constraints, and acceptance criteria. Your CEO will turn this objective into reviewable tasks.</p><form id="goal-form"><label>Goal title<input name="title" required minlength="4" maxlength="140" placeholder="Launch a customer-ready product concept"/></label><label>Objectives and constraints<textarea name="description" required minlength="10" maxlength="2500" rows="6" placeholder="Describe the deliverables, target audience, technical or budget constraints, and success criteria."></textarea></label><div class="modal-foot"><button class="secondary" type="button" data-action="close">Cancel</button><button class="primary" type="submit">Create goal</button></div></form>`);}
function manualPlanDialog(id){const options=roles.map(r=>`<option value="${r}">${r}</option>`).join('');showModal('MANUAL PLANNING','Compose a strategy',`<p class="modal-intro">Add 1–3 actionable text deliverables. The strategy will still require approval. This works without a model key.</p><form id="manual-form" data-id="${id}">${[1,2,3].map(n=>`<div class="plan-task"><label>Task ${n} · specialist role<select name="role_${n}">${options}</select></label><label class="space-top-8">Task title<input name="title_${n}" ${n===1?'required':''} maxlength="100" placeholder="Task ${n} deliverable title"/></label><label class="space-top-8">Task instructions<textarea name="desc_${n}" maxlength="1500" rows="2" placeholder="What should this specialist deliver?"></textarea></label></div>`).join('')}<div class="modal-foot"><button type="button" class="secondary" data-action="close">Cancel</button><button type="submit" class="primary">Submit for approval</button></div></form>`);}
function planDialog(id){const g=state.goals.find(x=>x.id===id);if(!g)return;showModal('CEO STRATEGY','Plan this mission',`<p class="modal-intro"><strong>${escapeHTML(g.title)}</strong></p><p class="modal-intro">${escapeHTML(g.description)}</p><div class="tips">AI planning makes a real inference call and consumes provider tokens. You can alternatively create a manual strategy without a model key.</div><div class="actions-bottom"><button class="secondary" data-action="manual-plan" data-id="${id}">Plan manually</button><button class="primary" data-action="ai-plan" data-id="${id}" ${state.model.ready?'':'disabled'}>✦ Generate CEO plan</button></div>${state.model.ready?'':'<p class="modal-hint">Configure AI_API_KEY to use automatic planning.</p>'}`);}
function artifactDialog(id){const t=state.tasks.find(x=>x.id===id);if(!t)return;showModal(`${t.agent_name||'AGENT'} DELIVERABLE`,t.title,`<div class="action-line space-bottom-13">${status(t.status)}<span class="text-muted">Updated ${prettyDate(t.updated_at)}</span><button class="secondary" id="copy-output">Copy text</button></div><pre class="artifact-output">${escapeHTML(t.output||'No output recorded')}</pre><p class="foot-note">AI-generated content should be verified before being used in production or published externally.</p>`);$('#copy-output').onclick=async()=>{try{await navigator.clipboard.writeText(t.output||'');toast('Output copied');}catch{toast('Clipboard access unavailable',true);}};}
function showPlanDialog(id){const a=state.approvals.find(x=>x.id===id);if(a)showModal('STRATEGY RECORD','Plan details',approvalCard(a,false));}
function runConfirm(id){const t=state.tasks.find(x=>x.id===id);if(!t)return;if(!state.model.ready){toast('Configure AI_API_KEY on the server to run an agent',true);return;}showModal('RUN AI AGENT','Execute this task',`<p class="modal-intro">This action calls your configured model provider and creates a persistent deliverable. No external files, websites, or systems will be changed.</p><div class="plan-task"><strong>${escapeHTML(t.title)}</strong><p>${escapeHTML(t.description)}</p><small>${escapeHTML(t.agent_name)} · estimated ${amount(t.estimated_cost_usd)}</small></div><div class="actions-bottom"><button class="secondary" data-action="close">Cancel</button><button class="primary" data-action="execute" data-id="${id}">Start execution</button></div>`);}
async function onClick(event){
 const viewEl=event.target.closest('[data-view]');if(viewEl){currentView=viewEl.dataset.view;render();return;}
 const el=event.target.closest('[data-action]');if(!el)return;const act=el.dataset.action,id=el.dataset.id;
 if(act==='new-goal')return goalDialog();
 if(act==='close')return closeModal();
 if(act==='plan')return planDialog(id);
 if(act==='manual-plan')return manualPlanDialog(id);
 if(act==='artifact')return artifactDialog(id);
 if(act==='inspect-plan')return showPlanDialog(id);
 if(act==='run')return runConfirm(id);
 if(act==='ai-plan')return task(async()=>{el.disabled=true;el.textContent='Planning with CEO…';try{await api(`/api/goals/${id}/plan`,{method:'POST',body:'{}'});closeModal();currentView='approvals';await refresh();toast('CEO strategy is ready for your approval');}catch(e){el.disabled=false;el.textContent='✦ Generate CEO plan';throw e;}});
 if(act==='decision')return task(async()=>{if(el.dataset.choice==='rejected'&&!confirm('Reject this strategy? You can create a new plan afterward.'))return;await api(`/api/approvals/${id}/decision`,{method:'POST',body:JSON.stringify({decision:el.dataset.choice})});await refresh();toast(el.dataset.choice==='approved'?'Strategy approved. Tasks added to queue.':'Strategy rejected.');});
 if(act==='execute')return task(async()=>{el.disabled=true;el.textContent='Agent working…';try{await api(`/api/tasks/${id}/run`,{method:'POST',body:'{}'});closeModal();await refresh();toast('Agent finished the deliverable');artifactDialog(id);}catch(e){await refresh();throw e;}});
 if(act==='verify')return task(async()=>{const result=await api('/api/audit/verify');toast(result.valid?`Audit chain verified: ${result.entries_checked} records`:'Audit chain integrity check failed',!result.valid);});
}
async function onSubmit(event){
 if(event.target.id==='auth-form'){
  event.preventDefault();const f=event.target;const data=Object.fromEntries(new FormData(f));$('#auth-error').hidden=true;
  try{const r=await api(`/api/${f.dataset.mode}`,{method:'POST',body:JSON.stringify(data)});csrf=r.csrf;await initialize();toast('Workspace unlocked');}catch(e){$('#auth-error').textContent=e.message;$('#auth-error').hidden=false;}return;
 }
 if(event.target.id==='goal-form'){
  event.preventDefault();const form=event.target;const data=Object.fromEntries(new FormData(form));await task(async()=>{await api('/api/goals',{method:'POST',body:JSON.stringify(data)});closeModal();currentView='goals';await refresh();toast('Goal created. You can now generate its plan.');});return;
 }
 if(event.target.id==='manual-form'){
  event.preventDefault();const form=event.target;const f=new FormData(form);const items=[];
  for(let n=1;n<=3;n++){const title=String(f.get(`title_${n}`)||'').trim(),desc=String(f.get(`desc_${n}`)||'').trim();if(!title&&!desc)continue;if(!title||desc.length<10){toast(`Task ${n} needs a title and at least 10 characters of instructions`,true);return;}items.push({title,description:desc,role:f.get(`role_${n}`),risk:'low',estimated_usd:0.02});}
  if(!items.length){toast('Add at least one task',true);return;}
  await task(async()=>{await api(`/api/goals/${form.dataset.id}/manual-plan`,{method:'POST',body:JSON.stringify({overview:'Human-authored strategy consisting of '+items.length+' scoped specialist deliverable(s).',tasks:items})});closeModal();currentView='approvals';await refresh();toast('Manual strategy submitted for approval.');});return;
 }
 if(event.target.id==='budget-form'){
  event.preventDefault();const budget=Number(new FormData(event.target).get('budget'));
  await task(async()=>{await api('/api/company',{method:'PATCH',body:JSON.stringify({monthly_budget_usd:budget})});await refresh();toast('Monthly spending limit updated');});return;
 }
}
$('#auth-form').addEventListener('submit',onSubmit);
$('#content').addEventListener('submit',onSubmit);
$('#modal-body').addEventListener('submit',onSubmit);
document.addEventListener('click',onClick);
$('#modal-close').onclick=closeModal;
$('#new-goal-top').onclick=goalDialog;
$('#refresh').onclick=()=>task(async()=>{await refresh();toast('Dashboard updated');});
$('#logout').onclick=()=>task(async()=>{await api('/api/logout',{method:'POST',body:'{}'});csrf=null;state=null;await initialize();});
initialize();
setInterval(async()=>{if(!state||isBusy||$('#modal').open)return;try{await refresh();}catch{}},20000);
