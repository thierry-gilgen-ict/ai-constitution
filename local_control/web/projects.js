/* Project-first journeys. All mutations use the existing reviewed APIs. */
const e = value => escapeHTML(value);
const ui = (op, body) => api('/api/ui/'+op,body);
const button = (id,label) => `<button id="${id}">${e(label)}</button>`;
const card = p => `<article class="panel project-card"><span class="pill">${e(p.status)}</span><h2>${e(p.name)}</h2><p>${e(p.machine)}</p><p class="caption">${e(p.project)}</p><div class="button-row"><button class="primary" data-open-project="${e(p.id)}">Open project</button><button data-favorite="${e(p.id)}" aria-label="Favorite ${e(p.name)}">${window.uiBootstrap?.preferences.favorites.includes(p.id)?'★ Favorite':'☆ Favorite'}</button></div></article>`;
function links(root) {
  root.querySelectorAll('[data-open-project]').forEach(b=>b.onclick=()=>window.navigateWorkspace('project-detail',{project:b.dataset.openProject}));
  root.querySelectorAll('[data-favorite]').forEach(b=>b.onclick=window.centerUI.safe(async()=>{
    const preferences=window.uiBootstrap.preferences, favorites=new Set(preferences.favorites);
    favorites.has(b.dataset.favorite)?favorites.delete(b.dataset.favorite):favorites.add(b.dataset.favorite);
    window.uiBootstrap.preferences=await ui('preferences',{favorites:[...favorites]});
    b.textContent=favorites.has(b.dataset.favorite)?'★ Favorite':'☆ Favorite';
  }));
  root.querySelectorAll('[data-destination]').forEach(b=>b.onclick=()=>page(b.dataset.destination));
}
async function home() {
  const data=await ui('home'), preferences=data.preferences;
  const rows=[...data.projects].sort((a,b)=>Number(preferences.favorites.includes(b.id))-Number(preferences.favorites.includes(a.id)) || (preferences.recent.indexOf(a.id)<0?100:preferences.recent.indexOf(a.id))-(preferences.recent.indexOf(b.id)<0?100:preferences.recent.indexOf(b.id)));
  $('home-content').innerHTML=`<div class="section-title"><div><h1>Your next project starts here.</h1><p>Choose a project, check its setup and open your coding application.</p></div><button id="home-add" class="primary">Add a project</button></div>${preferences.onboarding.project?'<article class="panel"><h2>Continue your setup</h2><button data-destination="onboarding">Resume onboarding</button></article>':''}${data.projects_stale?'<p class="center-note">Project observations are stale. Other workspace controls remain available.</p>':''}<div class="project-grid">${rows.slice(0,6).map(card).join('')||'<article class="center-empty"><h2>Bring your first project</h2><p>Use your existing coding subscription. Local models are optional.</p><button data-destination="onboarding">Connect a coding project</button></article>'}</div><article class="panel"><h2>Needs your attention</h2>${data.issues.map(v=>`<p>${e(v.service)}: ${e(v.message)}</p>`).join('')}${data.operations.filter(j=>['failed','interrupted'].includes(j.status)&&!j.acknowledged).map(j=>`<p>${e(j.label)} · ${e(j.status)}</p>`).join('')||'<p>No unresolved operations reported. Instruction coverage is verified separately.</p>'}<button data-destination="activity-page">View activity and recovery</button><button data-destination="audit">Check instruction health</button></article><article class="panel"><h2>Explore more</h2><div class="button-row"><button data-destination="models">Choose local models</button><button data-destination="worker-setup">Connect another computer</button><a class="button" href="/demo/" target="_blank" rel="noreferrer">Try the demonstration</a></div></article>`;
  $('home-add').onclick=()=>page('onboarding'); links($('home-content'));
}
async function projectList() {
  const data=await ui('projects');
  $('project-list-content').innerHTML='<div class="button-row"><button id="project-add" class="primary">Add a project</button><button data-destination="projects">Synchronization policies</button></div><label>Find a project<input type="search" id="project-search" autocomplete="off"></label><div class="project-grid" id="project-results"></div>';
  const draw=()=>{const text=$('project-search').value.toLowerCase();$('project-results').innerHTML=data.projects.filter(p=>(p.name+' '+p.project).toLowerCase().includes(text)).map(card).join('')||'<p>No matching projects. Add an existing folder to begin.</p>';links($('project-results'));};
  $('project-search').oninput=draw;$('project-add').onclick=()=>page('onboarding');links($('project-list-content'));draw();
}
async function launch(project) {
  const value=await api('/api/workflows/launch-preview',{project}), {modal,options}=window.centerUI;
  modal('Open a new coding session',`<p>Existing tasks stay in their current application and account.</p><label>Application<select id="project-launch-client">${options([['codex','Codex'],['cursor','Cursor'],['claude-code','Claude Code']])}</select></label><label>Execution<select id="project-launch-mode">${options([['hosted','Native application · existing login'],['local','Managed local terminal integration']])}</select></label><label>Claude profile<select id="project-launch-profile">${options((value.claude_profiles||[]).map(p=>[p.id,p.id]))}</select></label><label>Account mapping<select id="project-launch-account">${options([['','Verify in the native application'],...value.accounts.map(a=>[a.id,a.application+' · '+(a.label||a.login)+' · '+a.quota])])}</select></label><p class="caption">An account mapping does not change sign-in. Cursor local integration opens a terminal workflow; native Cursor Agent keeps its own connection. Claude requires an enrolled profile and a qualified Messages route for local execution.</p><button id="launch-profile-help">Manage Claude profiles</button>`, 'Launch new session',async()=>{
    const result=await api('/api/workflows/launch',{project,plan:value.plan,client:$('project-launch-client').value,mode:$('project-launch-mode').value,profile:$('project-launch-profile').value||undefined,account:$('project-launch-account').value});
    window.centerUI.done(result);
  });
  $('launch-profile-help').onclick=()=>{$('center-dialog').close();page('audit');};
}
async function projectDetail() {
  const identity=new URL(location.href).searchParams.get('project');
  const value=await ui('project',{id:identity}), p=value.project;
  window.uiBootstrap.preferences=await ui('preferences',{recent:[identity,...window.uiBootstrap.preferences.recent.filter(id=>id!==identity)].slice(0,30)});
  const tabs=['Overview','Instructions','Architecture','Apps & models','Configuration & backups','Activity'];
  $('project-detail-content').innerHTML=`<div class="section-title"><div><h1>${e(p.name)}</h1><p>${e(p.machine)} · ${e(p.project)}</p>${p.local===false?'<p class="caption">Remote metadata observed '+e(new Date(p.observed_at*1000).toLocaleString())+'; refresh through Controller sharing. This view does not contact the owner.</p>':''}</div><button id="project-launch" class="primary">Open project</button></div><nav class="workflow-tabs button-row" aria-label="Project sections">${tabs.map((label,i)=>`<button data-project-tab="${i}">${e(label)}</button>`).join('')}</nav><div id="project-tab-content"></div>`;
  $('project-launch').onclick=window.centerUI.safe(()=>p.local===false?window.centerUI.modal('Open on the owning computer','<p>Open Local Control on '+e(p.machine)+' and choose this checkout there. The shared inventory does not grant remote command execution.</p>',null,null):launch(p.project));
  const draw=index=>{
    $('project-detail-content').querySelectorAll('[data-project-tab]').forEach(b=>b.setAttribute('aria-pressed',String(+b.dataset.projectTab===index)));
    const evidence=value.inspection.evidence||{};
    const overview=`<article class="panel"><h2>Readiness</h2><dl class="project-facts"><dt>Installation</dt><dd>${e(p.status)}${p.local===false?' · owner reports '+e(p.owner_status||'Unknown'):''}</dd><dt>Client loading</dt><dd>${e(evidence.client_loading?.value||'Not independently verified')}</dd><dt>Local route</dt><dd>${e(p.route.mode)} · only managed sessions</dd><dt>Backup</dt><dd>${p.local===false?'Not shared':p.backup.configured?'Configured; inspect latest result':'Not configured'}</dd></dl>${value.inspection.findings.map(f=>`<p>${e(f.detail)} <button data-destination="${e(f.page)}">Review</button></p>`).join('')}<button data-destination="workflows">Prepare project or install toolkits</button></article>`;
    const content=[overview,
      '<article class="panel"><h2>Instructions and evidence</h2><p>Installed files, expected applicability and observed client loading are separate facts.</p><button data-destination="audit">Inspect instruction health</button><button data-destination="constitution">Open shared library</button><button data-destination="drafts">Review saved drafts</button></article>',
      `<article class="panel"><h2>Architecture</h2><p>${e(p.architecture?.id||'No architecture baseline selected')}</p><button data-destination="architectures">Choose or capture a template</button></article>`,
      `<article class="panel"><h2>Applications and accounts</h2>${p.accounts.map(a=>`<p>${e(a.application)} · ${e(a.label||a.login)} · ${e(a.login||'Identity not observed')}</p>`).join('')||'<p>No account mapping. Verify sign-in in your coding application.</p>'}<button data-destination="accounts">Manage accounts</button><button data-destination="models">Local model options</button></article>`,
      `<article class="panel"><h2>Private configuration</h2>${p.configurations.map(c=>`<p>${e(c.folder)}</p>`).join('')||'<p>No private configuration folder associated.</p>'}<button data-destination="vault">Configure backup or restore</button><button data-destination="storage">Storage preferences</button></article>`,
      '<article class="panel"><h2>Operations and history</h2><p>The activity center shows retained controller operations. Inspect the affected target before retrying.</p><button data-destination="activity-page">Open activity</button><button data-destination="projects">Synchronization history</button></article>'];
    $('project-tab-content').innerHTML=content[index];links($('project-tab-content'));
  };
  $('project-detail-content').querySelectorAll('[data-project-tab]').forEach(b=>b.onclick=()=>draw(+b.dataset.projectTab));draw(0);
}
async function onboarding() {
  const saved=window.uiBootstrap.preferences.onboarding, clients=window.uiBootstrap.clients;
  $('onboarding-content').innerHTML=`<h1>What would you like to do?</h1><div class="button-row"><button id="goal-project" aria-pressed="true">Connect a coding project</button><button data-destination="setup">Set up local models</button><button data-destination="worker-setup">Add another computer</button></div><article class="panel"><h2>1. Choose your project and applications</h2><label>Existing project directory<input id="onboard-project" value="${e(saved.project||'')}" placeholder="Absolute folder path on this computer" autocomplete="off"></label>${clients.map(c=>`<label class="check"><input type="checkbox" data-onboard-client="${c.id}" ${(saved.clients||['codex']).includes(c.id)?'checked':''}>${e(c.name)} · ${c.detected?'Detected on PATH':'Not detected on PATH'}</label>`).join('')}<p>No local model is required. Native sign-in stays in each application. Shared instructions will be previewed before enrollment.</p><label class="check"><input type="checkbox" id="onboard-adopt">Verify and adopt an existing portable constitution bundle</label><div class="button-row"><button id="onboard-preview" class="primary">Review instructions and enroll</button><button id="onboard-save">Save and continue later</button><button id="onboard-discover">Find repositories in a folder</button></div><p id="onboard-progress" role="status"></p></article><article class="panel"><h2>2. Optional architecture and private configuration</h2><p>After enrollment, select a template or capture choices from an existing project. You can keep your current architecture.</p><button data-destination="architectures">Explore templates</button></article>`;
  const progress=()=>({goal:'project',step:1,project:$('onboard-project').value.trim(),clients:[...document.querySelectorAll('[data-onboard-client]:checked')].map(b=>b.dataset.onboardClient)});
  $('onboard-save').onclick=window.centerUI.safe(async()=>{window.uiBootstrap.preferences=await ui('preferences',{onboarding:progress()});$('onboard-progress').textContent='Progress saved privately. No project files changed.';});
  $('onboard-preview').onclick=window.centerUI.safe(async()=>{
    const v=progress();if(!v.clients.length)throw new Error('Select at least one coding application.');
    window.uiBootstrap.preferences=await ui('preferences',{onboarding:v});
    const body={projects:[{project:v.project,clients:v.clients,adopt:$('onboard-adopt').checked}]};
    const preview=await api('/api/workspace/preview',body);
    if(!preview.ready)throw new Error(preview.projects[0]?.detail||'Resolve the project conflict before enrollment.');
    window.reviewWorkspace('Review project onboarding',{...preview,changes:preview.projects.flatMap(p=>p.changes||[]),scope:'Selected project and coding applications',effect:'Instruction files change on disk; verify loading in a new client session'},async()=>{
      const result=await api('/api/workspace/apply',{...body,plan:preview.plan});
      window.uiBootstrap.preferences=await ui('preferences',{onboarding:{}});
      const projects=(await ui('projects')).projects,p=projects.find(p=>p.project===preview.projects[0].project);
      if(p)setTimeout(()=>window.navigateWorkspace('project-detail',{project:p.id}),0);
      return result;
    });
  });
  $('onboard-discover').onclick=()=>{const {modal,field}=window.centerUI;modal('Find existing repositories',field('onboard-root','Search root')+'<p>Search is bounded to four levels. It does not execute project code.</p>','Find projects',async()=>{
    const result=await api('/api/workspace/discover',{roots:[$('onboard-root').value]});
    modal('Choose a repository',result.projects.map((p,i)=>`<p><button data-discovered="${i}">${e(p.name)}</button> ${e(p.project)}</p>`).join('')+(result.truncated?'<p>Search was truncated; choose a smaller root for full coverage.</p>':''),null,null);
    document.querySelectorAll('[data-discovered]').forEach(b=>b.onclick=()=>{$('onboard-project').value=result.projects[+b.dataset.discovered].project;$('center-dialog').close();});
  });};links($('onboarding-content'));
}
async function workerSetup() {
  const steps=['Select platform','Obtain package','Install and start','Pair','Choose access','Verify'];
  let step=window.uiBootstrap.preferences.onboarding.goal==='worker'?window.uiBootstrap.preferences.onboarding.step||0:0;
  const packages=await api('/api/workers');
  const draw=()=>{
    const content=[
      '<p>Choose the operating system of the other computer. Your controller’s OS may differ.</p><label>Worker platform<select id="wizard-platform"><option value="windows-amd64">Windows x64</option><option value="macos-arm64">macOS Apple Silicon</option><option value="macos-amd64">macOS Intel</option><option value="linux-amd64">Linux x64</option><option value="linux-arm64">Linux ARM64</option></select></label>',
      '<p>Download a verified package from Worker packages. Check its version and signing status. Transfer the complete archive to the other computer.</p><button data-destination="workers">Open worker packages</button>',
      '<p>On the worker: extract the full archive and use the complete commands shown for its OS. Keep private worker state outside the application folder.</p><button data-destination="workers">Show complete installation commands</button>',
      '<p>On the worker: create an expiring pairing invitation. On this controller: enter it in Machines. Certificate identity remains pinned.</p><button data-destination="machines">Pair the worker</button>',
      '<p>Inference pairing does not grant access to instruction files. The worker owner must approve roots and permissions locally before constitution auditing.</p><button data-destination="audit">Show constitution access setup</button>',
      '<p>Verify connection, supported version, model-service readiness and audit permissions separately. An offline or older worker can retain its last-known observations.</p><button data-destination="machines">Inspect connected machines</button>'
    ];
    $('worker-setup-content').innerHTML=`<h1>Add another computer</h1><p>Step ${step+1} of ${steps.length} · ${e(steps[step])}</p><progress max="6" value="${step+1}" aria-label="Worker setup progress"></progress><article class="panel">${content[step]}</article><div class="button-row">${step?button('worker-back','Back'):''}${step<5?button('worker-next','Save and continue'):button('worker-finish','Finish setup guide')}</div><p class="caption">Completing a step records your progress; readiness is verified separately.</p>`;
    if($('wizard-platform'))$('wizard-platform').value=window.uiBootstrap.preferences.onboarding.worker_platform||'windows-amd64';
    const save=async next=>{const worker_platform=$('wizard-platform')?.value||window.uiBootstrap.preferences.onboarding.worker_platform||'windows-amd64';window.uiBootstrap.preferences=await ui('preferences',{onboarding:{goal:'worker',step:next,worker_platform,worker_kind:$('wizard-kind')?.value||window.uiBootstrap.preferences.onboarding.worker_kind||'portable'}});step=next;draw();};
    if($('worker-next'))$('worker-next').onclick=window.centerUI.safe(()=>save(step+1));if($('worker-back'))$('worker-back').onclick=window.centerUI.safe(()=>save(step-1));
    if($('worker-finish'))$('worker-finish').onclick=window.centerUI.safe(async()=>{window.uiBootstrap.preferences=await ui('preferences',{onboarding:{}});page('machines');});links($('worker-setup-content'));
    const platform=window.uiBootstrap.preferences.onboarding.worker_platform||'windows-amd64';
    const win=platform.startsWith('windows'), os=platform.startsWith('macos')?'macos':win?'windows':'linux';
    if(step===1){
      const panel=$('worker-setup-content').querySelector('.panel');
      panel.insertAdjacentHTML('beforeend',packages.packages.filter(p=>p.platform==='all'||p.platform===os&&(platform.endsWith('arm64')?['arm64','aarch64'].includes(p.architecture):['amd64','x86-64','x86_64','x64'].includes(p.architecture))).map(p=>`<article><h3>${e(p.kind)} · ${e(p.architecture)}</h3><p>Version: ${e(p.version||'Not recorded; verify manifest')} · ${e(p.signing)}</p><p>${bytes(p.bytes)}</p><a href="${e(p.download)}" download>Download verified archive</a><details><summary>SHA-256 integrity</summary><code>${e(p.sha256)}</code></details></article>`).join('')||'<p>No matching cached packages. Use Worker packages to download a verified release or prepare a source bundle.</p>');
    }
    if(step===2||step===3){
      const panel=$('worker-setup-content').querySelector('.panel');
      panel.insertAdjacentHTML('beforeend','<label>Installation mode<select id="wizard-kind"><option value="portable">Portable package</option><option value="source">Python source</option></select></label><p>On the worker: open a fresh terminal in the extracted package folder.</p><div id="wizard-commands"></div>');
      const commands=()=>{
        const source=$('wizard-kind').value==='source';
        const exe=source?(win?'& .\\.venv\\Scripts\\python.exe scripts/local_control.py':'./.venv/bin/python scripts/local_control.py'):(win?"& '.\\app\\ai-constitution-local\\ai-constitution-local.exe'":'./app/ai-constitution-local/ai-constitution-local');
        const prefix=exe+(win?" --state-dir (Join-Path $env:USERPROFILE '.config\\ai-constitution\\local-worker')":' --state-dir "$HOME/.config/ai-constitution/local-worker"');
        const address=win?"(Read-Host 'Worker IPv4 address')":'WORKER_PRIVATE_IPV4';
        const rows=[];
        if(source&&step===2)rows.push(['Prepare environment',win?'py -3 -m venv .venv\n& .\\.venv\\Scripts\\python.exe -m pip install -r requirements-local-node.txt':'python3 -m venv .venv\n./.venv/bin/python -m pip install -r requirements-local-node.txt']);
        rows.push([step===2?'Start worker · keep terminal open':'Create expiring invitation · separate terminal',prefix+(step===2?' node --address ':' pairing --address ')+address]);
        if(step===2)rows.push(['Optional model runtime installation',prefix+' setup --ollama --llmfit']);
        $('wizard-commands').innerHTML=rows.map(([label,command],i)=>`<h3>${e(label)}</h3><pre class="center-code" id="wizard-command-${i}">${e(command)}</pre><button data-wizard-copy="${i}">Copy command</button>`).join('');
        $('wizard-commands').querySelectorAll('[data-wizard-copy]').forEach(b=>b.onclick=window.centerUI.safe(async()=>{await navigator.clipboard.writeText($('wizard-command-'+b.dataset.wizardCopy).textContent);notice('Command copied.');}));
      };$('wizard-kind').value=window.uiBootstrap.preferences.onboarding.worker_kind||'portable';$('wizard-kind').onchange=commands;commands();
    }
    if(step===5)$('worker-setup-content').querySelector('.panel').insertAdjacentHTML('beforeend',Object.entries(state?.nodes||{}).filter(([,n])=>n.kind==='worker').map(([id,n])=>`<article><h3>${e(n.name)}</h3><p>Connectivity: ${e(state.health?.[id]?.status||'Not checked')} · observed ${e(state.health?.[id]?.checked_at?new Date(state.health[id].checked_at*1000).toLocaleString():'never')}</p><p>Capabilities and package version: inspect Worker packages → maintenance. Model readiness: check Machines. File permissions: inspect Constitution health.</p></article>`).join('')||'<p>No paired workers yet.</p>');
  };draw();
}
export function installProjects() {
  window.openProjectSession=launch;
  registerView('home',home);registerView('project-list',projectList);registerView('project-detail',projectDetail);registerView('onboarding',onboarding);registerView('worker-setup',workerSetup);
}
