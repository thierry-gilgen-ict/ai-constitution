"""Measured local evidence, separate from catalog metadata and memory estimates."""
import statistics
from scripts import constitution as kit
from scripts.catalog import digest, json_bytes


def profiles(root):
    groups = {}
    for path in sorted((root / 'evaluations').glob('*.json'))[-500:]:
        kit.no_links(path)
        record = kit.read_json(path)
        key = {k: record.get(k) for k in ('node', 'model', 'context', 'hardware', 'fixture_version')}
        identity = digest(json_bytes(key))[:20]
        group = groups.setdefault(identity, {'id': identity, **key, 'samples': []})
        group['samples'].append(record)
    result = []
    for group in groups.values():
        samples = sorted(group.pop('samples'), key=lambda s: s.get('created', 0))[-20:]
        def median(field):
            values = [s[field] for s in samples if s.get('status') == 'passed' and type(s.get(field)) in (int,float)]
            return round(statistics.median(values), 3) if values else None
        result.append({**group, 'count': len(samples), 'passed': sum(s.get('status') == 'passed' for s in samples),
            'last_observed': samples[-1].get('created'), 'first_text_seconds': median('first_text_seconds'),
            'tokens_per_second': median('output_tokens_per_second'), 'resident_gpu_bytes': median('resident_gpu_bytes_after'),
            'memory': samples[-1].get('memory'), 'level': samples[-1].get('level', 'unverified'),
            'note': 'Observed on this machine, model alias and context. Clamp fixture only; no general coding-quality ranking.'})
    return sorted(result, key=lambda r: r['last_observed'] or 0, reverse=True)


def suggestion(control):
    rows = profiles(control.root)
    configured = [p for p in [control.config.get('primary'), *control.fallback_candidates()] if p]
    eligible = [r for r in rows if r['context'] == control.config['context'] and r['passed'] >= 1
                and any(e['node'] == r['node'] and e['model'] == r['model'] for e in configured)]
    fast = sorted(eligible, key=lambda r: (r['first_text_seconds'] is None, r['first_text_seconds'] or 0))
    return {'profiles': rows, 'fast_candidate': fast[0]['id'] if fast else None,
            'note': 'Fast suggestion uses measured time to first text among configured, tested routes. VRAM estimates alone never establish coding suitability.'}
