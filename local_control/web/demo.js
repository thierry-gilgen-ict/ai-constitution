/* No imports, fetch, storage, native launch, or production API access. */
const content=document.getElementById('demo-content'),status=document.getElementById('demo-status');
function reset(){
  status.textContent='';
  content.innerHTML='<article class="panel"><span class="pill">Example project</span><h2>Orbit website</h2><p>Instructions installed · client loading not yet verified · backup configured</p><button id="demo-launch">Simulate opening a project</button><button id="demo-review">Review an example change</button></article><article class="panel"><h2>Studio computer</h2><p>One fictional local model. Memory values are illustrations, not benchmarks.</p><button id="demo-gpu">Simulate freeing GPU memory</button></article>';
  document.getElementById('demo-launch').onclick=()=>status.textContent='Simulation: a new coding session would open using the client’s existing login. No application was launched.';
  document.getElementById('demo-gpu').onclick=()=>status.textContent='Simulation: fallback checked → response completed → model unloaded → release verified. Your GPU was not accessed.';
  document.getElementById('demo-review').onclick=()=>{status.replaceChildren();const heading=document.createElement('h2');heading.textContent='Example: add a verification rule';const text=document.createElement('p');text.textContent='Affected project: Orbit website. Takes effect after publication and a fresh client session. Recovery: restore the previous owned file if later edits permit.';const diff=document.createElement('pre');diff.textContent='+ Run the project’s documented checks before reporting completion.';const apply=document.createElement('button');apply.textContent='Apply simulated change';apply.onclick=()=>status.textContent='Example applied in memory. No real files changed.';status.append(heading,text,diff,apply);};
}
document.getElementById('demo-reset').onclick=reset;reset();
