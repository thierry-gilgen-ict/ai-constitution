/* Claude controls use the same reviewed workflows as the other clients. */
(() => {
  const e=escapeHTML;
  const call=(op,body)=>api('/api/claude/'+op,body);
  const ui=()=>window.centerUI;
  async function open(){
    if($('audit-machine')?.value && $('audit-machine').value!=='local'){
      ui().modal('Worker-owned Claude setup','<p>Claude profiles, sign-in and execution settings belong to the worker owner. Use Worker setup for grants, then run the documented claude-config commands on that computer. Switch Computer to This computer for this controller’s Claude settings.</p>',null,null);return;
    }
    const v=await call('overview'),{modal,field,options,safe,done}=ui();
    const check=(id,label,value)=>`<label class="check"><input id="${id}" type="checkbox" ${value?'checked':''}>${e(label)}</label>`;
    modal('Claude Code workspace',`<p><span class="pill">${e(v.client.status)}</span> Client ${e(v.client.version||'version unknown')}</p><p>${e(v.note)}</p><p>Sign-in: ${e(v.usage.account?.email||v.usage.status||'Unknown')} · subscription allowance unknown</p>${field('claude-project','Project directory')}
      <label>Claude profile<select id="claude-profile">${options(v.profiles.map(p=>[p.id,p.id+' · '+p.home]))}</select></label>
      <div class="button-row"><button type="button" id="claude-enroll">Preview project onboarding</button><button type="button" id="claude-hosted">Hosted launch command</button><button type="button" id="claude-local">Local launch command</button><button type="button" id="claude-collect">Refresh sign-in</button></div>
      <p><a href="https://code.claude.com/docs/en/setup" target="_blank" rel="noopener noreferrer">Installation instructions</a> · Update the native client in your terminal with <code>claude update</code>. Restart your own session to verify its new version.</p>
      <h3>Local model compatibility</h3><p>These tests send local inference. Qualify each configured route before using Claude. Active responses finish before model maintenance.</p>
      <div class="button-row"><button type="button" id="claude-primary">Test primary Messages route</button><button type="button" id="claude-fallback">Test fallback Messages route</button></div>
      <h3>Private monitoring and reviews</h3>${check('claude-monitor','Collect supported local sign-in status',v.settings.monitoring)}${check('claude-telemetry','Collect aggregate metrics from managed launches',v.settings.telemetry)}${check('claude-share','Share Claude account observations with paired controllers',v.settings.share)}${check('claude-auto','Enable isolated API/local reviews',v.settings.automated_reviews)}${field('claude-key-env','API key environment variable name (optional)',v.settings.api_key_env||'')}
      <p>Subscription reviews use Constitution health → Review. Isolated reviews require separate API/local setup and still produce a diff for approval.</p><button type="button" id="claude-review-cancel">Cancel isolated review</button><p id="claude-message" role="status"></p>`,'Save Claude preferences',async()=>{
        done(await call('settings',{monitoring:$('claude-monitor').checked,telemetry:$('claude-telemetry').checked,share:$('claude-share').checked,automated_reviews:$('claude-auto').checked,api_key_env:$('claude-key-env').value||null}));
      });
    $('claude-enroll').onclick=safe(async()=>{
      const project=$('claude-project').value,preview=await call('enroll-preview',{project});
      modal('Review Claude onboarding',`<p>Existing guidance outside the managed block is preserved. This enables Claude explicitly.</p>${preview.diffs.map(d=>`<h3>${e(d.path||'Instruction changes')}</h3><pre>${e(typeof d==='string'?d:d.diff||JSON.stringify(d,null,2))}</pre>`).join('')}`,'Apply reviewed onboarding',async()=>done(await call('enroll-apply',{project,plan:preview.plan})));
    });
    for(const role of ['primary','fallback'])$('claude-'+role).onclick=safe(async()=>done(await call('qualify',{role})));
    $('claude-review-cancel').onclick=safe(async()=>done(await call('review-cancel',{})));
    $('claude-collect').onclick=safe(async()=>done(await call('collect',{profile:$('claude-profile').value})));
    for(const mode of ['hosted','local'])$('claude-'+mode).onclick=safe(async()=>{
      const v=await call('launch-command',{project:$('claude-project').value,profile:$('claude-profile').value,mode});
      modal('Start a fresh Claude session',`<p>Run this on the owning computer. Current tasks and persistent hosted credentials are preserved.</p><pre>${e(v.command)}</pre><button type="button" id="claude-copy">Copy command</button>`,null,null);
      $('claude-copy').onclick=safe(async()=>navigator.clipboard.writeText(v.command));
    });
  }
  document.addEventListener('click',event=>{if(event.target.closest('#audit-claude'))ui().safe(open)();});
  window.claudeReview=async snapshot=>{
    const {modal,options,done}=ui();
    modal('Run an isolated Claude review','<p>This uses separately configured API credentials or a qualified local model. Subscription login is not used. Tools, MCP and hooks are disabled; resulting edits still require diff approval.</p><label>Execution<select id="claude-review-mode">'+options([['api','Configured API'],['local','Qualified local model']])+'</select></label>','Run isolated review',async()=>done(await call('review',{snapshot,execution:$('claude-review-mode').value})));
  };
})();
