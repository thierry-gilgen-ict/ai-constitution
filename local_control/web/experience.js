/* Recovery, onboarding and updates. All provider and user text is escaped. */
(() => {
  const e = escapeHTML, {modal, safe, done, table, field, options, when, size} = window.centerUI;
  let tracked = null, lastUpdateCheck = 0, release = null;
  const completed = new Set();
  const button = (id, label) => `<button id="${id}">${e(label)}</button>`;
  const go = name => { $('center-dialog').close(); page(name); };
  const recovery = job => /backup|restore|scheduled/.test(job.operation) ? 'vault' : /update|stage|check/.test(job.operation) ? 'updates' : /synchron|reconcile/.test(job.operation) ? 'projects' : /refresh/.test(job.operation) ? 'accounts' : 'overview';
  window.trackOperation = result => {
    tracked = result.job;
    $('operation-strip').hidden = false;
    $('operation-strip').innerHTML = '<strong>Operation queued</strong><progress aria-label="Operation in progress"></progress><p>You can keep using the dashboard.</p>';
  };
  window.renderExperience = current => {
    $('notifications-count').textContent = (current.notifications || []).length + (current.service_errors || []).length;
    if (tracked) {
      const job = current.jobs.find(j => j.id === tracked);
      if (job) {
        $('operation-strip').innerHTML = `<div class="section-title"><strong>${e(job.label)}</strong><span class="pill">${e(job.status)}</span></div><p>${e(job.detail)}</p>${['queued','running'].includes(job.status) ? '<progress aria-label="Operation in progress"></progress>' : '<button id="operation-dismiss">Dismiss</button>'}`;
        if ($('operation-dismiss')) $('operation-dismiss').onclick = () => { tracked = null; $('operation-strip').hidden = true; };
        if (job.status === 'done' && !completed.has(job.id) && !document.querySelector('dialog[open]')) {
          completed.add(job.id); const name = document.querySelector('.page.active')?.id;
          if (name) window.centerPage(name);
        }
      }
    }
    if (Date.now() - lastUpdateCheck > 60000) {
      lastUpdateCheck = Date.now(); api('/api/updates').then(v => {
        release = v; $('release-badge').hidden = !v.available;
        $('release-badge').textContent = v.available ? `Update available · ${v.latest}` : 'Up to date';
      }).catch(() => {});
    }
  };
  $('release-badge').onclick = () => page('updates');
  $('notifications-button').onclick = () => {
    const list = state?.notifications || [];
    modal('Notifications', (state?.service_errors || []).map(v=>`<p class="review-error">${e(v.service)}: ${e(v.message)}</p>`).join('') + (list.length ? list.map(j => `<article class="notification-card"><span class="pill">${e(j.status)}</span><h3>${e(j.label)}</h3><p>${e(j.detail)}</p><p class="caption">${e(when(j.last_observed || j.created_at))}${j.occurrences ? ' · repeated ' + j.occurrences + ' times' : ''}</p><div class="button-row"><button data-recover="${e(j.id)}">Review and retry</button><button data-ack="${e(j.id)}">Acknowledge</button></div></article>`).join('') : '<p>No unresolved operation failures.</p>'), null, null);
    $('center-dialog-body').querySelectorAll('[data-recover]').forEach(b => b.onclick = () => go(recovery(list.find(j => j.id === b.dataset.recover))));
    $('center-dialog-body').querySelectorAll('[data-ack]').forEach(b => b.onclick = safe(async () => { await api('/api/operations/acknowledge', {id:b.dataset.ack}); await refresh(); $('notifications-button').click(); }));
  };

  window.projectMetadata = p => `<dl class="project-facts"><dt>Machine</dt><dd>${e(p.machine)}</dd><dt>Architecture</dt><dd>${p.architecture ? e(p.architecture.id + ' · ' + p.architecture.version + ' · ' + (p.architecture.policy || 'latest')) : 'Not selected'}</dd><dt>Applications / accounts</dt><dd>${(p.accounts || []).map(a => e([a.application,a.label,a.login].filter(Boolean).join(' · '))).join('<br>') || 'Not assigned'}</dd><dt>Private configuration</dt><dd>${(p.configurations || []).map(c => e(c.folder)).join('<br>') || 'Not mapped'}</dd><dt>Backup</dt><dd>${p.backup?.configured ? e(p.backup.error || when(p.backup.last_success)) : 'Not configured'}</dd><dt>Local route</dt><dd>${e(p.route?.mode || 'Unconfigured')} · ${e(p.route?.applies || '')}</dd></dl><div class="button-row"><button data-project-launch="${e(p.project)}" data-client="codex">Open local Codex</button><button data-project-launch="${e(p.project)}" data-client="cursor">Open in Cursor</button><button data-project-resolve="vault">Configure backup</button><button data-project-resolve="accounts">Assign subscription</button></div>`;
  async function projectTools() {
    const bar = $('sync-content').querySelector('.button-row');
    if (bar) { const b = document.createElement('button'); b.id='bring-projects'; b.textContent='Bring my projects'; b.className='primary'; b.onclick=safe(discover); bar.prepend(b); }
    $('sync-content').querySelectorAll('[data-project-launch]').forEach(b => b.onclick = safe(async()=>done(await api('/api/action',{action:'launch',project:b.dataset.projectLaunch,client:b.dataset.client}))));
    $('sync-content').querySelectorAll('[data-project-resolve]').forEach(b => b.onclick=()=>page(b.dataset.projectResolve));
  }
  async function discover() {
    modal('Bring my projects', '<p>Choose the folders that contain your repositories. Search is limited to four levels and 5,000 directories.</p><label>Search roots · one absolute path per line<textarea id="discover-roots" rows="3" autocomplete="off"></textarea></label>', 'Find repositories', async()=> {
      const found = await api('/api/workspace/discover',{roots:$('discover-roots').value.split('\n').map(s=>s.trim()).filter(Boolean)}), vault=await api('/api/vault');
      modal('Choose projects to onboard', `<p>${e(found.note)}</p>${found.truncated?'<p class="review-error">Search limit reached. Use a smaller root to find more projects.</p>':''}${found.projects.map((p,i)=>`<article class="discovery-row"><label class="check"><input type="checkbox" data-discover="${i}" ${p.enrolled?'disabled':'checked'}>${e(p.name)} ${p.enrolled?'· already enrolled':''}</label><p class="caption">${e(p.project)}</p>${p.portable_bundle&&!p.enrolled?`<label class="check"><input type="checkbox" id="adopt-${i}">Verify and adopt the existing portable bundle</label>`:''}<label>Existing private configuration<select id="config-${i}">${options([['','Associate later'],...Object.entries(vault.projects).map(([id,v])=>[id,v.name])])}</select></label></article>`).join('') || '<p>No repositories found in these roots.</p>'}`, 'Preview enrollment', async()=> {
        const body={projects:[...document.querySelectorAll('[data-discover]:checked')].map(b=>({project:found.projects[+b.dataset.discover].project,adopt:$('adopt-'+b.dataset.discover)?.checked||false,configuration:$('config-'+b.dataset.discover).value}))};
        const preview=await api('/api/workspace/preview',body);
        modal('Review project enrollment', `<p>${e(preview.note)}</p><p><strong>${preview.ready} projects ready</strong></p>${preview.projects.map(p=>`<details class="diff-file" open><summary>${e(p.project)} · ${e(p.status)}</summary>${p.detail?`<p class="review-error">${e(p.detail)}</p>`:''}${(p.changes||[]).map(v=>`<details><summary>${e(v.path)}</summary><pre>${e(v.diff)}</pre></details>`).join('')}</details>`).join('')}`, preview.ready?'Enroll ready projects':null, preview.ready?async()=>{done(await api('/api/workspace/apply',{...body,plan:preview.plan}));await window.centerPage('projects');}:null);
      });
    });
  }

  async function updatesPage() {
    const [v,inbox]=await Promise.all([api('/api/updates'),api('/api/model-inbox')]); release=v;
    $('updates-content').innerHTML=`<article class="panel"><span class="eyebrow">APPLICATION</span><div class="section-title"><h2>${v.available?'Update available · '+e(v.latest):'Installed · '+e(v.current)}</h2>${button('update-check','Check GitHub')}</div><p>Last successful check: ${e(when(v.checked_at))}</p>${v.error?`<p class="review-error">${e(v.error)}</p>`:''}<label class="check"><input type="checkbox" id="update-auto" ${v.automatic_check?'checked':''}>Check public GitHub releases daily</label><p class="caption">No automatic installation. No account credentials are sent.</p>${v.notes?`<details><summary>Release changes</summary><pre class="release-notes">${e(v.notes)}</pre></details>`:''}<div class="button-row">${v.url?`<a class="button" target="_blank" rel="noreferrer" href="${e(v.url)}">View release on GitHub ↗</a>`:''}${v.available&&!v.staged?button('update-download','Download and verify update'):''}${v.staged?button('update-apply','Review restart · '+v.staged.version):''}${v.previous?button('update-rollback','Roll back application'):''}</div><p class="caption">${e(state?.permissions || '')}</p></article><article class="panel"><span class="eyebrow">MODEL DEFINITIONS</span><div class="section-title"><h2>Your model-update inbox</h2>${button('model-check','Check model definitions')}</div><p>${e(inbox.note || 'Discover additions, changed capabilities and prices before updating your library.')}</p><p>${(inbox.changes||[]).length} changes · ${(inbox.route_impact||[]).length} routes to review</p>${inbox.changes?.length?`<label>Filter provider or model<input id="model-diff-filter" placeholder="Search definitions"></label><div id="model-diff-list"></div>`:''}${inbox.status==='review'?button('model-apply','Review and apply definitions'):''}<details><summary>Routing impact</summary><pre>${e(JSON.stringify(inbox.route_impact||[],null,2))}</pre></details></article>`;
    $('update-check').onclick=safe(async()=>done(await api('/api/updates/check',{})));
    $('update-auto').onchange=safe(async()=>await api('/api/updates/settings',{automatic_check:$('update-auto').checked}));
    if($('update-download')) $('update-download').onclick=safe(async()=>done(await api('/api/updates/stage',{version:v.latest})));
    if($('update-apply')) $('update-apply').onclick=safe(()=>restart(false));
    if($('update-rollback')) $('update-rollback').onclick=safe(()=>restart(true));
    $('model-check').onclick=safe(async()=>done(await api('/api/model-inbox/check',{})));
    if($('model-diff-filter')) {
      const draw=()=>{const term=$('model-diff-filter').value.toLowerCase(), rows=inbox.changes.filter(r=>(r.provider+'/'+r.model).toLowerCase().includes(term));$('model-diff-list').innerHTML=`<p class="caption">${rows.length} matching definitions · showing up to 100</p>`+rows.slice(0,100).map(r=>`<details class="diff-file"><summary>${e(r.kind)} · ${e(r.provider+'/'+r.model)}</summary><pre>${e(JSON.stringify(r.fields,null,2))}</pre></details>`).join('');}; $('model-diff-filter').oninput=draw;draw();
    }
    if($('model-apply')) $('model-apply').onclick=()=>modal('Apply catalog changes',`<p>${e(inbox.note)}</p><p>${inbox.summary.models_added.length} added · ${inbox.summary.models_removed.length} removed · ${inbox.summary.models_changed.length} changed. A rollback snapshot will be retained.</p>`,'Apply reviewed definitions',async()=>{done(await api('/api/model-inbox/apply',{plan:inbox.plan}));await updatesPage();});
  }
  async function restart(rollback,node=null) {
    const call=(operation,body)=>node?api('/api/workers/manage',{node,operation,...body}):api('/api/updates/'+operation,body);
    const p=await call('preview',{rollback});
    modal(rollback?'Review application rollback':'Review update restart',`<p>${e(p.note)}</p><p>Target version: <strong>${e(p.version)}</strong></p>${p.blockers.map(b=>`<p class="review-error">${e(b)}</p>`).join('')}<label class="check"><input id="update-idle" type="checkbox">All other clients using this service are idle</label>`,p.blockers.length?null:'Restart and verify',p.blockers.length?null:async()=>{
      if(!$('update-idle').checked) throw new Error('Confirm other clients are idle before restarting.');
      done(await call('apply',{rollback,plan:p.plan,acknowledge_external:true}));
      if(!node) { notice('Restarting. This page will reconnect automatically.'); lastUpdateCheck=0; }
    });
  }

  async function performance() {
    const v=await api('/api/insights');
    $('insights-content').innerHTML=`<article class="panel"><div class="section-title"><h2>Choose the next-request profile</h2>${button('performance-refresh','Refresh measurements')}</div><p>${e(v.note)}</p><div class="button-row">${['fast','deep','gaming'].map(p=>`<button data-profile="${p}">${p==='fast'?'Fast · measured latency':p==='deep'?'Deep · configured primary':'Gaming · release protected GPU'}</button>`).join('')}</div><label class="check"><input type="checkbox" id="route-auto" ${state?.automatic_fallback?'checked':''}>Use a tested, healthy fallback before dispatch if the selected route is unavailable</label><p class="caption">No replay after a generation is sent. Gaming always honors GPU exclusions.</p></article><div class="center-grid">${v.profiles.map(p=>`<article class="panel"><span class="eyebrow">${e(p.node)} · ${e(p.context)} CONTEXT</span><h2>${e(p.model)}</h2><p>${p.passed}/${p.count} fixture evaluations passed · ${e(p.level)}</p><dl class="project-facts"><dt>First text</dt><dd>${p.first_text_seconds??'Unknown'} seconds</dd><dt>Throughput</dt><dd>${p.tokens_per_second??'Unknown'} tokens/sec</dd><dt>Resident GPU memory</dt><dd>${e(size(p.resident_gpu_bytes))}</dd></dl><p class="caption">${e(p.note)}</p><details><summary>Memory evidence</summary><pre>${e(JSON.stringify(p.memory,null,2))}</pre></details></article>`).join('')||'<article class="panel"><h2>No measured profiles yet.</h2><p>Configure and test a model, then run its coding evaluation from Overview. Estimates in Model library remain clearly labelled.</p><button id="evaluate-go">Open evaluations</button></article>'}</div>`;
    $('performance-refresh').onclick=safe(performance);
    document.querySelectorAll('[data-profile]').forEach(b=>b.onclick=safe(async()=>done(await api('/api/routing/profile',{profile:b.dataset.profile,automatic_fallback:$('route-auto').checked}))));
    $('route-auto').onchange=safe(async()=>done(await api('/api/routing/profile',{profile:state?.task_profile||'deep',automatic_fallback:$('route-auto').checked})));
    if($('evaluate-go')) $('evaluate-go').onclick=()=>page('overview');
  }

  async function vaultTools() {
    const v=await api('/api/encrypted-backup');
    $('vault-content').insertAdjacentHTML('afterbegin',`<article class="panel" id="encryption-panel"><span class="eyebrow">ENCRYPTION &amp; RECOVERY</span><h2>${v.enabled?'Encrypted restic backups enabled':'Choose your backup protection'}</h2><p>${e(v.note)}</p><p>restic: <strong>${v.installed?'Installed':'Not installed'}</strong> · <a href="${e(v.docs)}" target="_blank" rel="noreferrer">Installation guide ↗</a></p><div class="button-row">${button('restic-settings','Configure encryption')}${button('restic-init','Initialize repository')}${button('restic-check','Verify repository')}${button('restic-restore','Restore encrypted snapshot')}${button('restic-retention','Review retention')}${button('backup-os-schedule','Schedule outside the dashboard')}</div></article>`);
    $('restic-settings').onclick=()=>modal('Encrypted backup settings',`${field('restic-repo','Repository location',v.repository)}${field('restic-password-file','Private password file (optional)',v.password_file)}${field('restic-password-env','Password environment-variable name',v.password_env)}${field('restic-keep','Snapshots to keep',v.keep_last,'number')}<label class="check"><input type="checkbox" id="restic-enabled" ${v.enabled?'checked':''}>Use this encrypted backend for manual and scheduled backups</label><p class="caption">Never enter the password itself. S3/SFTP credentials come from your OS environment or normal backend configuration.</p>`,'Save encryption settings',async()=>{done(await api('/api/encrypted-backup/settings',{repository:$('restic-repo').value,password_file:$('restic-password-file').value,password_env:$('restic-password-env').value,keep_last:Number($('restic-keep').value),enabled:$('restic-enabled').checked}));await window.centerPage('vault');});
    $('restic-init').onclick=()=>modal('Initialize encrypted repository','<p>Create a restic repository at the configured destination. Keep a separate copy of its password before adding backups.</p>','Initialize repository',async()=>done(await api('/api/encrypted-backup/init',{})));
    $('restic-check').onclick=safe(async()=>done(await api('/api/encrypted-backup/check',{})));
    $('restic-retention').onclick=safe(async()=>{const p=await api('/api/encrypted-backup/retention-preview',{});modal('Review snapshot retention',`<p>${e(p.note)}</p><p>${p.remove.length} snapshots will be deleted.</p><pre>${e(p.remove.join('\n'))}</pre>`,p.remove.length?'Delete reviewed snapshots':null,p.remove.length?async()=>done(await api('/api/encrypted-backup/retention-apply',{plan:p.plan})):null);});
    $('restic-restore').onclick=safe(async()=>{const v=await api('/api/encrypted-backup/snapshots');modal('Restore encrypted snapshot',`<label>Snapshot<select id="encrypted-snapshot">${options(v.snapshots.map(s=>[s.id,s.time+' · '+s.id.slice(0,12)]))}</select></label>${field('encrypted-destination','New absolute directory')}`,'Preview restoration',async()=>{const body={snapshot:$('encrypted-snapshot').value,destination:$('encrypted-destination').value},p=await api('/api/encrypted-backup/restore-preview',body);modal('Review encrypted restoration',`<p>${e(p.note)}</p><p>${e(p.destination)}</p>`,'Restore and verify',async()=>done(await api('/api/encrypted-backup/restore',{...body,plan:p.plan})));});});
    $('backup-os-schedule').onclick=safe(async()=>{const schedule=await api('/api/backup-schedule');modal('Run backups while the dashboard is closed',`${field('os-backup-hours','Interval in hours',schedule.hours,'number')}<label class="check"><input id="os-backup-enabled" type="checkbox" ${schedule.enabled?'checked':''}>Enable a backup task for my OS user</label><p>Windows and macOS require your user to be logged in. Linux requires systemd’s user manager. Enable the backup schedule and select project folders above too. Credentials must be available to the scheduled process; a private password file is convenient for restic.</p>`,'Save OS schedule',async()=>done(await api('/api/backup-schedule',{enabled:$('os-backup-enabled').checked,hours:Number($('os-backup-hours').value)})));});
  }

  async function workerTools() {
    const nodes=Object.entries(state?.nodes||{}).filter(([,n])=>n.kind==='worker');
    $('workers-content').insertAdjacentHTML('afterbegin',`<article class="panel"><span class="eyebrow">WORKER LIFECYCLE</span><h2>Maintain your other computers.</h2><button id="worker-release-download">Get a verified release package</button><p>Pairing credentials, certificates and model storage stay on each worker during upgrades. Put a worker in maintenance before restarting it.</p>${nodes.map(([id,n])=>`<div class="section-title"><strong>${e(n.name)}</strong><button data-worker-open="${e(id)}">Version, updates &amp; startup</button></div>`).join('')||'<p class="caption">Paired workers appear here. Use the installation instructions below to add one.</p>'}<details><summary>Start a worker automatically at login</summary><p>After installing a package, run its executable with <code>autostart enable --worker-address PRIVATE_IPV4</code>. Disable with the same address and <code>autostart disable</code>. Windows and macOS are supported.</p></details></article>`);
    $('worker-release-download').onclick=()=>modal('Download worker package','<label>Computer type<select id="worker-release-target"><option value="windows-amd64">Windows · x64</option><option value="darwin-arm64">macOS · Apple Silicon</option><option value="linux-x86_64">Linux · x64</option></select></label><p>Downloads and verifies the official GitHub package. Extract the complete archive on the worker and follow the setup commands below. Other architectures can use the source package.</p>','Download and verify',async()=>done(await api('/api/workers/fetch',{target:$('worker-release-target').value})));
    document.querySelectorAll('[data-worker-open]').forEach(b=>b.onclick=safe(()=>worker(b.dataset.workerOpen)));
  }
  async function worker(node) {
    const call=(operation,body={})=>api('/api/workers/manage',{node,operation,...body});
    const [v,u]=await Promise.all([call('version'),call('updates')]);
    modal('Worker maintenance',`<p>Version <strong>${e(v.version)}</strong> · protocol ${e(v.protocol)}</p><p class="caption">${e((v.capabilities||[]).join(' · '))}</p>${u.error?`<p class="review-error">${e(u.error)}</p>`:''}<p>${u.available?'Update available: '+e(u.latest):'No newer release reported'}</p><div class="button-row">${button('worker-check','Check updates')}${u.available&&!u.staged?button('worker-download','Download update'):''}${u.staged?button('worker-restart','Review restart'):''}${u.previous?button('worker-rollback','Roll back'):''}${button('worker-autostart','Enable login startup')}${button('worker-no-autostart','Disable login startup')}${button('worker-refresh','Refresh worker status')}</div><div id="worker-job-status" role="status"></div>`,null,null);
    async function track(result) {
      if(!result.job){$('worker-job-status').textContent=result.applies||result.note||'Saved';return;}
      $('worker-job-status').textContent='Operation queued on the worker…';
      for(let n=0;n<300;n++) {
        if(!$('center-dialog').open||!$('worker-job-status'))return;
        const jobs=await call('jobs'), job=jobs.jobs.find(j=>j.id===result.job);
        if(job) {$('worker-job-status').textContent=job.label+' · '+job.status+' · '+job.detail;if(!['queued','running'].includes(job.status))return;}
        await new Promise(resolve=>setTimeout(resolve,2000));
      }
    }
    $('worker-check').onclick=safe(async()=>track(await call('check')));
    if($('worker-download'))$('worker-download').onclick=safe(async()=>track(await call('stage',{version:u.latest})));
    if($('worker-restart'))$('worker-restart').onclick=safe(()=>restart(false,node));
    if($('worker-rollback'))$('worker-rollback').onclick=safe(()=>restart(true,node));
    $('worker-autostart').onclick=safe(async()=>track(await call('startup',{enabled:true})));
    $('worker-no-autostart').onclick=safe(async()=>track(await call('startup',{enabled:false})));
    $('worker-refresh').onclick=safe(()=>worker(node));
  }

  async function accountTools() {
    const data=await api('/api/monitoring'), v=data.local;
    $('accounts-content').insertAdjacentHTML('afterbegin',`<article class="panel"><h2>Collector health &amp; API cost connections</h2>${(v.alerts||[]).map(a=>`<p class="review-error">${e(a.message)}</p>`).join('')||'<p>No collector or allowance alerts.</p>'}<details><summary>Available connector permissions</summary>${table(['Connector','Scope','Permission'],(v.connectors||[]).map(c=>`<tr><td>${e(c.id)}</td><td>${e(c.scope)}</td><td>${e(c.permission)}</td></tr>`))}</details>${Object.values(v.accounts).map(a=>`<article class="notification-card"><strong>${e(a.label||a.login||a.id)}</strong><p class="caption">Subscription identity ${e(a.subscription_key||a.id)} · same account across hosts, not additive quotas</p>${a.report?`<details><summary>Latest API cost report · ${e(a.report.status)}</summary><pre>${e(JSON.stringify(a.report,null,2))}</pre></details>`:''}<div class="button-row"><button data-connector-config="${e(a.id)}">Configure read-only connector</button>${a.connector&&a.connector.id!=='manual/import'?`<button data-connector-refresh="${e(a.id)}">Refresh API cost report</button>`:''}</div></article>`).join('')}</article>`);
    document.querySelectorAll('[data-connector-config]').forEach(b=>b.onclick=()=>{const a=v.accounts[b.dataset.connectorConfig];modal('Connect an API organization',`<p>API billing is separate from ChatGPT, Codex and Claude subscription quotas. Reads use an admin key already in your OS environment. No inference calls.</p><label>Connector<select id="cost-connector">${options([['manual/import','Manual / imported observations'],['openai-api','OpenAI API organization costs'],['anthropic-api','Anthropic API organization costs']])}</select></label>${field('cost-key-env','Admin key environment-variable name',a.connector?.key_env||'OPENAI_ADMIN_KEY')}`,'Save connector',async()=>{done(await api('/api/connectors/configure',{account:a.id,connector:$('cost-connector').value,key_env:$('cost-key-env').value}));await window.centerPage('accounts');});$('cost-connector').value=a.connector?.id||'manual/import';});
    document.querySelectorAll('[data-connector-refresh]').forEach(b=>b.onclick=safe(async()=>done(await api('/api/connectors/refresh',{account:b.dataset.connectorRefresh}))));
  }

  const parentPage=window.centerPage;
  window.centerPage=safe(async name=>{
    await parentPage(name);
    if(name==='projects')await projectTools();
    if(name==='updates')await updatesPage();
    if(name==='insights')await performance();
    if(name==='vault')await vaultTools();
    if(name==='workers')await workerTools();
    if(name==='accounts')await accountTools();
  });
  const policy=document.createElement('label');policy.innerHTML='Architecture update policy<select id="template-follow-policy"><option value="">Follow saved template; pin unsaved edits</option><option value="latest">Follow latest saved template</option><option value="pinned">Pin this exact revision</option></select>';
  $('template-apply-preview').before(policy);
  const history=document.createElement('button');history.textContent='Versions & inheritance';history.type='button';$('template-clone').after(history);
  history.onclick=safe(async()=>{
    const value=window.templateRevision(),versions=await api('/api/studio/template-versions?id='+encodeURIComponent(value.id)),templates=await api('/api/studio/templates');
    modal('Template versions & inheritance',`<p>Projects can follow the current saved template or pin an exact revision. Applying a revision previews a migration; local edits are protected.</p>${versions.versions.map((v,i)=>`<div class="history-row"><span>${e(v.version)} · ${e(v.revision.slice(0,12))}</span><button data-template-revision="${i}">Open revision</button></div>`).join('')}<h3>Inherit a saved baseline</h3><label>Parent template<select id="template-parent">${options(templates.templates.map((t,i)=>[String(i),t.template.name+' · '+t.template.version]))}</select></label><button id="template-inherit">Create child from selected baseline</button><p class="caption">The parent is embedded as an immutable snapshot. Child components and files override matching parent entries. Edit constraints in the template JSON using exact numeric comparisons, for example &gt;=1.2.0,&lt;2.0.0.</p>`,null,null);
    document.querySelectorAll('[data-template-revision]').forEach(b=>b.onclick=()=>{$('center-dialog').close();window.useCapturedTemplate(versions.versions[+b.dataset.templateRevision].template);$('template-follow-policy').value='pinned';});
    $('template-inherit').onclick=()=>{const parent=templates.templates[+$('template-parent').value].template;const child={schema_version:1,id:parent.id+'-child',name:parent.name+' · child',version:'1.0.0',description:'Project baseline inheriting '+parent.name,components:[],extends:parent,files:{},decisions:[]};$('center-dialog').close();window.useCapturedTemplate(child);};
  });
})();
