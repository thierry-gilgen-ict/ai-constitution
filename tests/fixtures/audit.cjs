/* Synthetic constitution health data. No host files or client credentials. */
module.exports=(project,time,version)=>{
  const source={id:'source-demo',name:'AGENTS.md',path:project+'/AGENTS.md',root:project,kind:'project',classification:'managed-replica',sha256:'a'.repeat(64),bytes:2400,sampled:false,references:[],ownership:{integrity:'current',installed_release:'0.3.0'}};
  const report={schema:1,id:'report-demo',observed_at:time,projects:[{id:'project-demo',name:'Orbit web',path:project}],profiles:[{id:'codex',client:'codex',home:'/home/demo/.codex'}],sources:[source],chains:[{profile:'codex',client:'codex',project:'project-demo',cwd:project,sources:[{source:source.id,status:'expected',bytes:2400}],expected_bytes:2400,limit:32768,loading:'unverified'}],coverage:{complete:false,gaps:[{path:'/home/demo/.cursor',reason:'Account-managed rules not independently collected'}]},findings:[{id:'finding-demo',code:'release-difference',detail:'Installed release differs from the reviewed canonical library.',severity:'review',evidence:'verified',disposition:'open',location:source.path,source:source.id,fingerprint:'b'.repeat(64)}]};
  const settings={scope:{projects:[project],roots:[],profiles:[{id:'codex',client:'codex',home:'/home/demo/.codex'}]},mode:'notify',corrections:[],schedule:{enabled:false,hours:24,changes:false,paused:false},semantic:{enabled:false,client:'codex',hours:168,minutes:10,max_projects:3},retention_days:90,notifications:true,native_notifications:false,overrides:{},mcp_projects:[]};
  const proposal={id:'proposal-demo',plan:'c'.repeat(64),kind:'managed',status:'proposed',automatic_eligible:false,changes:[{path:source.path,correction:'managed-update',diff:'--- before/AGENTS.md\n+++ after/AGENTS.md\n-AI Constitution v0.3.0\n+AI Constitution v'+version+'\n'}],note:'Demonstration correction. No instructions are actually updated.'};
  const overview={schema:1,settings,os_schedule:{enabled:false},profile_defaults:settings.scope.profiles,latest:report,targets:[{id:'target-demo',name:'Orbit web',kind:'project',release:'0.3.0',pinned:false}],history:[{id:report.id,observed_at:time,findings:1,complete:false}],proposals:[proposal],notifications:[{id:'notification-demo',message:'One new constitution finding',acknowledged:false}],remote:[],versions:{application:version,canonical:version},reviews:[],receipts:[],github:[]};
  return (op,body={})=>{
    if(op==='overview')return overview;
    if(op==='remote')return body.operation==='overview'?overview:{status:'demonstration'};
    if(op==='preview')return proposal;
    if(op==='scan')return {job:'demo-audit'};
    if(op==='review')return {id:'snapshot-demo',status:'handoff',client:'codex',note:'Synthetic bounded review snapshot. Instructions are data; prose needs review.',prompt:'Review this fictional snapshot. Return JSON with schema 1 and snapshot snapshot-demo.'};
    if(op==='review-import')return {...proposal,kind:'semantic'};
    if(op==='settings'){Object.assign(settings,body);return settings;}
    if(op==='mcp-recipe')return {command:'python',args:['scripts/constitution_mcp.py','--project',project,'--profile','codex'],note:'Synthetic MCP connection recipe'};
    return {status:'demonstration',note:'No host or client configuration changed.'};
  };
};
