/* Bounded reads only. Never retry an uncertain mutation. */
let failures = 0, timerHandle, inFlight=false;
export async function request(path, body, headers = {}) {
  const controller = new AbortController();
  const timer = body === undefined || path === '/api/login' ? setTimeout(() => controller.abort(), 8000) : null;
  try {
    const response = await fetch(path, {method: body === undefined ? 'GET' : 'POST', credentials:'same-origin',
      signal: controller.signal, headers:{'Content-Type':'application/json', ...headers},
      ...(body === undefined ? {} : {body:JSON.stringify(body)})});
    let data;
    try { data = await response.json(); } catch { const error=new Error('The service returned an unreadable response. Reload the application or inspect Activity.');error.kind='application';throw error; }
    if (!response.ok) { const error = new Error(data.error || 'Request failed'); error.status = response.status; error.problem=data.problem; throw error; }
    return data;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('The service did not answer within eight seconds. Last-known values may be stale.');
    throw error;
  } finally { clearTimeout(timer); }
}
export function connection(kind, detail = '') {
  const labels = {starting:'Starting', connected:'Connected locally', signin:'Sign-in required', disconnected:'Disconnected · values stale', incompatible:'Update required', error:'Application error'};
  document.getElementById('connection').textContent = labels[kind] || kind;
  document.documentElement.dataset.connection = kind;
  if (detail) notice(detail, kind !== 'connected');
}
export async function start() {
  connection('starting');
  const token = location.hash.slice(1);
  if (token) {
    history.replaceState(null, '', location.pathname + location.search);
    try { await request('/api/login', {}, {Authorization:'Bearer '+token}); }
    catch(error) { connection(error.status === 401 ? 'signin' : 'disconnected', error.message);if(error.status===401&&!$('login').open)$('login').showModal(); }
  }
  async function tick() {
    if(inFlight)return;
    inFlight=true;
    try {
      if (document.documentElement.dataset.connection === 'signin') return;
      state = await request('/api/status'); authorized = true;
      renderState(); failures = 0; connection('connected');
      if (!window.uiBootstrap) {
        const bootstrap = await request('/api/ui/bootstrap');
        if (bootstrap.ui_protocol !== 1) { connection('incompatible','Reload the dashboard to use this application version.'); return; }
        window.uiBootstrap = bootstrap;
        document.dispatchEvent(new CustomEvent('workspace-ready'));
      }
      if(state.application_version && state.application_version!==window.uiBootstrap.version){
        connection('incompatible','The application was updated. Save your drafts before reloading.');
        document.dispatchEvent(new CustomEvent('workspace-version-changed'));
      }
      document.dispatchEvent(new CustomEvent('workspace-status'));
    } catch(error) {
      ++failures;
      if (error.status === 401) {
        authorized = false; connection('signin','Use the AI Constitution desktop shortcut to open authenticated access.');
        if (!$('login').open) $('login').showModal();
      } else connection(error.kind==='application'?'error':'disconnected',error.message+' Use the desktop launcher if the service has stopped.');
    } finally {
      inFlight=false;clearTimeout(timerHandle);
      timerHandle=setTimeout(tick, Math.min(30000, failures ? 2000 * 2 ** Math.min(failures,4) : document.hidden ? 15000 : 3000));
    }
  }
  $('refresh').onclick = () => { connection('starting'); if ($('login').open) $('login').close();clearTimeout(timerHandle);tick(); };
  await tick();
}
