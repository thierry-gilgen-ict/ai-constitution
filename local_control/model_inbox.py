"""Review catalog changes before replacing the private library snapshot."""
import json
from pathlib import Path
from scripts import catalog, constitution as kit, releases
from scripts.catalog import digest, json_bytes
from .studio import Studio
from .storage import atomic, wait_lock


def read(root):
    path = Path(root) / 'model-inbox.json'; kit.no_links(path)
    return kit.read_json(path) if path.exists() else {'status': 'not-checked', 'changes': [], 'route_impact': []}


def check(root, progress=lambda _: None, raw=None):
    studio = Studio(root)
    progress('Fetching public model definitions; no provider inference or account calls')
    providers = catalog.validate_providers(json.loads(catalog.fetch_public(catalog.CATALOG_URL) if raw is None else raw))
    with wait_lock(studio.guard):
        studio.initialize()
        old_bytes = (studio.draft / 'registry/catalog.json').read_bytes()
        old = json.loads(old_bytes)['providers']
        report = catalog.catalog_diff(old, providers)
        changes = []
        for provider in sorted(set(old) | set(providers)):
            before, after = old.get(provider, {}).get('models', {}), providers.get(provider, {}).get('models', {})
            for name in sorted(set(before) | set(after)):
                if before.get(name) == after.get(name): continue
                fields = {key: {'before': (before.get(name) or {}).get(key), 'after': (after.get(name) or {}).get(key)}
                    for key in ('name','cost','limit','modalities','tool_call','reasoning','attachment','open_weights','status','release_date','last_updated')
                    if (before.get(name) or {}).get(key) != (after.get(name) or {}).get(key)}
                changes.append({'provider': provider, 'model': name, 'kind': 'added' if name not in before else 'removed' if name not in after else 'changed', 'fields': fields})
        changed = {(v['provider'], v['model']) for v in changes}
        curated = kit.read_json(studio.draft / 'registry/models.json')['models']
        impacted = {m['key'] for m in curated if (m['provider'], m.get('selector')) in changed}
        routes = kit.read_json(studio.draft / 'registry/routes.json')['routes']
        candidate = {'schema_version': 1, 'source': catalog.CATALOG_URL, 'source_license': 'MIT; see docs/licenses/models-dev.txt',
            'retrieved_at': catalog.utc_now(), 'source_sha256': digest(json_bytes(providers)),
            'provenance': 'Community catalog metadata. Account access and evaluated performance are separate evidence.',
            'provider_count': len(providers), 'model_count': sum(len(v['models']) for v in providers.values()), 'providers': providers}
        data = catalog.catalog_bytes(candidate)
        atomic(Path(root) / 'model-candidate.json', candidate)
        value = {'status': 'review', 'checked_at': candidate['retrieved_at'], 'base': digest(old_bytes), 'candidate': digest(data),
            'changes': changes, 'summary': report, 'route_impact': [r for r in routes if impacted.intersection([r['preferred'], *r['fallbacks']])],
            'note': 'Catalog inclusion does not establish account access or measured performance. Applying preserves curated routes and verified overrides; review impacted routes explicitly.'}
        value['plan'] = digest(json_bytes({'base': value['base'], 'candidate': value['candidate']}))
        atomic(Path(root) / 'model-inbox.json', value)
    return {'status': 'review', 'changes': len(changes), 'note': 'Model changes are ready in the update inbox.'}


def apply(root, expected):
    studio = Studio(root)
    with wait_lock(studio.guard):
        value = read(root)
        path = Path(root) / 'model-candidate.json'; kit.no_links(path)
        data = catalog.catalog_bytes(kit.read_json(path))
        if value.get('plan') != expected or digest(data) != value.get('candidate') or digest((studio.draft / 'registry/catalog.json').read_bytes()) != value.get('base'):
            raise ValueError('Catalog changed since review; check models again')
        payload = studio.staged({'registry/catalog.json': data})
        current = studio.payload()
        result = kit.transaction(studio.history, {studio.file_path(n): b for n,b in payload.items() if current.get(n) != b})
        value['status'] = 'applied'; atomic(Path(root) / 'model-inbox.json', value)
        return {**result, 'note': 'Catalog applied to the private library. Curated model choices remain unchanged.'}
