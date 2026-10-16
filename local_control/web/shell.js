import {request, connection, start} from './connection.js';
import {installProjects} from './projects.js';
import {installForms} from './forms.js';

window.uiRequest = request;
if (!window.centerUI || !window.trackOperation || !window.claudeReview || !viewRegistry.has('audit') || !viewRegistry.has('workflows')) {
  throw new Error('A required dashboard component did not load. Reload the page before continuing.');
}
const sections = {
  home: {label:'Home', pages:[['home','Your workspace'],['onboarding','Get started']]},
  projects: {label:'Projects', pages:[['project-list','All projects'],['architectures','Templates'],['workflows','Toolkits & preparation']]},
  instructions: {label:'Instructions', pages:[['constitution','Shared library'],['drafts','Saved drafts'],['audit','Health & findings']]},
  compute: {label:'Models & machines', pages:[['machines','Machines'],['models','Models'],['worker-setup','Add a worker'],['workers','Worker packages'],['overview','GPU & sessions'],['setup','Local model setup'],['connect','Local client integrations'],['insights','Measurements']]},
  activity: {label:'Activity', pages:[['activity-page','Operations'],['projects','Synchronization']]},
  settings: {label:'Settings', pages:[['accounts','Apps & accounts'],['storage','Storage'],['vault','Backups'],['updates','Updates'],['settings-page','Startup & help']]}
};
const labels = Object.fromEntries(Object.values(sections).flatMap(v=>v.pages));
const e = escapeHTML;
let navigating = false, currentAddress=location.pathname+location.search;
const legacyPage = page;
window.navigateWorkspace = async (name, {replace=false, project=null}={}) => {
  if (navigating) return;
  if (!labels[name] && name !== 'project-detail') name='home';
  if (document.querySelector('.page.active')?.id !== name && window.studioUnsaved?.()) {
    const decision = await dirtyChoice();
    if (decision === 'stay') {if(replace)history.pushState({},'',currentAddress);return;}
    if (decision === 'save') { try { await window.saveStudioDraft(); } catch(error) { notice(error.message,true); return; } }
    else window.discardStudioEdits?.();
  }
  navigating = true;
  try {
    const section = name === 'project-detail' ? 'projects' : Object.keys(sections).find(k=>sections[k].pages.some(p=>p[0]===name)) || 'projects';
    document.querySelectorAll('[data-section]').forEach(b=>{b.classList.toggle('active',b.dataset.section===section);b.setAttribute('aria-current',b.dataset.section===section?'page':'false');});
    $('section-tabs').innerHTML = sections[section].pages.map(([id,label])=>`<button class="nav ${id===name?'active':''}" data-page="${id}">${e(label)}</button>`).join('');
    $('section-tabs').querySelectorAll('button').forEach(b=>b.onclick=()=>window.navigateWorkspace(b.dataset.page));
    document.body.classList.remove('menu-open'); $('menu-toggle').setAttribute('aria-expanded','false');
    const url = new URL(location.href); url.searchParams.set('view',name);
    if(project) url.searchParams.set('project',project); else url.searchParams.delete('project');
    history[replace?'replaceState':'pushState']({},'',url.pathname+url.search);currentAddress=url.pathname+url.search;
    legacyPage(name);
    const help=$('context-help');if(help)help.href='https://github.com/thierry-gilgen-ict/ai-constitution/blob/main/docs/manual/'+({home:'usability',projects:'usability',instructions:name==='audit'?'audit':'constitution',compute:'workers',activity:'recovery',settings:'accounts'}[section]||'README')+'.md';
    $('breadcrumb').textContent = sections[section].label + ' / ' + (labels[name] || 'Project');
  } finally { navigating=false; }
};
page = name => window.navigateWorkspace(name);
const help=document.createElement('a');help.id='context-help';help.textContent='Help';help.target='_blank';help.rel='noreferrer';document.querySelector('.topbar > div').append(help);
const nav = document.querySelector('.sidebar nav');
nav.innerHTML = Object.entries(sections).map(([key,value])=>`<button class="nav" data-section="${key}">${e(value.label)}</button>`).join('');
nav.querySelectorAll('button').forEach(b=>b.onclick=()=>page(sections[b.dataset.section].pages[0][0]));
$('menu-toggle').onclick=()=>{const open=document.body.classList.toggle('menu-open');$('menu-toggle').setAttribute('aria-expanded',String(open));if(open)nav.querySelector('button')?.focus();};
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&document.body.classList.contains('menu-open')){document.body.classList.remove('menu-open');$('menu-toggle').setAttribute('aria-expanded','false');$('menu-toggle').focus();}});
window.addEventListener('popstate',()=>window.navigateWorkspace(new URL(location.href).searchParams.get('view')||'home',{replace:true,project:new URL(location.href).searchParams.get('project')}));

