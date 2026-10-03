/* Private library studio. User text is displayed as text, never executable HTML. */
(() => {
  let templates = [], components = [], roles = [], baseline = null, baselineHash = null;
  let templateDirty = false, fileDirty = false, currentFile = null, fileList = [], editingComponent = -1;
  let previewAction = null, templatesLoaded = false, filesLoaded = false;
  const clone = value => JSON.parse(JSON.stringify(value));
  const lines = value => value.split('\n').map(v => v.trim()).filter(Boolean);
  const comma = value => value.split(',').map(v => v.trim()).filter(Boolean);
  const call = (operation, body) => api('/api/studio/' + operation, body);
  const safely = fn => async (...args) => { try { await fn(...args); } catch (e) {
    notice(e.message, true);
    const dialog = document.querySelector('.studio-modal[open]');
    if (dialog) {
      let message = dialog.querySelector('[data-studio-error]');
      if (!message) { message = document.createElement('p'); message.dataset.studioError = ''; message.className = 'review-error'; dialog.prepend(message); }
      message.textContent = e.message; message.scrollIntoView({block:'nearest'});
    }
  } };
  const changed = () => { templateDirty = true; $('template-status').textContent = 'Unsaved changes'; };
  const reviewHTML = value => !value ? '' : `<div class="studio-review">${value.errors.map(v => `<p class="review-error">${escapeHTML(v)}</p>`).join('')}${value.warnings.map(v => `<p>${escapeHTML(v)}</p>`).join('')}<p class="caption">${escapeHTML(value.evidence)}</p></div>`;
  const changesHTML = value => (value.changes || []).map(v => `<details class="diff-file"><summary><span class="pill">${escapeHTML(v.status)}</span> ${escapeHTML(v.path)}</summary><pre>${escapeHTML(v.diff || 'Binary content changed.')}</pre></details>`).join('') || '<p>No file changes.</p>';

  function preview(title, value, label, apply) {
    $('studio-preview').querySelector('[data-studio-error]')?.remove();
    $('studio-preview-title').textContent = title;
    $('studio-preview-body').innerHTML = `<p>${escapeHTML(value.note || '')}</p>${reviewHTML(value.review)}${value.conflicts?.length ? `<p class="review-error">Resolve upstream conflicts first: ${escapeHTML(value.conflicts.join(', '))}</p>` : ''}${value.retained_files?.length ? `<p>Kept from the previous baseline: ${escapeHTML(value.retained_files.join(', '))}</p>` : ''}${changesHTML(value)}`;
    $('studio-preview-confirm').textContent = label;
    $('studio-preview-confirm').hidden = !apply;
    $('studio-preview-confirm').disabled = Boolean(value.conflicts?.length || value.review?.errors?.length);
    previewAction = apply;
    $('studio-preview').showModal();
  }
  $('studio-preview-cancel').onclick = () => $('studio-preview').close();
  $('studio-preview-confirm').onclick = safely(async () => {
    if (!previewAction) return;
    $('studio-preview-confirm').disabled = true;
    try { await previewAction(); $('studio-preview').close(); }
    finally { $('studio-preview-confirm').disabled = false; }
  });

  async function loadTemplates() {
    const data = await call('templates');
    templates = data.templates; components = data.components; roles = data.roles;
    $('template-gallery').innerHTML = templates.map((item, i) => `<article class="template-card"><span class="step">${String(i + 1).padStart(2, '0')} / ${escapeHTML(item.template.version)}</span><h2>${escapeHTML(item.template.name)}</h2><p>${escapeHTML(item.template.description)}</p><div class="component-tags">${item.template.components.map(c => `<span>${escapeHTML(c.name)}</span>`).join('')}</div><button data-template="${i}">Explore baseline →</button></article>`).join('');
    $('template-gallery').querySelectorAll('[data-template]').forEach(b => b.onclick = () => selectTemplate(templates[Number(b.dataset.template)].template, templates[Number(b.dataset.template)].sha256));
    $('component-catalog').innerHTML = components.map((c, i) => `<option value="${i}">${escapeHTML(c.name)} · ${escapeHTML(c.role)}</option>`).join('');
    $('component-role').innerHTML = roles.map(v => `<option>${escapeHTML(v)}</option>`).join('');
    templatesLoaded = true;
  }
  function selectTemplate(value, hash = null) {
    if (templateDirty && !confirm('Discard unsaved baseline changes?')) return;
    baseline = clone(value); baselineHash = hash; templateDirty = false;
    $('template-workbench').hidden = false;
    for (const key of ['name', 'id', 'version', 'description']) $('template-' + key).value = baseline[key];
    $('template-heading').textContent = baseline.name;
    $('template-decisions').value = (baseline.decisions || []).join('\n');
    $('template-files').value = JSON.stringify(baseline.files || {}, null, 2);
    $('template-status').textContent = hash ? 'Saved in private draft' : 'New draft';
    $('template-result').textContent = '';
    renderComponents();
    $('template-workbench').scrollIntoView({behavior:'smooth', block:'start'});
  }
  function readTemplate() {
    if (!baseline) throw new Error('Choose a baseline first.');
    const value = clone(baseline);
    for (const key of ['name', 'id', 'version', 'description']) value[key] = $('template-' + key).value.trim();
    value.decisions = lines($('template-decisions').value);
    try { value.files = JSON.parse($('template-files').value || '{}'); }
    catch (_) { throw new Error('Scaffold files must be a JSON object of paths and text.'); }
    return value;
  }
  function renderComponents() {
    $('template-components').innerHTML = baseline.components.map((c,i) => `<article class="component-item"><div><span class="step">${escapeHTML(c.role)}</span><h3>${escapeHTML(c.name)}</h3><p class="caption">${escapeHTML(c.reference || 'Version selected during implementation')}</p>${c.repository ? `<p class="component-link">${escapeHTML(c.repository)}</p>` : ''}</div><div class="button-row"><button data-edit-component="${i}" aria-label="Edit ${escapeHTML(c.name)}">Edit</button><button data-remove-component="${i}" aria-label="Remove ${escapeHTML(c.name)}">Remove</button></div></article>`).join('') || '<p class="muted">Add a component from the library, or define your own repository and setup guidance.</p>';
    $('template-components').querySelectorAll('[data-edit-component]').forEach(b => b.onclick = () => editComponent(Number(b.dataset.editComponent)));
    $('template-components').querySelectorAll('[data-remove-component]').forEach(b => b.onclick = () => { baseline.components.splice(Number(b.dataset.removeComponent), 1); changed(); renderComponents(); });
  }
  ['name','id','version','description','decisions','files'].forEach(key => $('template-' + key).oninput = changed);
  $('template-new').onclick = () => selectTemplate({schema_version:1, id:'my-baseline', name:'My project baseline', version:'1.0.0', description:'The starting point for my projects.', components:[], decisions:[], files:{}});
  window.useCapturedTemplate = value => { selectTemplate(value); changed(); };
  window.templateRevision = () => readTemplate();
  $('template-clone').onclick = safely(() => {
    const value = readTemplate(); value.id += '-copy'; value.name += ' · copy';
    templateDirty = false; selectTemplate(value); changed();
  });
  $('component-add').onclick = safely(() => {
    if (!baseline) return;
    const component = components[Number($('component-catalog').value)];
    if (baseline.components.some(c => c.id === component.id)) throw new Error('This component is already in the baseline. Edit it below.');
    baseline.components.push(clone(component)); changed(); renderComponents();
  });
  function editComponent(index) {
    $('component-dialog').querySelector('[data-studio-error]')?.remove();
    editingComponent = index;
    const value = index < 0 ? {id:'custom-component',name:'My component',role:'custom'} : baseline.components[index];
    for (const key of ['id','name','role','repository','reference','docs','instructions']) $('component-' + key).value = value[key] || '';
    for (const key of ['provides','requires','conflicts']) $('component-' + key).value = (value[key] || []).join(', ');
    $('component-checks').value = (value.checks || []).join('\n');
    $('component-env').value = (value.env || []).map(v => `${v.name} | ${v.secret ? 'secret' : 'public'} | ${v.purpose}`).join('\n');
    $('component-dialog').showModal();
  }
  $('component-new').onclick = () => editComponent(-1);
  $('component-cancel').onclick = () => $('component-dialog').close();
  $('component-form').onsubmit = safely(event => {
    event.preventDefault();
    const value = {};
    for (const key of ['id','name','role','repository','reference','docs','instructions']) value[key] = $('component-' + key).value.trim();
    for (const key of ['provides','requires','conflicts']) value[key] = comma($('component-' + key).value);
    value.checks = lines($('component-checks').value);
    value.env = lines($('component-env').value).map(line => {
      const [name, classification, ...purpose] = line.split('|').map(v => v.trim());
      if (!['secret','public'].includes(classification) || !purpose.length) throw new Error('Use NAME | secret or public | purpose for each variable.');
      return {name, secret: classification === 'secret', purpose: purpose.join(' | ')};
    });
    if (baseline.components.some((c,i) => c.id === value.id && i !== editingComponent)) throw new Error('Use a unique component identifier.');
    if (editingComponent < 0) baseline.components.push(value); else baseline.components[editingComponent] = value;
    changed(); renderComponents(); $('component-dialog').close();
  });
  function templateRequest(value) {
    // Renaming creates a new template, never overwrites another baseline implicitly.
    return {template:value, sha256:value.id === baseline.id ? baselineHash : null};
  }
  $('template-save').onclick = safely(async () => {
    const value = readTemplate(), body = templateRequest(value), plan = await call('template-preview', body);
    preview('Save this baseline', plan, 'Save to private library', async () => {
      await call('template-save', {...body, plan:plan.plan});
      templateDirty = false; await loadTemplates();
      const saved = templates.find(v => v.template.id === value.id); selectTemplate(saved.template, saved.sha256);
      filesLoaded = false; notice('Baseline saved in your private library.');
    });
  });
  $('template-apply-preview').onclick = safely(async () => {
    const body = {policy: $('template-follow-policy')?.value || (templateDirty || !baselineHash ? 'pinned' : 'latest'), template:readTemplate(), project:$('template-project').value.trim(), name:$('template-project-name').value.trim()};
    const plan = await call('project-preview', body);
    preview('Review project: ' + body.name, {...plan, note: plan.note + ' Architecture policy: ' + plan.policy + ' · revision ' + plan.revision.slice(0,12)}, 'Apply baseline to project', async () => {
      const result = await call('project-apply', {...body, plan:plan.plan});
      $('template-result').textContent = 'Applied. Open .ai/architecture-onboarding.md in this project and give it to your coding agent. ' + (result.snapshot ? 'Rollback snapshot: ' + result.snapshot : 'Files were already current.');
      notice('Project onboarded with the selected architecture. Dependencies have not been installed.');
    });
  });
  $('template-import').onclick = () => $('template-import-file').click();
  $('template-import-file').onchange = safely(async event => {
    const file = event.target.files[0]; if (!file) return;
    try {
      if (file.size > 256 * 1024) throw new Error('Choose a template smaller than 256 KiB.');
      const value = JSON.parse(await file.text());
      // Validate against the server before displaying any imported fields.
      await call('template-validate', {template:value});
      selectTemplate(value, templates.find(v => v.template.id === value.id)?.sha256 || null); changed();
    } finally { event.target.value = ''; }
  });
  $('template-export').onclick = safely(async () => {
    const value = readTemplate();
    await call('template-validate', {template:value});
    const href = URL.createObjectURL(new Blob([JSON.stringify(value,null,2) + '\n'], {type:'application/json'}));
    const link = document.createElement('a'); link.href = href; link.download = value.id + '.json'; link.click();
    setTimeout(() => URL.revokeObjectURL(href), 1000);
  });

  async function loadFiles() {
    const data = await call('files'); fileList = data.files; filesLoaded = true; renderFiles();
  }
  function renderFiles() {
    const search = $('library-filter').value.toLowerCase();
    const items = fileList.filter(v => v.path.toLowerCase().includes(search) && (!$('library-modified').checked || v.modified));
    $('library-count').textContent = items.length + ' files · local draft';
    $('library-files').innerHTML = items.map(v => `<button class="file-entry ${currentFile?.path === v.path ? 'selected' : ''}" data-file="${escapeHTML(v.path)}"><span>${escapeHTML(v.path)}</span><small>${v.modified ? 'CUSTOMIZED' : v.generated ? 'GENERATED' : v.editable ? 'EDITABLE' : 'VIEW'}</small></button>`).join('') || '<p class="caption">No matching files.</p>';
    $('library-files').querySelectorAll('[data-file]').forEach(b => b.onclick = safely(() => openFile(b.dataset.file)));
  }
  async function openFile(path, offset = 0) {
    if (fileDirty && !confirm('Discard unsaved file changes?')) return;
    const value = await call('file?path=' + encodeURIComponent(path) + '&offset=' + offset);
    currentFile = value; fileDirty = false;
    $('library-path').textContent = path;
    $('library-file-status').textContent = value.editable ? 'Private draft' : 'View only';
    $('library-file-note').textContent = value.editable ? 'Saving validates and rebuilds generated files. Following projects synchronize automatically; global client activation is separate.' : value.reason || 'Library image';
    $('library-editor').value = value.content || ''; $('library-editor').readOnly = !value.editable;
    $('library-editor').classList.toggle('prose-editor', /\.(md|mdc|txt)$/.test(path));
    $('library-editor-label').hidden = Boolean(value.image); $('library-image').hidden = !value.image;
    if (value.image) $('library-image').src = value.image;
    $('library-save').disabled = true; $('library-reload').disabled = false;
    $('library-next').hidden = value.next === null || value.next === undefined;
    $('library-previous').hidden = !value.offset;
    $('library-result').textContent = value.next || value.offset ? `Characters ${value.offset + 1}–${value.offset + value.content.length} of ${value.characters}` : '';
    renderFiles();
  }
  $('library-filter').oninput = renderFiles; $('library-modified').onchange = renderFiles;
  $('library-editor').oninput = () => { fileDirty = true; $('library-save').disabled = false; $('library-file-status').textContent = 'Unsaved changes'; };
  $('library-reload').onclick = safely(() => openFile(currentFile.path));
  $('library-next').onclick = safely(() => openFile(currentFile.path, currentFile.next));
  $('library-previous').onclick = safely(() => openFile(currentFile.path, Math.max(0, currentFile.offset - 64000)));
  $('library-save').onclick = safely(async () => {
    const body = {path:currentFile.path, sha256:currentFile.sha256, content:$('library-editor').value};
    const plan = await call('file-preview', body);
    preview('Review your instruction changes', plan, 'Save private draft', async () => {
      const result = await call('file-save', {...body,plan:plan.plan});
      fileDirty = false; await loadFiles(); await openFile(body.path); templatesLoaded = false;
      $('library-result').textContent = 'Draft saved. ' + (result.snapshot ? 'Rollback snapshot: ' + result.snapshot : 'No changes.');
      notice('Saved and validated. Following projects synchronize automatically while Local Control runs. Check Project sync for conflicts; global client activation remains separate.');
    });
  });
  $('library-activate').onclick = safely(async () => {
    if (fileDirty || templateDirty) throw new Error('Save or discard unsaved changes before activation.');
    const plan = await call('activation-preview', {});
    preview('Activate this instruction library', {note:'Updates enrolled, unpinned installations. Pinned projects keep their current bundle. Existing private policy overrides stay in effect. Verify loading in a fresh client session.', changes:[]}, 'Activate reviewed library', async () => {
      const result = await call('activate', {plan:plan.plan});
      notice('Library activated. ' + (result.snapshot ? 'Rollback snapshot: ' + result.snapshot + '. ' : '') + 'Open a fresh client session to verify instruction loading.');
    });
    $('studio-preview-body').innerHTML = `<p>Activate a checked, immutable copy of this draft. Existing private policy overrides remain in effect. Pinned projects are skipped.</p><p><strong>${plan.files.length} files will change.</strong></p>${plan.targets.map(v => `<p>${escapeHTML(v.target)} · ${escapeHTML(v.status)}</p>`).join('') || '<p>No enrolled installations yet. This sets the active library for future onboarding.</p>'}<details class="diff-file"><summary>Changed file paths</summary><pre>${escapeHTML(plan.files.join('\n'))}</pre></details><p class="caption">Activation updates instructions on disk. Verify loading in a fresh client session. It does not replace Local Control or switch running models.</p>`;
  });
  $('library-refresh').onclick = safely(async () => {
    if (fileDirty || templateDirty) throw new Error('Save or discard unsaved changes before refreshing the library.');
    const plan = await call('refresh-preview', {});
    preview('Bring your draft up to date', plan, 'Refresh unchanged files', async () => {
      await call('refresh-apply', {plan:plan.plan}); await loadFiles(); templatesLoaded = false;
      if (currentFile) await openFile(currentFile.path);
      notice('Private library refreshed from this application version. Review activation separately.');
    });
  });
  $('library-history').onclick = safely(async () => {
    const value = await call('history');
    preview('Your draft history', {changes:[]}, '', null);
    $('studio-preview-body').innerHTML = '<p>Undo a draft save or refresh. Later edits are protected; undo newer saves first. Project and activation snapshots use the CLI rollback command.</p>' + (value.snapshots.map(v => `<div class="history-row"><div><strong>${escapeHTML(v.snapshot)}</strong><p>${v.files} files · ${escapeHTML(v.state)}</p></div>${v.state === 'applied' ? `<button data-rollback="${escapeHTML(v.snapshot)}">Undo this save</button>` : ''}</div>`).join('') || '<p>No draft saves yet.</p>');
    $('studio-preview-body').querySelectorAll('[data-rollback]').forEach(b => b.onclick = safely(async () => {
      if (fileDirty || templateDirty) throw new Error('Save or discard unsaved changes before undoing a draft save.');
      if (!confirm('Restore the files from before this save? Later modifications will prevent rollback.')) return;
      await call('rollback', {snapshot:b.dataset.rollback}); await loadFiles(); templatesLoaded = false;
      if (currentFile && fileList.some(v => v.path === currentFile.path)) await openFile(currentFile.path);
      $('studio-preview').close(); notice('Draft save rolled back. Following projects receive the restored library on the next synchronization.');
    }));
  });
  window.studioPage = safely(async name => {
    if (name === 'architectures' && !templatesLoaded) await loadTemplates();
    if (name === 'constitution' && !filesLoaded) { await loadFiles(); if (!currentFile) await openFile('constitution.md'); }
  });
  window.addEventListener('beforeunload', event => { if (templateDirty || fileDirty) { event.preventDefault(); event.returnValue = ''; } });
})();
