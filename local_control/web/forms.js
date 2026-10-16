/* Structured edits round-trip the full document, including fields not shown here. */
const e=value=>escapeHTML(value);
const layouts={
  'toolkit-editor':{title:'Toolkit',fields:['id','name','version'],arrays:{rules:['id','description','content'],skills:['id','description','content'],commands:['id','description','content'],mcp:['id','url','command','args']}},
  'prepare-recipe':{title:'Preparation recipe',fields:['id','name','environment'],arrays:{steps:['id','kind','argv','cwd','url','timeout']}}
};
function input(key,value,path) {
  const label={id:'Identifier',name:'Name',version:'Version',environment:'Environment names · one per line',description:'Description',content:'Instructions',url:'URL',command:'Executable',args:'Arguments · one per line',argv:'Command and arguments · one per line',kind:'Step type',cwd:'Working directory · relative to project (command steps)',timeout:'Timeout in seconds',platform:'Coding application',task:'Task intent',preferred:'Preferred model selector',fallbacks:'Fallback selectors · one per line',note:'Routing guidance'}[key]||key;
  const attr=`data-form-path="${e(path.join('/'))}"`;
  if(key==='kind')return `<label>${label}<select ${attr}>${['venv','python-install','npm-install','compose-up','command','http'].map(v=>`<option ${v===value?'selected':''}>${v}</option>`).join('')}</select></label>`;
  if(['content','environment','args','argv','fallbacks','note'].includes(key))return `<label>${label}<textarea ${attr} rows="3">${e(Array.isArray(value)?value.join('\n'):value||'')}</textarea></label>`;
  return `<label>${label}<input ${attr} ${key==='timeout'?'type="number" min="1" max="1800"':''} value="${e(value??'')}"></label>`;
}
function enhance(editor,layout) {
  if(editor.dataset.structured)return;
  editor.dataset.structured='true';
  const label=editor.closest('label'),details=document.createElement('details'),host=document.createElement('section');
  details.innerHTML='<summary>Advanced JSON · all fields preserved</summary>';label.before(host,details);details.append(label);
  const get=()=>JSON.parse(editor.value);
  const put=value=>{window.trackEditorBaseline?.(editor);editor.value=JSON.stringify(value,null,2);editor.dispatchEvent(new Event('input',{bubbles:true}));};
  const draw=()=>{
    let data;try{data=get();}catch{host.textContent='Correct the advanced JSON to use the form editor.';details.open=true;return;}
    host.className='structured-fields';
    host.innerHTML=`<h3>${e(layout.title)}</h3><p class="caption">Changes are validated when you preview or save. Commands are never executed by this editor.</p><div class="studio-fields">${layout.fields.map(k=>input(k,data[k],[k])).join('')}</div>`+Object.entries(layout.arrays).map(([key,fields])=>`<fieldset><legend>${e(key)}</legend>${(data[key]||[]).map((row,i)=>`${key==='routes'?'<details class="form-row"><summary>'+e(row.platform)+' · '+e(row.task)+'</summary>':'<article class="form-row">'}<div class="studio-fields">${fields.filter(k=>key!=='steps'||k!=='argv'&&k!=='url'&&k!=='cwd'||['argv','cwd'].includes(k)&&row.kind==='command'||k==='url'&&row.kind==='http').map(k=>input(k,row[k],[key,i,k])).join('')}</div><div class="button-row"><button type="button" data-up="${key}/${i}" ${i===0?'disabled':''}>Move up</button><button type="button" data-remove-row="${key}/${i}">Remove ${e(key==='steps'?'step':'entry')}</button></div>${key==='routes'?'</details>':'</article>'}`).join('')}<button type="button" data-add-row="${key}">Add ${e(key==='steps'?'step':'entry')}</button></fieldset>`).join('');
    host.querySelectorAll('[data-form-path]').forEach(el=>el.onchange=()=>{
      try {
        const value=get(),path=el.dataset.formPath.split('/'),key=path.pop();let target=value;
        for(const part of path)target=target[part];
        target[key]=['environment','args','argv','fallbacks'].includes(key)?el.value.split('\n').map(v=>v.trim()).filter(Boolean):key==='timeout'?Number(el.value):el.value;
        if(key==='kind'){if(el.value!=='command'){delete target.argv;delete target.cwd;}if(el.value!=='http')delete target.url;}
        if(!el.value && ['url','command','timeout','cwd'].includes(key))delete target[key];
        put(value);if(key==='kind')draw();
      }catch{notice('The advanced document is invalid. Correct it before using the form.',true);}
    });
    host.querySelectorAll('[data-add-row]').forEach(b=>b.onclick=()=>{const value=get(),key=b.dataset.addRow;value[key]||=[];value[key].push(key==='steps'?{id:'step-'+(value[key].length+1),kind:'command',argv:['python','--version'],timeout:300}:key==='routes'?{platform:'codex',task:'small',description:'',preferred:'codex:fast',fallbacks:[],note:''}:key==='mcp'?{id:'connection-'+(value[key].length+1),url:''}:{id:'entry-'+(value[key].length+1),description:'',content:''});put(value);draw();});
    host.querySelectorAll('[data-remove-row]').forEach(b=>b.onclick=()=>{const [key,index]=b.dataset.removeRow.split('/'),value=get();value[key].splice(+index,1);put(value);draw();});
    host.querySelectorAll('[data-up]').forEach(b=>b.onclick=()=>{const [key,index]=b.dataset.up.split('/'),value=get(),i=+index;[value[key][i-1],value[key][i]]=[value[key][i],value[key][i-1]];put(value);draw();});
  };
  editor.addEventListener('change',draw);draw();
  return ()=>{editor.removeEventListener('change',draw);details.before(label);host.remove();details.remove();delete editor.dataset.structured;};
}
export function installForms() {
  let clearRoute;document.addEventListener('workspace-library-file',event=>{clearRoute?.();clearRoute=null;if(event.detail.path==='registry/routes.json')clearRoute=enhance($('library-editor'),{title:'Routing preferences',fields:[],arrays:{routes:['platform','task','description','preferred','fallbacks','note']}});});
  document.addEventListener('workspace-modal',()=>{
    for(const [id,layout] of Object.entries(layouts)){const editor=document.getElementById(id);if(editor)enhance(editor,layout);}
  });
}