window.chooseDraftNavigation=dirtyChoice;
function dirtyChoice() {
  return new Promise(resolve=>{
    const {modal} = window.centerUI;
    modal('Keep your edits?', '<p>Your editor contains unsaved changes.</p><div class="button-row"><button id="dirty-save">Save draft and continue</button><button id="dirty-discard">Discard edits</button><button id="dirty-stay">Stay here</button></div>',null,null);
    const dialog=$('center-dialog'); let answered=false;
    const answer=value=>{answered=true;dialog.close();resolve(value);};
    $('dirty-stay').onclick=()=>answer('stay');
    $('dirty-save').onclick=()=>answer('save');$('dirty-discard').onclick=()=>answer('discard');
    dialog.addEventListener('close',()=>{if(!answered)resolve('stay');},{once:true});
  });
}

export function review(title, value, apply) {
  const {modal,safe,done}=window.centerUI;
  const changes=value.changes||value.diffs||[];
  const html=`<p>${e(value.note || 'Review the selected changes before applying.')}</p><dl class="project-facts"><dt>Affected scope</dt><dd>${e(value.scope || (value.targets?.length ? value.targets.length+' enrolled targets' : 'Selected target only'))}</dd><dt>When it takes effect</dt><dd>${e(value.effect || 'After this reviewed action; client loading requires a fresh session')}</dd><dt>Verification</dt><dd>${e(value.verification || 'Existing backend validation and fingerprint checks apply')}</dd><dt>Recovery</dt><dd>${e(value.rollback || 'Availability depends on this operation; later edits are protected')}</dd></dl>${value.targets?.length?'<h3>Affected enrollments</h3>'+value.targets.slice(0,100).map(t=>'<p>'+e(t.project||t.target||t.name)+' · '+(t.pinned?'Pinned · preserved':t.paused?'Paused · preserved':'Follows existing synchronization policy')+'</p>').join('')+(value.targets.length>100?'<p>Additional targets are included in the reviewed plan.</p>':''):''}${changes.map(d=>`<details class="diff-file"><summary>${e(d.path||'Change')}</summary><pre>${e(d.diff||d.status||'Review details in the affected workflow')}</pre></details>`).join('')}`;
  modal(title,html,apply?'Apply reviewed changes':null,apply?safe(async()=>{const result=await apply();done(result);return result;}):null);
}
window.reviewWorkspace = review;

