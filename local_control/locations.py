"""Explicit storage preferences and verified copies; never delete the original data."""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile

from scripts import constitution as kit
from scripts.catalog import digest, json_bytes
from .storage import atomic


def preferences(root):
    path = Path(root) / 'locations.json'
    kit.no_links(path)
    value = kit.read_json(path) if path.exists() else {'schema': 1}
    if value.get('schema') != 1: raise ValueError('Unsupported storage preference version')
    return value


def folder(root, kind):
    defaults = {'downloads': Path(root) / 'downloads', 'studio': Path(root) / 'studio',
                'constitution_state': Path(root).parent / 'state'}
    if kind not in defaults: raise ValueError('Unknown storage location')
    result = Path(preferences(root).get(kind, str(defaults[kind]))).absolute()
    kit.no_links(result)
    return result


def destination(value):
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
        raise ValueError('Enter an absolute local directory path')
    path = Path(value).expanduser()
    if not path.is_absolute() or '..' in path.parts or path == Path(path.anchor) or str(path).startswith(('\\\\', '//')):
        raise ValueError('Choose a local directory, not a drive root, network share or relative path')
    kit.no_links(path)
    for parent in (path, *path.parents):
        if (parent / '.git').exists(): raise ValueError('Storage must be outside Git repositories')
    if path.exists() and not path.is_dir(): raise ValueError('The selected path is a file')
    return path.absolute()


def space(path):
    current = Path(path)
    while not current.exists(): current = current.parent
    kit.no_links(current)
    info = shutil.disk_usage(current)
    return {'free_bytes': info.free, 'total_bytes': info.total}


def tree(path, *, exclude=()):
    path = Path(path); kit.no_links(path)
    result = {}
    if not path.exists(): return result
    for item in sorted(path.rglob('*')):
        kit.no_links(item)
        name = item.relative_to(path).as_posix()
        if name in exclude: continue
        if item.is_file():
            stat = item.stat()
            result[name] = [stat.st_size, stat.st_mtime_ns]
            if len(result) > 100000: raise ValueError('Storage tree exceeds the copy file-count limit')
        elif not item.is_dir(): raise ValueError('Storage contains a special file; review it before copying')
    return result


def file_hash(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''): result.update(data)
    return result.hexdigest()


def copy_plan(source, target, *, exclude=()):
    source = Path(source).absolute(); target = destination(str(target))
    kit.no_links(source)
    if source == target: return {'source': str(source), 'destination': str(target), 'files': 0, 'bytes': 0, 'unchanged': True}
    if target.is_relative_to(source) or source.is_relative_to(target):
        raise ValueError('Source and destination directories must not contain one another')
    if target.exists(): raise ValueError('Choose a new directory. Existing directories are never replaced or merged.')
    inventory = tree(source, exclude=exclude)
    size = sum(v[0] for v in inventory.values())
    available = space(target)
    if available['free_bytes'] < size + 16 * 1024 * 1024: raise ValueError('Not enough free space for a verified copy')
    return {'source': str(source), 'destination': str(target), 'files': len(inventory), 'bytes': size,
            'free_bytes': available['free_bytes'], 'fingerprint': digest(json_bytes(inventory))}


def copy_verified(source, target, expected, *, exclude=(), progress=lambda _: None, prepare=None):
    plan = copy_plan(source, target, exclude=exclude)
    if plan.get('unchanged'): return plan
    if plan['fingerprint'] != expected: raise ValueError('Source files changed since preview. Preview the copy again.')
    source, target = Path(source), destination(str(target))
    inventory = tree(source, exclude=exclude)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix='.constitution-copy-', dir=target.parent) as temporary:
        staging = Path(temporary).resolve()
        if not staging.is_relative_to(target.parent.resolve()): raise ValueError('Invalid copy staging directory')
        if prepare: prepare(staging)
        for index, name in enumerate(inventory):
            original = kit.safe_path(source, name); output = kit.safe_path(staging, name)
            output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copyfile(original, output)
            if os.name != 'nt': output.chmod(0o700 if original.stat().st_mode & 0o111 else 0o600)
            if file_hash(original) != file_hash(output): raise ValueError('Copy verification failed; original files are unchanged')
            progress(f'Verified {index + 1} of {len(inventory)} files')
        if tree(source, exclude=exclude) != inventory: raise ValueError('Source changed during copying; original files are unchanged')
        kit.no_links(target)
        if target.exists(): raise ValueError('Destination appeared during copying; it was left untouched')
        # Both resolved paths are within the explicitly selected target parent.
        if staging.parent != target.parent.resolve(): raise ValueError('Copy staging escaped its parent')
        staging.rename(target)
    return plan


