"""Suggest a baseline from allowlisted manifests; never copy existing configuration values."""
import copy
import json
from pathlib import Path
import re
import tomllib

from scripts import architecture, constitution as kit
from . import project_vault


def bounded(path):
    kit.no_links(path)
    if path.stat().st_size > 1024 * 1024: raise ValueError('A project manifest exceeds the 1 MiB inspection limit')
    return path.read_text(encoding='utf-8-sig')


def capture(studio, root, body):
    project = Path(body.get('project', ''))
    if not project.is_absolute() or not project.is_dir(): raise ValueError('Choose an existing absolute project directory')
    kit.no_links(project)
    identity = architecture.identifier(body.get('id'))
    catalog = {v['id']: v for v in kit.read_json(studio.draft / 'templates/architecture-components.json')['components']}
    found, evidence, env = {}, [], set()
    mappings = {'next':'nextjs', 'better-auth':'better-auth', 'echarts':'echarts', 'resend':'resend', 'pg':'postgres', 'postgres':'postgres'}
    def add(key, source, version=''):
        if key not in catalog: return
        found[key] = copy.deepcopy(catalog[key])
        evidence.append({'file': source, 'component': key, 'version': version if re.fullmatch(r'[~^<>= v0-9.*|,-]{1,80}', version) else 'Review the project lockfile'})
    if (project / 'package.json').is_file():
        package = json.loads(bounded(project / 'package.json'))
        for group in ('dependencies','devDependencies'):
            for name, version in package.get(group, {}).items():
                if name in mappings: add(mappings[name], 'package.json', str(version))
    pyproject = project / 'pyproject.toml'
    if pyproject.is_file():
        value = tomllib.loads(bounded(pyproject))
        dependencies = value.get('project', {}).get('dependencies', [])
        if any(isinstance(v,str) and re.match(r'(?i)^fastapi(?:\b|\[)', v) for v in dependencies): add('fastapi','pyproject.toml')
    requirements = project / 'requirements.txt'
    if requirements.is_file() and re.search(r'(?im)^fastapi\b', bounded(requirements)): add('fastapi','requirements.txt')
    for name in ('compose.yaml','compose.yml','docker-compose.yml','docker-compose.yaml'):
        path = project / name; kit.no_links(path)
        if path.is_file(): add('docker', name)
    # Even .env.example may contain real values: parse names only, discard all right-hand sides.
    example = project / '.env.example'; kit.no_links(example)
    sources = [example] if example.is_file() else []
    if body.get('configuration'):
        entry = project_vault.read(root)['projects'].get(body['configuration'])
        if not entry or Path(entry.get('project', '')).absolute() != project.absolute():
            raise ValueError('Choose a registered configuration mapping belonging to this project')
        folder = Path(entry['folder']); kit.no_links(folder)
        sources += [p for p in folder.iterdir() if p.is_file() and (p.name.startswith('.env') or p.suffix == '.env')]
    for path in sources:
        for line in bounded(path).splitlines():
            match = re.match(r'^\s*(?:export\s+)?([A-Z][A-Z0-9_]{0,79})\s*=', line)
            if match: env.add(match[1])
    if len(env) > 40: raise ValueError('More than 40 environment keys found; split this baseline into smaller components')
    for component in found.values():
        # Detection shows presence, not compatibility; do not infer deployment credentials or pins.
        component['reference'] = ''
    if env:
        known = {v['name'] for c in found.values() for v in c.get('env', [])}
        found['project-config'] = {'id':'project-config','role':'custom','name':'Project configuration',
            'instructions':'Supply values from the private project configuration directory. Review each variable purpose and classification.',
            'env':[{'name': n, 'purpose':'Detected key; document its purpose before use', 'secret':True} for n in sorted(env - known)]}
    value = architecture.validate({'schema_version':1, 'id': identity, 'name':body.get('name') or 'Captured project baseline',
        'version':'0.1.0', 'description':'Baseline proposed from supported project manifests. Review versions, dependencies and acceptance checks before reuse.',
        'components':list(found.values()), 'decisions':['Keep real environment files and deployment credentials in the centrally configured private project folder.'], 'files':{}})
    return {'template':value, 'evidence':evidence, 'environment_keys':len(env), 'review':architecture.review(value),
        'note':'Proposed template only. Source code, dependency URLs, scripts, environment values and deployment configuration were not copied. Unknown frameworks and custom architecture need manual review.'}