registerView('activity-page', async()=>{
  const value=await api('/api/ui/operations');
  $('activity-content').innerHTML=`<p>${e(value.retention)}</p>`+value.jobs.map(j=>`<article class="panel"><span class="pill">${e(j.status)}</span><h2>${e(j.label)}</h2><p>${e(j.detail || 'No additional detail')}</p><p class="caption">${e(j.created_at?new Date(j.created_at*1000).toLocaleString():'Time not recorded')}</p><p>${e(j.recovery)}</p>${j.actions.includes('cancel')?`<button data-job-cancel="${e(j.id)}">Cancel operation</button>`:''}<details><summary>Operation reference</summary><code>${e(j.id)}</code></details><button data-recovery="${e(j.operation||'')}">Inspect related workflow</button></article>`).join('')||'<p>No retained operations yet. Downloads, scans and updates will appear here.</p>';
  $('activity-content').querySelectorAll('[data-job-cancel]').forEach(b=>b.onclick=()=>action({action:'cancel',job:b.dataset.jobCancel}));
  $('activity-content').querySelectorAll('[data-recovery]').forEach(b=>b.onclick=()=>page(/audit|constitution/.test(b.dataset.recovery)?'audit':/backup|restore/.test(b.dataset.recovery)?'vault':/update|stage/.test(b.dataset.recovery)?'updates':/prepare|toolkit/.test(b.dataset.recovery)?'workflows':'overview'));
});
registerView('drafts', async()=>{
  const value=await api('/api/ui/drafts');
  $('drafts-content').innerHTML='<p>These candidates are separate from the published library. Saving a draft never synchronizes it to projects.</p>'+Object.entries(value.files).map(([name,v])=>`<article class="panel"><h2>${e(name)}</h2><p>Saved ${e(new Date(v.saved_at*1000).toLocaleString())}</p><details><summary>Draft contents</summary><pre>${e(v.content)}</pre></details><button data-discard-draft="${e(name)}">Discard this draft</button></article>`).join('')+(Object.keys(value.files).length?'<button id="publish-drafts" class="primary">Review publication</button>':'<p>No saved drafts. Edit a file in Shared library to begin.</p>');
  $('drafts-content').querySelectorAll('[data-discard-draft]').forEach(b=>b.onclick=window.centerUI.safe(async()=>{const name=b.dataset.discardDraft;review('Discard private draft',{note:'Discard the saved candidate for '+name+'. The published library stays unchanged.',effect:'Candidate removed immediately',rollback:'No recovery for discarded candidate; copy it first if needed'},async()=>{const result=await api('/api/ui/draft-discard',{path:name,sha256:value.files[name].revision});await window.renderView('drafts');return result;});}));
  if($('publish-drafts'))$('publish-drafts').onclick=window.centerUI.safe(async()=>{const preview=await api('/api/ui/draft-preview',{});review('Publish saved drafts',preview,async()=>{const result=await api('/api/ui/draft-publish',{plan:preview.plan});window.invalidateStudioViews?.();await window.renderView('drafts');return result;});});
});
registerView('settings-page',()=>{
  $('settings-content').innerHTML='<article class="panel"><h2>Open and maintain this workspace</h2><p>Use the AI Constitution shortcut to start the service and open authenticated access. A browser cannot start a stopped local process.</p><div class="button-row"><button id="settings-startup-on">Start at login</button><button id="settings-startup-off">Disable login startup</button><button data-goto="overview">Service and recovery</button></div></article><article class="panel"><h2>Schedules</h2><p>Existing choices remain in effect. Configure each schedule in its owning workflow.</p><div class="button-row"><button data-goto="audit">Instruction scans</button><button data-goto="vault">Configuration backups</button><button data-goto="workflows">Resource automation</button></div></article><article class="panel"><h2>Learn with examples</h2><p>The demo uses fictional projects and simulated operations. It has no access to your workspace.</p><a class="button" href="/demo/" target="_blank" rel="noreferrer">Explore demonstration</a><p><a href="https://github.com/thierry-gilgen-ict/ai-constitution/blob/main/docs/manual/README.md" target="_blank" rel="noreferrer">Illustrated manual</a></p></article>';
  $('settings-startup-on').onclick=()=>action({action:'autostart',enabled:true});$('settings-startup-off').onclick=()=>action({action:'autostart',enabled:false});
  $('settings-content').querySelectorAll('[data-goto]').forEach(b=>b.onclick=()=>page(b.dataset.goto));
});
installProjects(); installForms();
document.addEventListener('workspace-ready',()=>{
  const v=window.uiBootstrap;
  $('environment-label').textContent=`${v.preferences.environment} · ${v.version} · ${v.controller}`;
  $('login-guidance').textContent=v.launch_kind==='packaged'?'Open the AI Constitution desktop shortcut. It starts the app and signs you in locally.':'Run the Local Control open command from your source installation.';
  const url=new URL(location.href);window.navigateWorkspace(url.searchParams.get('view')||'home',{replace:true,project:url.searchParams.get('project')});
});
document.addEventListener('workspace-version-changed',()=>{if($('version-reload'))return;const b=document.createElement('button');b.id='version-reload';b.textContent='Save drafts and reload';b.onclick=window.centerUI.safe(async()=>{if(window.studioUnsaved?.())await window.saveStudioDraft();location.reload();});$('environment-label').append(b);});
window.addEventListener('beforeunload',event=>{if(window.studioUnsaved?.()){event.preventDefault();event.returnValue='';}});
window.addEventListener('error',()=>connection('error','A dashboard component could not start. Reload the page; if it repeats, inspect the local application version.'));
await start();
