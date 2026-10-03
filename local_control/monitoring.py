"""Private application/account inventory; read-only, explicitly enabled collectors."""
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import threading
import time
import uuid

from scripts import constitution as kit
from .storage import atomic
from . import diagnostics

PROVIDERS = {'openai', 'cursor', 'anthropic', 'xai', 'google', 'other'}
LINKS = {'openai': 'https://chatgpt.com/codex/settings/usage', 'cursor': 'https://cursor.com/dashboard',
         'anthropic': 'https://claude.ai/settings/usage', 'xai': 'https://console.x.ai/', 'google': 'https://aistudio.google.com/'}


def load(root):
    path = Path(root) / 'monitoring.json'; kit.no_links(path)
    return kit.read_json(path) if path.exists() else {'schema': 1, 'codex_enabled': False, 'share_with_controllers': False,
        'accounts': {}, 'observations': {}, 'events': [], 'refreshed_at': None}


def text(value, limit=160):
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 for c in value): raise ValueError('Enter a short text value without control characters')
    # Fields are labels, never credential inputs.
    if re.search(r'(?:sk-[A-Za-z0-9_-]{15,}|eyJ[A-Za-z0-9_-]{15,}\.|Bearer\s+\S+)', value): raise ValueError('Use an account label or login email, never a token')
    return value


def event(value, target, status, code):
    value['events'].insert(0, {'time': time.time(), 'target': target, 'status': status, 'code': code})
    del value['events'][200:]


def configure(root, body, *, local=True):
    with kit.state_lock(Path(root) / 'monitor-operations'):
        value = load(root)
        for key in ('codex_enabled', 'share_with_controllers'):
            if key in body:
                if not local: raise ValueError('Enable account sharing locally on the worker')
                if type(body[key]) is not bool: raise ValueError('Choose whether to enable the collector')
                value[key] = body[key]
        if 'account' in body:
            item = body['account']
            provider = item.get('provider')
            if provider not in PROVIDERS: raise ValueError('Choose a supported provider or Other')
            identity = item.get('id') or uuid.uuid4().hex[:12]
            if not re.fullmatch('[a-f0-9]{12}', identity): raise ValueError('Invalid account record')
            fields = {k: text(item.get(k, '')) for k in ('label','login','plan','machine','application')}
            projects = item.get('projects', [])
            if not isinstance(projects, list) or len(projects) > 100: raise ValueError('Choose up to 100 projects')
            fields['projects'] = [text(p, 500) for p in projects]
            previous = value['accounts'].get(identity, {})
            value['accounts'][identity] = {**previous, **fields, 'id': identity, 'provider': provider, 'source': 'manual',
                'subscription_key': hashlib.sha256((provider + '|' + fields['login'].strip().casefold() + '|' + fields['plan'].casefold()).encode()).hexdigest()[:24] if fields['login'] else identity}
            event(value, identity, 'saved', 'account_mapping_updated')
        if 'remove' in body:
            value['accounts'].pop(body['remove'], None)
        atomic(Path(root) / 'monitoring.json', value)
        return {'status': 'saved'}


def record_usage(root, identity, sample):
    """Portable manual/import schema; no raw logs, prompts or arbitrary JSON retained."""
    if not isinstance(sample, dict): raise ValueError('Enter a usage observation')
    amount = sample.get('used'); limit = sample.get('limit')
    for number in (amount, limit):
        if number is not None and (type(number) not in (int, float) or not math.isfinite(number) or number < 0): raise ValueError('Usage and allowance must be nonnegative numbers or null')
    if amount is None: raise ValueError('Enter observed usage')
    if limit == 0: raise ValueError('Allowance must be positive or unknown')
    unit = sample.get('unit')
    if unit not in ('tokens','requests','USD','EUR','CHF','percent'): raise ValueError('Choose a supported unit')
    observed = sample.get('observed_at', time.time())
    if type(observed) not in (int,float) or not math.isfinite(observed) or not 0 < observed <= time.time() + 60: raise ValueError('Invalid observation time')
    item = {'used': amount, 'limit': limit, 'unit': unit, 'period': text(sample.get('period', 'Unspecified period')),
            'observed_at': observed, 'source': 'manual/import', 'model': text(sample.get('model', ''))}
    with kit.state_lock(Path(root) / 'monitor-operations'):
        value = load(root)
        if identity not in value['accounts']: raise ValueError('Choose an account first')
        entries = value['accounts'][identity].setdefault('usage', [])
        entries.insert(0, item); del entries[90:]
        event(value, identity, 'saved', 'usage_observation_recorded')
        atomic(Path(root) / 'monitoring.json', value)
    return {'status': 'saved'}


