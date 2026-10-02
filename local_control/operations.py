"""Bounded, private job history. Recovery never replays an interrupted operation."""
import json
import time
from .storage import atomic


class Cancelled(ValueError):
    pass


def recover(root):
    path = root / 'operations.json'
    if not path.exists():
        return {}, []
    value = json.loads(path.read_text(encoding='utf-8'))
    if value.get('schema') != 1:
        raise ValueError('Unsupported operation history; preserve it before recovery')
    jobs = {j['id']: j for j in value.get('jobs', [])[-50:]}
    for job in jobs.values():
        if job['status'] in ('queued', 'running'):
            job.update(status='interrupted', detail='Service restarted. Check actual machine state, then explicitly retry.')
    events = value.get('events', [])[:80]
    save(root, jobs, events)
    return jobs, events


def save(root, jobs, events):
    atomic(root / 'operations.json', {'schema': 1, 'jobs': list(jobs.values())[-50:], 'events': events[:80]})
