/* Public demonstration data. Serves no host files, accounts, models or credentials. */
const fs = require('node:fs');
const path = require('node:path');
const ROOT = path.resolve(__dirname, '../..');
const VERSION = fs.readFileSync(path.join(ROOT, 'VERSION'), 'utf8').trim();
const NOW = Date.parse('2026-10-03T12:00:00Z');
const TIME = NOW / 1000;
const HOME = '/home/demo';
const PROJECT = HOME + '/projects/orbit-web';
const clone = value => JSON.parse(JSON.stringify(value));
const read = file => JSON.parse(fs.readFileSync(path.join(ROOT, file), 'utf8'));

function fixture(scenario = 'ready') {
  const templates = ['web-product', 'data-dashboard', 'python-api'].map(id => ({
    template: read('templates/architectures/' + id + '.json'), sha256: 'demo-revision',
    review: {errors: [], warnings: [], evidence: 'Demonstration baseline. Review dependencies before implementation.'},
  }));
  const review = {errors: [], warnings: [], evidence: 'Demonstration preview; no project files are changed.'};
  const change = {path: '.ai/architecture.md', status: 'create', diff: '+ # Orbit web architecture\n+ Authentication: Better Auth\n+ Email: Resend\n+ Development services: Docker Compose\n'};
  const plan = {plan: 'demonstration-preview', review, changes: [change], conflicts: [], note: 'Review the managed files before applying. Existing guidance is preserved.', policy: 'pinned', revision: 'a1b2c3d4e5f6'};
  const route = {node: 'local', model: 'demo-coder:7b', source_model: 'demo-coder:7b', cpu: false, contract: {level: 'coding-tested'}};
  const fallback = {...route, node: 'work-pc', model: 'demo-coder:3b', source_model: 'demo-coder:3b'};
  const failure = {id: 'demo-backup-failure', label: 'Scheduled configuration backup', operation: 'scheduled', status: 'failed', created_at: TIME - 3600, detail: 'Backup destination is unavailable. Check storage, then preview and retry.', occurrences: 2};
  const state = {nodes: {local: {name: 'Studio PC · demonstration', kind: 'ollama', url: 'http://127.0.0.1:11434'}, 'work-pc': {name: 'Work PC · demonstration', kind: 'worker', url: 'https://192.168.50.20:8767', gaming_eligible: true}},
    primary: route, fallback, fallbacks: [], mode: 'work', phase: 'idle', active_requests: 0, queued_requests: 0, waiting_requests: [],
    sessions: [], jobs: [], events: [{time: '12:00:00', message: 'Demonstration primary and fallback configured.'}], notifications: [], service_errors: [],
    alias: 'constitution-local', context: 8192, managed: {}, maintenance: [], driver_paused: [], routing_policy: 'configured', task_profile: 'deep', automatic_fallback: true,
    permissions: 'Demonstration state only; no personal files are read',
    health: {local: {status: 'online', version: 'example', checked_at: TIME}, 'work-pc': {status: 'online', version: 'example', checked_at: TIME}},
    health_history: [{node: 'local', status: 'online', checked_at: TIME}], drivers: {}};
  const driver = {status: 'ok', platform: 'Windows', os_version: '11 · example', checked_at: TIME, source: 'Synthetic driver inventory',
    adapters: [{name: 'Demonstration graphics adapter', vendor: 'Example vendor', version: '1.2.3.4', date: '2026-09-01'}],
    note: 'Example data illustrates version visibility; it does not establish driver compatibility.',
    updates: {status: 'not-checked', note: 'Review official update controls on the selected computer.'},
    actions: [{id: 'windows-update', label: 'Windows Update', detail: 'Open the selected machine’s native update controls after all model clients are idle.'}]};
  state.drivers = {local: driver, 'work-pc': {...driver, actions: clone(driver.actions)}};
  const inventory = {version: 'example', models: [{name: 'demo-coder:7b', size: 4 * 1024**3, details: {quantization_level: 'Q4_K_M'}}, {name: 'demo-coder:3b', size: 2 * 1024**3, details: {quantization_level: 'Q4_K_M'}}],
    running: [{name: 'demo-coder:7b', size_vram: 5 * 1024**3, context_length: 8192}]};
  const account = {id: 'demo-subscription', label: 'Development subscription · example', login: 'demo@example.com', plan: 'Demonstration plan', provider: 'openai', application: 'Codex', machine: 'Studio PC', projects: [PROJECT], subscription_key: 'demonstration-identity',
    usage: [{used: 42, limit: 100, unit: 'percent', period: 'Example billing period', observed_at: TIME, source: 'Demonstration observation', model: 'Example model'}], connector: {id: 'openai-api', key_env: 'EXAMPLE_ADMIN_KEY'},
    report: {status: 'available', observed_at: TIME, scope: 'Demonstration API organization costs', daily: [{date: '2026-10-03', amount: '1.25', currency: 'USD'}]}};
  const observation = {status: 'available', login: account.login, plan: account.plan, observed_at: TIME, source: 'Synthetic report · no subscription queried', windows: [{bucket: 'Example allowance', window: 'primary', duration_minutes: 300, used_percent: 42, resets_at: TIME + 7200}], daily: [{date: '2026-10-02', tokens: 25000}, {date: '2026-10-03', tokens: 18000}]};
  const local = {schema: 1, codex_enabled: true, accounts: {[account.id]: account}, observations: {codex: observation},
    provider_links: {openai: 'https://platform.openai.com'}, alerts: [], note: 'All accounts and measurements in this documentation example are fictional.',
    events: [{time: TIME, target: account.id, status: 'available', code: 'demonstration_report'}],
    connectors: [{id: 'codex', scope: 'Local CLI profile', permission: 'Explicit local opt-in'}, {id: 'openai-api', scope: 'API organization costs', permission: 'Existing admin key environment variable'}, {id: 'manual/import', scope: 'Other subscriptions', permission: 'User supplied observations'}]};
  const workspace = {enabled: true, checked_at: TIME, scope: 'Enrolled repositories on this controller.', runtime: 'Following projects receive shared changes; local edits are protected.', projects: [{project: PROJECT, status: 'current', machine: 'Studio PC · demonstration', template: 'web-product', architecture: {id: 'web-product', version: '1.0.0', policy: 'latest'}, accounts: [account], configurations: [{folder: HOME + '/.config/orbit-web'}], backup: {configured: true, last_success: TIME - 1800}, route: {mode: 'work', applies: 'Managed Local Control sessions'}, paused: false, pinned: false}]};
  const vault = {config_root: HOME + '/.config', backup_root: HOME + '/backups/configuration', schedule: {enabled: true, hours: 24}, last_success: TIME - 1800, next_due: TIME + 84600,
    projects: {'orbit-web': {name: 'Orbit web', folder: HOME + '/.config/orbit-web', project: PROJECT}}, warnings: [], available_folders: [{name: 'orbit-web', path: HOME + '/.config/orbit-web'}],
    snapshots: [{id: 'snapshot-20261003T113000Z-abcdef01', created: TIME - 1800, projects: ['orbit-web'], files: 3, bytes: 2048}], note: 'Example mappings and snapshots. No environment values are displayed.'};
  const updates = {current: VERSION, latest: '99.0.0', available: true, automatic_check: true, checked_at: TIME, notes: 'DEMONSTRATION RELEASE\nExample changes illustrate the update review. This is not an announcement of a published version.', url: 'https://github.com/thierry-gilgen-ict/ai-constitution/releases', previous: {version: '0.2.0'}};
  const inbox = {status: 'review', changes: [{provider: 'example-provider', model: 'example-coder', kind: 'added', fields: {tool_call: {before: null, after: true}, limit: {before: null, after: {context: 32768}}}}], summary: {models_added: ['example-coder'], models_removed: [], models_changed: []}, plan: 'demonstration-preview', route_impact: [{id: 'example-route', preferred: 'Review preferred model deliberately'}], note: 'Synthetic catalog change. Definitions, account access and measured performance are separate.'};
  const profiles = [{node: 'Studio PC · demonstration', model: 'demo-coder:7b', context: 8192, count: 3, passed: 3, level: 'coding-tested', first_text_seconds: 0.8, tokens_per_second: 24, resident_gpu_bytes: 5 * 1024**3, memory: {samples: 4, peak_gpu_bytes_sampled: 5 * 1024**3}, note: 'Synthetic measurements for documentation. Not a model or hardware benchmark.'}, {node: 'Work PC · demonstration', model: 'demo-coder:3b', context: 8192, count: 2, passed: 2, level: 'coding-tested', first_text_seconds: 1.4, tokens_per_second: 16, resident_gpu_bytes: 3 * 1024**3, memory: {samples: 4}, note: 'Synthetic measurements for documentation.'}];
  if (scenario === 'gaming') { state.mode = 'gaming'; inventory.running = []; state.events = [{time: '12:00:00', message: 'Demonstration: fallback selected; protected GPU released.'}]; }
  if (scenario === 'draining') { state.mode = 'draining'; state.phase = 'waiting for active responses'; state.active_requests = 1; }
  if (scenario === 'failure') { state.jobs = [failure]; state.notifications = [failure]; }
  if (scenario === 'conflict') { workspace.projects[0].status = 'conflict'; workspace.projects[0].detail = 'Managed instructions were edited locally. Review the diff before retrying synchronization.'; }
  if (scenario === 'empty') { workspace.projects = []; inventory.models = []; inventory.running = []; profiles.length = 0; }
  if (scenario === 'staged' || scenario === 'blocked') updates.staged = {version: '99.0.0'};
  if (scenario === 'collector-failed') { local.observations.codex = {status: 'unavailable', last_successful: observation}; local.alerts = [{message: 'Refresh failed. The last successful demonstration report is retained.'}]; }
  let authorized = scenario !== 'login';
  const schedule = {enabled: true, hours: 24, scope: 'Example per-user OS task'};
  const encrypted = {enabled: true, installed: true, repository: HOME + '/backups/encrypted', password_file: HOME + '/private/restic-password', password_env: 'EXAMPLE_BACKUP_PASSWORD', tag: 'demonstration-only', keep_last: 10, docs: 'https://restic.readthedocs.io/en/stable/020_installation.html', note: 'Example encrypted backup configuration. No password is read or shown.'};
  const diagnostics = {schema: 1, version: VERSION, mode: state.mode, active_requests: state.active_requests, nodes: [{name: 'Demonstration worker', health: 'online'}], note: 'Synthetic allowlisted report. No credentials, prompts or personal paths.'};
  const paths = {models: HOME + '/models/ollama', studio: HOME + '/.config/ai-constitution/library', downloads: HOME + '/downloads/ai-constitution', configuration: HOME + '/.config/ai-constitution/local-control', constitution_state: HOME + '/.config/ai-constitution/state'};
  function response(url, method, body = {}) {
    const parsed = new URL(url, 'http://127.0.0.1'); const p = parsed.pathname;
    if (p === '/api/login') { authorized = true; return {}; }
    if (!authorized) return {__status: 401, error: 'Open the authenticated dashboard from your terminal.'};
    if (p.startsWith('/api/workflows/')) return require('./workflows.cjs')(workspace,TIME)(p.replace('/api/workflows/',''),body);
    if (p === '/api/status') return state;
    if (p === '/api/version') return {version: VERSION, protocol: 2};
    if (p === '/api/inventory') return inventory;
    if (p === '/api/hardware') return {system: {gpu_name: 'Demonstration GPU · 16 GB', gpu_vram_gb: 16, total_ram_gb: 32, cpu_name: 'Demonstration CPU'}};
    if (p === '/api/setup') return {inventory, context: 8192, ollama: true, llmfit: true, disk_free_bytes: 250 * 1024**3, primary_ready: true, fallback_ready: true};
    if (p === '/api/context-advice') return {suggested: 8192, reason: 'Demonstration estimate; validate on your hardware.'};
    if (p === '/api/recommendations') return {context: 8192, note: 'Synthetic fit estimates for documentation. Read the actual model card and license.', models: [{name: 'example/demo-coder', best_quant: 'Q4_K_M', memory_required_gb: 5.5, estimated_tps: 24, fit_label: 'example', license: 'Check model card'}]};
    if (p === '/api/hf/search') return [{id: 'example/demo-coder-GGUF', url: 'https://huggingface.co', downloads: 12000}];
    if (p === '/api/hf/files') return {id: 'example/demo-coder-GGUF', license: 'Example metadata · verify publisher terms', note: 'Synthetic repository and file list', gated: false, files: [{name: 'demo-coder-Q4_K_M.gguf', bytes: 4 * 1024**3}]};
    if (p === '/api/diagnostics' || p === '/api/monitoring/diagnostics') return diagnostics;
    if (p === '/api/workspace') return workspace;
    if (p === '/api/workspace/discover') return {note: 'Demonstration discovery results.', truncated: false, projects: [{name: 'orbit-api', project: HOME + '/projects/orbit-api', enrolled: false, portable_bundle: false}, {name: 'orbit-tools', project: HOME + '/projects/orbit-tools', enrolled: false, portable_bundle: true}]};
    if (p === '/api/workspace/preview') return {ready: 2, plan: plan.plan, note: plan.note, projects: body.projects.map(v => ({project: v.project, status: 'ready', changes: [change]}))};
    if (p === '/api/monitoring') return {local, machines: {local: {name: 'Studio PC', kind: 'ollama'}, 'work-pc': {name: 'Work PC', kind: 'worker'}}, workers: {'work-pc': {observed_at: TIME, report: {...local, observations: {codex: {...observation, login: 'worker@example.com', plan: 'Second demonstration plan'}}}}}};
    if (p === '/api/storage') return {paths, volumes: {models: {free_bytes: 500 * 1024**3}, studio: {free_bytes: 250 * 1024**3}, downloads: {free_bytes: 250 * 1024**3}}, observed_models: {path: paths.models, evidence: 'Demonstration store'}, note: 'All shown locations are fictional demonstration paths.'};
    if (p === '/api/storage/preview') return {...plan, copies: [{source: paths.studio, destination: body.paths.studio, files: 12, bytes: 32000}], note: 'Verified copies preserve originals. Review the destination before saving.'};
    if (p === '/api/storage/models-preview') return {...plan, source: paths.models, destination: HOME + '/new-model-store', files: 2, bytes: 6 * 1024**3};
    if (p === '/api/vault') return vault;
    if (p === '/api/vault/preview') return {...plan, files: 3, projects: ['orbit-web'], bytes: 2048, destination: encrypted.repository};
    if (p === '/api/vault/restore-preview') return {...plan, files: 3, bytes: 2048, destination: body.destination, note: 'Restore into a new folder. Active environment files are never overwritten.'};
    if (p === '/api/encrypted-backup') return encrypted;
    if (p === '/api/encrypted-backup/snapshots') return {snapshots: [{id: 'a'.repeat(64), time: '2026-10-03T11:30:00Z'}]};
    if (p === '/api/encrypted-backup/retention-preview') return {...plan, remove: ['b'.repeat(64)], keep_last: 10, note: 'Deletes only the reviewed demonstration snapshot in this controller’s tag group.'};
    if (p === '/api/encrypted-backup/restore-preview') return {...plan, destination: body.destination, note: 'Restore and verify into a new private directory; active files are preserved.'};
    if (p === '/api/backup-schedule') return schedule;
    if (p === '/api/updates') return updates;
    if (p === '/api/updates/preview') return {...plan, version: body.rollback ? '0.2.0' : '0.3.1', blockers: scenario === 'blocked' ? ['Managed coding sessions', 'Active or queued model responses'] : [], note: 'Restart only when all model clients are idle. The previous application is retained.'};
    if (p === '/api/model-inbox') return inbox;
    if (p === '/api/insights') return {profiles, note: 'All performance figures below are synthetic documentation data.'};
    if (p === '/api/evaluations') return profiles.map(v => ({...v, status: 'passed', coding: {passed: 3, total: 3}, quantization: 'Q4_K_M', output_tokens_per_second: v.tokens_per_second}));
    if (p === '/api/workers') return {note: 'Example package choices. No executable is downloaded by this fixture.', builds_url: 'https://github.com/thierry-gilgen-ict/ai-constitution/releases', packages: [{platform: 'windows', architecture: 'amd64', kind: 'portable', signing: 'Unsigned preview · demonstration', bytes: 24 * 1024**2, sha256: 'c'.repeat(64), download: '/demonstration-package.zip'}, {platform: 'any', architecture: 'source', kind: 'source', signing: 'Python source · demonstration', bytes: 4 * 1024**2, sha256: 'd'.repeat(64), download: '/demonstration-source.zip'}]};
    if (p === '/api/workers/manage') {
      if (body.operation === 'version') return {version: VERSION, protocol: 2, capabilities: ['updates', 'diagnostics', 'monitoring', 'drivers', 'autostart']};
      if (body.operation === 'updates') return {...updates, staged: {version: '0.3.1'}};
      if (body.operation === 'preview') return {...plan, version: '0.3.1', blockers: [], note: 'Put this worker in maintenance and confirm other controllers are idle.'};
    }
    if (p === '/api/studio/templates') return {templates, components: read('templates/architecture-components.json').components, roles: ['framework', 'authentication', 'charts', 'database', 'email', 'deployment', 'testing', 'custom']};
    if (p === '/api/studio/template-versions') return {versions: [{version: '1.0.0', revision: 'a1b2c3d4e5f6', template: templates[0].template}]};
    if (p === '/api/studio/files') return {files: ['constitution.md', 'engineering.md', 'research.md', 'routing.md', 'registry/routes.json', 'templates/architectures/web-product.json'].map(name => ({path: name, editable: name !== 'routing.md', generated: name === 'routing.md', modified: false}))};
    if (p === '/api/studio/file') {
      const name = parsed.searchParams.get('path');
      if (!['constitution.md', 'engineering.md', 'research.md', 'routing.md', 'registry/routes.json', 'templates/architectures/web-product.json'].includes(name)) throw new Error('File not allowlisted for documentation');
      return {path: name, editable: name !== 'routing.md', generated: name === 'routing.md', sha256: 'demo-file', content: fs.readFileSync(path.join(ROOT, name), 'utf8'), offset: 0, next: null, reason: 'Generated routing is rebuilt from the registry; edit its source definitions.'};
    }
    if (p === '/api/studio/history') return {snapshots: [{snapshot: '20261003-demo-save', state: 'applied', files: 2}]};
    if (p === '/api/studio/activation-preview') return {...plan, files: ['AGENTS.md', '.cursor/rules/ai-constitution.mdc'], targets: [{target: PROJECT, status: 'ready'}]};
    if (p === '/api/studio/file-preview') return {...plan, changes: [{path: body.path, status: 'update', diff: '+ ' + body.content.split('\n').join('\n+ ')}]};
    if (p === '/api/studio/refresh-preview') return {...plan, changes: [{path: 'engineering.md', status: 'update', diff: '+ Verify behavior with checks suited to the change.\n'}]};
    if (p === '/api/studio/template-preview') return {...plan, changes: [{path: 'templates/architectures/' + body.template.id + '.json', status: 'update', diff: '+ Baseline: ' + body.template.name + '\n+ Review component versions and environment-variable names.\n'}]};
    if (p === '/api/studio/project-capture') return {template: templates[0].template, review, environment_keys: 3, note: 'Demonstration manifest inspection; variable values and scripts excluded.', evidence: [{file: 'package.json', component: 'nextjs', version: 'example'}, {file: 'apps/web/package.json', component: 'resend', version: 'example'}]};
    if (p.startsWith('/api/studio/') && p.endsWith('-preview')) return plan;
    if (p === '/api/action') {
      if (body.action === 'mode') { state.mode = body.mode; inventory.running = body.mode === 'gaming' ? [] : inventory.running; }
      if (body.action === 'pull') { state.jobs = [{id: 'demo-download', label: 'Download / update model', operation: 'pull', status: 'running', detail: 'Demonstration download · 42% complete'}]; return {job: 'demo-download'}; }
      return {status: 'demonstration', note: 'Demonstration only. No client, runtime or operating-system action was performed.'};
    }
    const harmless = ['/api/projects/follow', '/api/projects/sync', '/api/workspace/apply', '/api/vault/settings', '/api/vault/backup', '/api/vault/restore', '/api/monitoring/settings', '/api/monitoring/refresh', '/api/monitoring/usage', '/api/connectors/configure', '/api/connectors/refresh', '/api/operations/acknowledge', '/api/routing/profile', '/api/updates/check', '/api/updates/stage', '/api/updates/settings', '/api/model-inbox/check', '/api/workers/source', '/api/workers/fetch'];
    if (method === 'POST' && harmless.includes(p)) return {status: 'demonstration', note: 'Simulated documentation action. No live state is changed.'};
    return {__status: 400, error: 'Unimplemented documentation fixture endpoint: ' + p};
  }
  return {response, state, paths, workspace, VERSION, NOW, PROJECT};
}
module.exports = {fixture, VERSION, NOW, HOME, PROJECT};
