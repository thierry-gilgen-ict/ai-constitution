"""Private, bounded workflow state and deterministic review fingerprints."""
import copy
import re
import time
from pathlib import Path

from scripts import constitution as kit
from scripts.catalog import digest, json_bytes
from .storage import atomic


def read(root, name, default, *, limit=4 * 1024 * 1024):
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,63}\.json', name):
        raise ValueError('Invalid workflow state name')
    path = Path(root) / 'workspace' / name
    kit.no_links(path)
    if not path.exists(): return copy.deepcopy(default)
    if not path.is_file() or path.stat().st_size > limit:
        raise ValueError('Workflow state exceeds its size limit; preserve it before recovery')
    value = kit.read_json(path)
    if not isinstance(value, dict) or value.get('schema') != default.get('schema'):
        raise ValueError('Unsupported workflow state; preserve it before migration')
    return value


def write(root, name, value):
    # Validate the destination even for new files. Existing private state is never
    # imported into a public library or included in a portable source export.
    read(root, name, {'schema': value.get('schema')})
    if len(json_bytes(value)) > 4 * 1024 * 1024:
        raise ValueError('Workflow history exceeds its size limit')
    atomic(Path(root) / 'workspace' / name, value)


def seal(value):
    return {**value, 'plan': digest(json_bytes(value))}


def verify(value, reviewed):
    if not isinstance(reviewed, str) or reviewed != value.get('plan'):
        raise ValueError('Setup or target state changed since review. Preview again.')


def fingerprint(path):
    path = Path(path); kit.no_links(path)
    if not path.exists(): return None
    if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError('Workflow input must be a bounded ordinary file')
    return digest(path.read_bytes())


def project(root, value):
    if not isinstance(value, str) or len(value) > 1000:
        raise ValueError('Choose an enrolled project')
    path = Path(value).expanduser().absolute(); kit.no_links(path)
    from .studio import Studio
    targets = kit.state_load(Studio(root).state)['targets']
    if not path.is_dir() or 'project:' + str(path) not in targets:
        raise ValueError('Choose an existing project enrolled on this controller')
    return path


def evidence(value, source, *, level='observed', observed_at=None):
    return {'value': value, 'source': source, 'level': level,
            'observed_at': time.time() if observed_at is None else observed_at}


class Checkpoints:
    """Durable steps; uncertain side effects require an explicit reviewed retry."""
    def __init__(self, root, identity, signature):
        if not re.fullmatch(r'[a-f0-9]{12}', identity): raise ValueError('Invalid workflow operation')
        self.root, self.identity = root, identity
        self.value = read(root, 'run-' + identity + '.json',
                          {'schema': 1, 'plan': signature, 'steps': {}, 'created_at': time.time()})
        if self.value['plan'] != signature: raise ValueError('Operation belongs to a different reviewed plan')

    def step(self, name, perform, verified=lambda _: True, *, retry_uncertain=False):
        previous = self.value['steps'].get(name, {})
        if previous.get('status') == 'done':
            if not verified(previous.get('evidence')):
                raise ValueError('Completed step changed; inspect it before continuing')
            return previous.get('evidence')
        if previous.get('status') == 'started' and not retry_uncertain:
            raise ValueError('Step may have completed before interruption. Inspect actual state, then explicitly review a retry.')
        self.value['steps'][name] = {'status': 'started', 'started_at': time.time()}
        self.save()
        result = perform()
        self.value['steps'][name] = {'status': 'done', 'evidence': result, 'finished_at': time.time()}
        self.save()
        return result

    def save(self): write(self.root, 'run-' + self.identity + '.json', self.value)
