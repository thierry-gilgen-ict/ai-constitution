"""Explicit, read-only subscription connectors with honest capability boundaries."""
import datetime as dt
from decimal import Decimal, InvalidOperation
import json
import os
import re
import time
import urllib.parse
import urllib.request
from . import monitoring
from .storage import atomic, wait_lock


def capabilities():
    return [
        {'id': 'codex', 'scope': 'Local CLI sign-in', 'permission': 'Explicit collector opt-in', 'metrics': ['account','quota windows','daily usage when exposed']},
        {'id': 'openai-api', 'scope': 'API organization, separate from ChatGPT/Codex subscription', 'permission': 'Admin API key in a named environment variable', 'metrics': ['daily API cost']},
        {'id': 'anthropic-api', 'scope': 'Claude Console API organization; excludes Priority Tier costs', 'permission': 'Admin API key in a named environment variable', 'metrics': ['daily API cost']},
        {'id': 'manual/import', 'scope': 'Cursor, xAI, Google, Claude subscriptions and other providers', 'permission': 'User supplied observations', 'metrics': ['usage','allowance','period','model']},
    ]


def alerts(value):
    results = []
    for name, report in value.get('observations', {}).items():
        if report.get('status') == 'unavailable': results.append({'source': name, 'kind': 'collector', 'message': 'Refresh failed; last successful report remains available.'})
        for window in report.get('windows', []):
            percent = window.get('used_percent')
            if percent is not None and percent >= 85:
                results.append({'source': name, 'kind': 'usage', 'message': str(window.get('bucket')) + ': ' + str(percent) + '% used', 'resets_at': window.get('resets_at')})
    for account in value.get('accounts', {}).values():
        sample = next(iter(account.get('usage', [])), {})
        if sample.get('limit') and sample['used'] / sample['limit'] >= .85:
            results.append({'source': account['id'], 'kind': 'usage', 'message': 'Observed usage is at least 85% of the recorded allowance; verify the period in the provider dashboard.'})
    return results


def configure(root, body):
    with wait_lock(root / 'monitor-operations'):
        value = monitoring.load(root)
        account = value['accounts'].get(body.get('account'))
        if not account: raise ValueError('Choose a subscription record first')
        connector = body.get('connector')
        if connector not in ('openai-api','anthropic-api','manual/import'): raise ValueError('Choose a listed connector')
        env = body.get('key_env', '')
        if connector != 'manual/import' and not re.fullmatch('[A-Z][A-Z0-9_]{0,79}', env):
            raise ValueError('Enter the name of an environment variable containing the admin key, not its value')
        account['connector'] = {'id': connector, 'key_env': env}
        atomic(root / 'monitoring.json', value)
    return {'status': 'saved', 'note': 'Connector configured. Reads occur only when you refresh this API account; no inference calls.'}


def get(url, headers):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args): raise ValueError('Provider redirect refused; credentials were not forwarded')
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as response:
        raw = response.read(2 * 1024**2 + 1)
    if len(raw) > 2 * 1024**2: raise ValueError('Usage report exceeds the size limit')
    return json.loads(raw)


def refresh(root, identity, progress=lambda _: None, fetch=get):
    value = monitoring.load(root); account = value['accounts'].get(identity)
    if not account: raise ValueError('Choose an account')
    config = account.get('connector', {})
    provider = config.get('id'); key = os.environ.get(config.get('key_env', ''))
    if provider not in ('openai-api','anthropic-api') or not key: raise ValueError('Configure a supported connector and make its admin key available to this process')
    now = dt.datetime.now(dt.timezone.utc); begin = now.replace(hour=0, minute=0, second=0, microsecond=0) - dt.timedelta(days=7)
    if provider == 'openai-api':
        base = 'https://api.openai.com/v1/organization/costs'
        params = {'start_time': int(begin.timestamp()), 'end_time': int(now.timestamp()), 'limit': 31}
        headers = {'Authorization': 'Bearer ' + key}
    else:
        base = 'https://api.anthropic.com/v1/organizations/cost_report'
        params = {'starting_at': begin.isoformat(), 'ending_at': now.isoformat(), 'limit': 31}
        headers = {'x-api-key': key, 'anthropic-version': '2023-06-01'}
    daily, status = [], 'available'
    try:
        for _ in range(10):
            data = fetch(base + '?' + urllib.parse.urlencode(params), headers)
            for bucket in data.get('data', []):
                amount = Decimal(0)
                for entry in bucket.get('results', []):
                    raw = entry.get('amount', {}) if provider == 'openai-api' else entry
                    currency = raw.get('currency', '').upper()
                    if currency != 'USD': raise ValueError('Unsupported cost currency')
                    number = Decimal(str(raw.get('value') if provider == 'openai-api' else raw.get('amount'))) / (1 if provider == 'openai-api' else 100)
                    if not number.is_finite() or number < 0: raise ValueError('Invalid cost value')
                    amount += number
                date = dt.datetime.fromtimestamp(bucket['start_time'], dt.timezone.utc).date().isoformat() if provider == 'openai-api' else bucket['starting_at'][:10]
                daily.append({'date': date, 'amount': str(amount), 'currency': 'USD'})
            if not data.get('has_more'): break
            if not isinstance(data.get('next_page'), str): raise ValueError('Missing report pagination cursor')
            params['page'] = data['next_page']
        else: raise ValueError('Report exceeds ten pages')
        report = {'status': status, 'observed_at': time.time(), 'daily': daily, 'scope': 'API organization costs, not subscription quota', 'source': provider}
    except (ValueError, OSError, InvalidOperation, KeyError, TypeError):
        report = {'status': 'unavailable', 'observed_at': time.time(), 'source': provider, 'code': 'collector_failed'}
    with wait_lock(root / 'monitor-operations'):
        current = monitoring.load(root); target = current['accounts'].get(identity)
        if not target or target.get('connector') != config: raise ValueError('Connector changed during refresh; result discarded')
        previous = target.get('report', {})
        if report['status'] != 'available': report['last_successful'] = previous.get('last_successful') or (previous if previous.get('status') == 'available' else None)
        target['report'] = report
        if report['status'] == 'available':
            history = target.setdefault('history', []); history.append(report); del history[:-90]
        monitoring.event(current, identity, report['status'], 'read_only_api_cost_report')
        atomic(root / 'monitoring.json', current)
    if report['status'] == 'unavailable': raise ValueError('API cost refresh failed; previous report preserved. Check the admin key and organization permissions.')
    return {'status': 'refreshed', 'days': len(daily)}