def observed_models(rpc, node):
    try:
        models = rpc(node, '/api/tags', timeout=5).get('models', [])
        for model in models[:3]:
            info = rpc(node, '/api/show', {'model': model['name']}, timeout=5)
            for line in info.get('modelfile', '').splitlines():
                if line.startswith('FROM '):
                    blob = Path(line[5:].strip().strip('"'))
                    if blob.is_absolute() and blob.parent.name == 'blobs' and re.fullmatch(r'sha256-[a-f0-9]{64}', blob.name):
                        kit.no_links(blob)
                        if blob.is_file(): return {'path': str(blob.parent.parent), 'evidence': 'Reported by the running Ollama model metadata'}
    except (ValueError, OSError): pass
    default = os.environ.get('OLLAMA_MODELS')
    if not default:
        default = '/usr/share/ollama/.ollama/models' if platform.system() == 'Linux' else str(Path.home() / '.ollama/models')
    return {'path': str(Path(default).expanduser()), 'evidence': 'Environment or platform default; running server path is unverified'}


def inspect(root, rpc, node):
    settings = preferences(root)
    model = observed_models(rpc, node)
    paths = {'configuration': str(root), 'studio': str(folder(root, 'studio')), 'downloads': str(folder(root, 'downloads')),
             'constitution_state': str(folder(root, 'constitution_state')), 'models': settings.get('models', model['path'])}
    volumes = {}
    for name, path in paths.items():
        try: volumes[name] = space(path)
        except (OSError, ValueError): volumes[name] = {'status': 'unavailable'}
    return {'schema': 1, 'platform': platform.system(), 'paths': paths, 'observed_models': model,
            'pending_model_restart': paths['models'] != model['path'],
            'volumes': volumes,
            'note': 'Model weights, including Hugging Face GGUF downloads, are stored by Ollama. Browser downloads use the browser’s own download setting.'}


def settings_plan(root, values):
    if not isinstance(values, dict) or set(values) != {'models','studio','downloads'}: raise ValueError('Choose model, library and download directories')
    selected = {k: str(destination(v)) for k,v in values.items()}
    paths = [Path(v) for v in selected.values()]
    if any(a == b or a.is_relative_to(b) or b.is_relative_to(a) for i,a in enumerate(paths) for b in paths[i+1:]):
        raise ValueError('Model, library and download directories must be separate')
    current = preferences(root)
    for key, path in zip(selected, paths):
        protected = [Path(root), folder(root, 'constitution_state')]
        for directory in protected:
            # Default library/download children are valid; never select the state root or its parent.
            if path == directory or directory.is_relative_to(path): raise ValueError('Do not place a storage category over the private state directory')
        if path.is_relative_to(folder(root, 'constitution_state')): raise ValueError('Storage must be separate from instruction enrollment state')
    copies = [copy_plan(folder(root, key), Path(selected[key])) for key in ('studio','downloads') if selected[key] != str(folder(root,key))]
    if len(copies) > 1: raise ValueError('Move the library or managed downloads one at a time so each change can be verified independently')
    signature = [{k:v for k,v in c.items() if k != 'free_bytes'} for c in copies]
    return {'plan': digest(json_bytes({'current': current, 'selected': selected, 'copies': signature})), 'paths': selected, 'copies': copies,
            'model_environment': platform.system() in ('Windows','Darwin'),
            'note': 'Library and managed downloads are copied and verified; originals remain. The Ollama model folder applies after restarting Ollama. Model weights are not copied by this save.'}


def save_settings(root, values, expected, progress=lambda _: None):
    with kit.state_lock(Path(root) / 'studio-operations'):
        plan = settings_plan(root, values)
        if plan['plan'] != expected: raise ValueError('Locations changed since preview. Preview again.')
        for item in plan['copies']:
            from .project_vault import protect
            copy_verified(Path(item['source']), Path(item['destination']), item['fingerprint'], progress=progress, prepare=protect)
            if item['destination'] == plan['paths']['studio']:
                # Rebase recovery targets inside this copied workspace only.
                for journal in (Path(item['destination']) / 'state/transactions').glob('*.json'):
                    record = kit.read_json(journal)
                    for entry in record['files']:
                        path = Path(entry['path'])
                        if path.is_relative_to(Path(item['source'])):
                            entry['path'] = str(Path(item['destination']) / path.relative_to(item['source']))
                    atomic(journal, record)
        old = preferences(root)
        value = {**old, **plan['paths'], 'schema': 1}
        atomic(Path(root) / 'locations.json', value)
        return {'status': 'saved', 'paths': plan['paths'],
                'note': 'Folder preferences saved. Use Apply Ollama location to set the OS environment, then restart Ollama when idle. Copy model weights separately if needed. A running CPU fallback retains its old model store until restarted.'}


