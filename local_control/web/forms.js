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
  const put=value=>{editor.value=JSON.stringify(value,null,2);editor.dispatchEvent(new Event('input',{bubbles:true}));};
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