// Only validated toolkit/recipe documents can be persisted; other form values stay in memory.
export function installEditGuards() {
  const originals=new Map(); let approvedClose=false;
  const value=el=>el.type==='checkbox'||el.type==='radio'?String(el.checked):el.value;
  const eligible=el=>el?.matches?.('input:not([type=search]),textarea,select') && !el.readOnly && !el.disabled && !el.closest('#workspace-palette,#editor-leave-dialog') && el.id!=='library-editor' && !el.closest('#template-workbench');
  const track=event=>{const el=event.target;if(eligible(el)&&!originals.has(el))originals.set(el,value(el));};
  document.addEventListener('focusin',track,true);
  window.trackEditorBaseline=el=>track({target:el});
  const dirty=()=>[...originals].filter(([el,v])=>el.isConnected&&el.closest('.page.active,dialog[open]')&&value(el)!==v);
  window.workspaceUnsaved=()=>Boolean(window.studioUnsaved?.()||dirty().length);
  window.acceptEditorChanges=(root=document)=>{for(const [el] of originals)if(!el.isConnected||root.contains(el))originals.delete(el);};
  window.saveDocumentDraft=async editor=>{
    const info=editor.dataset.editorKind,context=editor.dataset.editorContext||'library';
    if(!info)throw new Error('This form cannot store private drafts. Save through its owning workflow.');
    const result=await api('/api/ui/editor-save',{kind:info,context,document:JSON.parse(editor.value),revision:editor.dataset.draftRevision||undefined});
    editor.dataset.draftRevision=result.revision;window.acceptEditorChanges(editor.closest('dialog')||editor.parentElement);notice(result.note);
  };
  window.confirmWorkspaceNavigation=async(scope=document)=>{
    const scopedDirty=()=>dirty().filter(([el])=>scope.contains(el));const studio=scope===document;
    if(!(studio&&window.studioUnsaved?.())&&!scopedDirty().length)return true;
    let dialog=document.getElementById('editor-leave-dialog');
    if(!dialog){dialog=document.createElement('dialog');dialog.id='editor-leave-dialog';document.body.append(dialog);}
    const editor=document.querySelector('#center-dialog[open] textarea[data-editor-kind]');
    const canSave=Boolean(editor||studio&&window.studioUnsaved?.());
    dialog.innerHTML='<h2>Keep your edits?</h2><p>Leaving this view would discard unsaved form changes.</p>'+(editor?'<p>Save draft keeps the validated document only. Operational choices such as retry approval are never saved as authorization.</p>':'')+'<p id="editor-leave-error" role="alert"></p><div class="button-row">'+(canSave?'<button id="editor-leave-save">Save draft and continue</button>':'')+'<button id="editor-leave-discard">Discard edits</button><button id="editor-leave-stay" autofocus>Stay here</button></div>';
    dialog.showModal();
    return new Promise(resolve=>{
      let answered=false;
      const finish=ok=>{answered=true;dialog.close();if(ok){window.acceptEditorChanges(scope);approvedClose=true;$('center-dialog').close();approvedClose=false;}resolve(ok);};
      $('editor-leave-stay').onclick=()=>finish(false);
      $('editor-leave-discard').onclick=()=>{for(const [el,v] of scopedDirty()){if(el.type==='checkbox'||el.type==='radio')el.checked=v==='true';else el.value=v;}if(studio)window.discardStudioEdits?.();finish(true);};
      if(canSave)$('editor-leave-save').onclick=async()=>{try{if(editor)await window.saveDocumentDraft(editor);if(studio&&window.studioUnsaved?.())await window.saveStudioDraft();finish(true);}catch(error){$('editor-leave-error').textContent=error.message;}};
      dialog.oncancel=event=>{event.preventDefault();finish(false);};
      dialog.onclose=()=>{if(!answered)resolve(false);};
    });
  };
  const close=async event=>{if(approvedClose)return;event.preventDefault();if(await window.confirmWorkspaceNavigation($('center-dialog')))$('center-dialog').close();};
  $('center-dialog-close').onclick=close;$('center-dialog').addEventListener('cancel',close);
  document.addEventListener('workspace-modal',async()=>{
    window.acceptEditorChanges($('center-dialog'));
    const editor=$('toolkit-editor')||$('prepare-recipe');if(!editor)return;
    editor.dataset.editorKind=editor.id==='toolkit-editor'?'toolkit':'preparation';
    editor.dataset.editorContext=editor.id==='prepare-recipe'?window.preparationContext:'library';
    const bar=document.createElement('div');bar.className='button-row';
    bar.innerHTML='<button type="button" data-save-editor>Save private draft</button><button type="button" data-restore-editor hidden>Restore saved draft</button><button type="button" data-discard-editor hidden>Delete saved draft</button><span role="status"></span>';
    $('center-dialog-body').prepend(bar);
    bar.querySelector('[data-save-editor]').onclick=window.centerUI.safe(()=>window.saveDocumentDraft(editor));
    try{
      const saved=await api('/api/ui/editor-draft',{kind:editor.dataset.editorKind,context:editor.dataset.editorContext});
      if(!editor.isConnected)return;
      editor.dataset.draftRevision=saved.revision||'';
      if(saved.draft){const restore=bar.querySelector('[data-restore-editor]');restore.hidden=false;restore.onclick=()=>{window.trackEditorBaseline(editor);editor.value=JSON.stringify(saved.draft.document,null,2);editor.dispatchEvent(new Event('change'));bar.querySelector('span').textContent='Private draft restored for review. Nothing was applied.';};const discard=bar.querySelector('[data-discard-editor]');discard.hidden=false;discard.onclick=window.centerUI.safe(async()=>{await api('/api/ui/editor-discard',{kind:editor.dataset.editorKind,context:editor.dataset.editorContext,revision:editor.dataset.draftRevision});editor.dataset.draftRevision='';restore.hidden=discard.hidden=true;bar.querySelector('span').textContent='Saved candidate deleted. Current form contents are unchanged.';});}
    }catch(error){bar.querySelector('span').textContent=error.message;}
  });
  window.addEventListener('beforeunload',event=>{if(window.workspaceUnsaved()){event.preventDefault();event.returnValue='';}});
}