def apply_models(root):
    value = preferences(root)
    target = str(destination(value.get('models')))
    if platform.system() == 'Windows':
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, 'Environment') as key:
            winreg.SetValueEx(key, 'OLLAMA_MODELS', 0, winreg.REG_SZ, target)
        import ctypes
        from ctypes import wintypes
        send = ctypes.windll.user32.SendMessageTimeoutW
        send.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPCWSTR, wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
        send.restype = wintypes.LPARAM
        result = ctypes.c_size_t()
        send(65535, 0x1A, 0, 'Environment', 2, 1000, ctypes.byref(result))
    elif platform.system() == 'Darwin':
        subprocess.run(['launchctl', 'setenv', 'OLLAMA_MODELS', target], check=True, capture_output=True, timeout=10)
    else:
        return {'status': 'manual', 'note': 'Set OLLAMA_MODELS in the Ollama systemd service environment and give its service user access to this directory, then restart the service when idle.'}
    return {'status': 'pending-restart', 'note': 'Environment updated. Restart Ollama when idle. On macOS repeat this step after login. Existing processes and active tasks keep their current model store.'}


def model_copy_plan(control):
    observed = observed_models(control.rpc, control.node('local'))
    if not observed['evidence'].startswith('Reported'):
        raise ValueError('Ollama has not confirmed its current model store. Start it with an installed model before copying weights.')
    selected = preferences(control.root).get('models')
    if not selected: raise ValueError('Save the desired model location first')
    result = copy_plan(Path(observed['path']), Path(selected))
    if result.get('unchanged'): raise ValueError('The selected model store is already in use')
    result['plan'] = digest(json_bytes({k:v for k,v in result.items() if k != 'free_bytes'}))
    return result


def copy_models(control, expected, progress=lambda _: None):
    with control.operation:
        preview = model_copy_plan(control)
        if preview['plan'] != expected: raise ValueError('The model store or destination changed. Preview the copy again.')
        return copy_verified(Path(preview['source']), Path(preview['destination']), preview['fingerprint'], progress=progress)


def resolve_root(root):
    root = Path(root).absolute()
    for _ in range(8):
        kit.no_links(root)
        marker = root / 'relocated.json'; kit.no_links(marker)
        if not marker.exists(): return root
        root = destination(kit.read_json(marker)['destination'])
    raise ValueError('Configuration relocation chain is invalid')


def relocation_plan(root, target):
    excluded = tuple(n for n in tree(root) if n.endswith('.lock') or n in ('runtime.json','relocated.json'))
    return copy_plan(root, target, exclude=excluded), excluded


def relocate(root, target, expected):
    from .storage import ProcessLock
    from .project_vault import protect
    # The OS lock proves the service has stopped; no process is killed here.
    ownership = ProcessLock(Path(root) / 'server.lock')
    try:
        plan, excluded = relocation_plan(root, target)
        if plan.get('unchanged') or plan['fingerprint'] != expected: raise ValueError('Configuration changed; preview relocation again after stopping the service')
        old = Path(root); target = destination(str(target))
        copy_verified(old, target, expected, exclude=excluded, prepare=protect)
        value = preferences(target)
        for kind in ('studio','downloads'):
            previous = folder(old, kind)
            value[kind] = str(target / previous.relative_to(old)) if previous.is_relative_to(old) else str(previous)
        value['constitution_state'] = str(folder(old, 'constitution_state'))
        atomic(target / 'locations.json', value)
        # Transaction histories in the moved draft must point to its new location.
        for journal in (Path(value['studio']) / 'state/transactions').glob('*.json'):
            record = kit.read_json(journal)
            for entry in record['files']:
                path = Path(entry['path'])
                if path.is_relative_to(old): entry['path'] = str(target / path.relative_to(old))
            atomic(journal, record)
        atomic(old / 'relocated.json', {'schema': 1, 'destination': str(target)})
        return {'status': 'relocated', 'destination': str(target), 'note': 'Original files retained. Existing launch commands follow the private relocation pointer; start Local Control again.'}
    finally: ownership.close()