def codex_binary():
    executable = shutil.which('codex.exe') or shutil.which('codex')
    if os.name == 'nt' and (not executable or Path(executable).suffix.lower() in ('.cmd','.bat','.ps1')):
        base = Path(os.environ.get('APPDATA', '')) / 'npm/node_modules/@openai'
        binaries = sorted(base.glob('codex*/**/codex.exe')) if base.is_dir() else []
        executable = str(binaries[0]) if binaries else None
    return executable


class ProbeError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__('Codex account probe: ' + code)


class CodexReader:
    """Own one stdio process, issue only allowlisted reads, never start a turn."""
    def __init__(self, executable):
        self.process = subprocess.Popen([executable, 'app-server'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding='utf-8', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.messages = queue.Queue(maxsize=64); self.number = 0
        self.write_lock = threading.Lock()
        self.thread = threading.Thread(target=self.read, daemon=True); self.thread.start()

    def read(self):
        try:
            while True:
                line = self.process.stdout.readline(2 * 1024 * 1024)
                if not line: break
                if len(line) >= 2 * 1024 * 1024: break
                value = json.loads(line)
                if 'id' in value and 'method' not in value:
                    self.messages.put_nowait(value)
                elif 'id' in value:
                    # Refuse server-initiated actions; this connection is read-only.
                    self.send({'id': value['id'], 'error': {'code': -32601, 'message': 'Read-only monitoring client'}})
        except (OSError, ValueError, queue.Full): pass

    def send(self, value):
        with self.write_lock:
            self.process.stdin.write(json.dumps(value) + '\n'); self.process.stdin.flush()

    def call(self, method, params=None):
        if method not in ('initialize','account/read','account/rateLimits/read','account/usage/read'): raise ProbeError('method_not_allowed')
        self.number += 1; identity = self.number
        self.send({'id': identity, 'method': method, 'params': params or {}})
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            try: result = self.messages.get(timeout=max(.01, deadline - time.monotonic()))
            except queue.Empty: raise ProbeError('timeout') from None
            if result.get('id') != identity: continue
            if 'error' in result:
                code = result['error'].get('code')
                raise ProbeError('unsupported_method' if code == -32601 else 'provider_error')
            return result.get('result', {})
        raise ProbeError('timeout')

    def close(self):
        self.process.stdin.close()
        try: self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try: self.process.wait(timeout=2)
            except subprocess.TimeoutExpired: self.process.kill(); self.process.wait(timeout=2)
        self.thread.join(timeout=1); self.process.stdout.close()


def number(value):
    return value if type(value) in (int,float) and math.isfinite(value) and value >= 0 else None


def codex_snapshot(executable, reader=CodexReader):
    rpc = reader(executable)
    result = {'source': 'Codex app-server / local CLI profile', 'observed_at': time.time(), 'status': 'available', 'windows': [], 'daily': [], 'issues': []}
    try:
        rpc.call('initialize', {'clientInfo': {'name': 'ai_constitution_monitor', 'title': 'AI Constitution Monitor', 'version': '0.2.0'}})
        rpc.send({'method': 'initialized', 'params': {}})
        account = rpc.call('account/read', {'refreshToken': False}).get('account')
        if not account: return {**result, 'status': 'signed-out', 'login': '', 'plan': ''}
        result.update(login=text(account.get('email') or ''), plan=text(account.get('planType') or ''), auth_type=text(account.get('type') or 'unknown'))
        for method in ('account/rateLimits/read','account/usage/read'):
            try:
                data = rpc.call(method)
                if method.endswith('rateLimits/read'):
                    buckets = data.get('rateLimitsByLimitId') or {'codex': data.get('rateLimits')}
                    for key, bucket in list(buckets.items())[:20]:
                        if not isinstance(bucket, dict): continue
                        for window in ('primary','secondary'):
                            v = bucket.get(window)
                            if isinstance(v, dict): result['windows'].append({'bucket': text(key), 'window': window,
                                'used_percent': number(v.get('usedPercent')), 'duration_minutes': number(v.get('windowDurationMins')), 'resets_at': number(v.get('resetsAt'))})
                else:
                    result['summary'] = {k: number((data.get('summary') or {}).get(k)) for k in ('lifetimeTokens','peakDailyTokens','longestRunningTurnSec','currentStreakDays','longestStreakDays')}
                    result['daily'] = [{'date': text(v.get('startDate', ''), 30), 'tokens': number(v.get('tokens'))} for v in (data.get('dailyUsageBuckets') or [])[-365:]]
            except ProbeError as error: result['issues'].append({'endpoint': method, 'code': error.code})
        return result
    finally: rpc.close()


def collect(root):
    value = load(root)
    observations = {}
    executable = codex_binary()
    observations['codex'] = {'installed': bool(executable), 'status': 'disabled', 'source': 'Local CLI profile; may differ from the desktop app login'}
    if value['codex_enabled']:
        if not executable: observations['codex']['status'] = 'not-installed'
        else:
            try: observations['codex'] = {**observations['codex'], **codex_snapshot(executable)}
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                observations['codex'].update(status='unavailable', code=error.code if isinstance(error, ProbeError) else 'collector_failed')
    cursor = shutil.which('cursor') or (os.name == 'nt' and (Path(os.environ.get('LOCALAPPDATA','')) / 'Programs/cursor/Cursor.exe').is_file())
    observations['cursor'] = {'installed': bool(cursor), 'status': 'manual/import', 'source': 'Account mapping and usage observations; no private browser/session-token scraping'}
    with kit.state_lock(Path(root) / 'monitor-operations'):
        current = load(root)
        # Respect a collector disabled while the probe was in flight.
        if not current['codex_enabled']: observations['codex'] = {'status': 'disabled', 'installed': bool(executable)}
        for name, observation in observations.items():
            previous = current.get('observations', {}).get(name, {})
            if observation.get('status') == 'available':
                observation['subscription_key'] = hashlib.sha256(('openai|' + observation.get('login', '').strip().casefold() + '|' + observation.get('plan', '').casefold()).encode()).hexdigest()[:24]
                history = current.setdefault('history', {}).setdefault(name, [])
                history.append({k:v for k,v in observation.items() if k in ('observed_at','windows','summary','subscription_key')})
                del history[:-288]
            elif previous.get('status') == 'available' or previous.get('last_successful'):
                observation['last_successful'] = previous.get('last_successful') or previous
        current['observations'] = observations; current['refreshed_at'] = time.time()
        event(current, 'codex', observations['codex']['status'], observations['codex'].get('code', 'read_only_account_probe'))
        atomic(Path(root) / 'monitoring.json', current)
    return current


def local_report(control):
    value = load(control.root)
    from .connectors import capabilities, alerts
    return {**value, 'connectors': capabilities(), 'alerts': alerts(value), 'diagnostics': diagnostics.report(control), 'provider_links': LINKS,
            'note': 'Login identifiers are private metadata. No passwords, API keys, auth files or conversation contents are collected. Provider quotas are account-wide, not per-machine totals. A missing value is unknown, never zero.'}


def refresh(control, node_id='local', progress=lambda _: None):
    node = control.node(node_id)
    if node['kind'] == 'ollama':
        collect(control.root)
        return {'status': 'refreshed'}
    report = control.rpc(node, '/monitoring/refresh', {}, timeout=55)
    # Reports are from authenticated, pinned workers; still validate their public schema.
    if not isinstance(report, dict) or report.get('schema') != 1: raise ValueError('Worker returned an unsupported monitoring report')
    with kit.state_lock(control.root / 'monitor-operations'):
        path = control.root / 'worker-observations.json'; kit.no_links(path)
        value = kit.read_json(path) if path.exists() else {}
        value[node_id] = {'observed_at': time.time(), 'report': report}
        atomic(path, value)
    return {'status': 'refreshed'}


def overview(control):
    path = control.root / 'worker-observations.json'; kit.no_links(path)
    workers = kit.read_json(path) if path.exists() else {}
    allowed = control.status()['nodes']
    return {'local': local_report(control), 'workers': {k:v for k,v in workers.items() if k in allowed},
            'machines': {k: {'name':v['name'], 'kind':v['kind']} for k,v in allowed.items() if k != 'local-cpu'}}
