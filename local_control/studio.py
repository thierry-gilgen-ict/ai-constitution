"""Private architecture and instruction workspace. Never execute draft source code."""
import base64
import difflib
import json
from pathlib import Path
import sys
import tempfile

from scripts import constitution as kit, architecture, releases
from scripts.catalog import atomic_bytes, digest, json_bytes

MAX_EDIT = 512 * 1024
PAGE_SIZE = 64000


def bundled_source():
    return Path(sys._MEIPASS) / 'library' if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]


def difference(name, before, after):
    return {'path': name, 'status': 'new' if before is None else 'changed',
            'diff': ''.join(difflib.unified_diff((before or b'').decode('utf-8').splitlines(True),
                after.decode('utf-8').splitlines(True), fromfile='before/' + name, tofile='after/' + name))[:60000]}


class Studio:
    def __init__(self, root, *, source=None, state=None):
        self.base = Path(root) / 'studio'
        self.draft = self.base / 'library'
        self.history = self.base / 'state'
        self.state = Path(state) if state is not None else Path(root).parent / 'state'
        self.source = Path(source) if source is not None else bundled_source()

    def initialize(self):
        marker = self.base / 'origin.json'
        kit.no_links(marker)
        if marker.exists():
            return
        payload = releases.files(self.source)
        kit.validate(self.source)
        kit.build(self.source, check=True)
        # An interrupted first copy can be retried; never overwrite a partial draft
        # that somebody edited meanwhile.
        for name, data in payload.items():
            path = kit.safe_path(self.draft, name)
            if path.exists() and path.read_bytes() != data:
                raise ValueError('An unfinished library draft has local changes. Preserve it before initializing again.')
        for name, data in payload.items():
            atomic_bytes(kit.safe_path(self.draft, name), data)
        atomic_bytes(marker, json_bytes(releases.manifest(payload)))

    def payload(self):
        return releases.files(self.draft)

    def generated(self):
        return set(kit.render(self.draft))

    def editable(self, name, size=0):
        if not releases.allowed(name) or size > MAX_EDIT:
            return False
        if name in self.generated() or name == 'registry/catalog.json':
            return False
        # Source is visible for transparency, but editing executable code belongs
        # in the normal repository/editor review workflow.
        return (Path(name).suffix in {'.md', '.mdc', '.json', '.txt'}
                and not name.startswith(('scripts/', 'local_control/', 'packaging/'))
                and not name.startswith('requirements-'))

    def file_path(self, name):
        if not isinstance(name, str) or not releases.allowed(name):
            raise ValueError('Choose a library file from the file browser')
        return kit.safe_path(self.draft, name)

    def files(self):
        payload = self.payload()
        generated = self.generated()
        origin = kit.read_json(self.base / 'origin.json')['files']
        return {'files': [{'path': n, 'bytes': len(b), 'editable': self.editable(n, len(b)),
                           'generated': n in generated, 'modified': digest(b) != origin.get(n)} for n,b in payload.items()],
                'scope': 'Private library draft. Saving here does not activate client instructions or change the public checkout.',
                'draft': str(self.draft)}

    def read(self, name, offset=0):
        path = self.file_path(name)
        if not path.is_file() or path.stat().st_size > 32 * 1024 * 1024:
            raise ValueError('File is missing or exceeds the 32 MiB viewer limit')
        data = path.read_bytes()
        result = {'path': name, 'sha256': digest(data), 'editable': self.editable(name, len(data)), 'bytes': len(data)}
        if path.suffix == '.png':
            return {**result, 'image': 'data:image/png;base64,' + base64.b64encode(data).decode()}
        content = data.decode('utf-8')
        if type(offset) is not int or offset < 0 or offset > len(content):
            raise ValueError('Invalid file page')
        # Editable files are always returned whole; immutable catalog pages are bounded.
        end = len(content) if result['editable'] else offset + PAGE_SIZE
        return {**result, 'content': content[offset:end], 'offset': offset, 'characters': len(content),
                'next': end if end < len(content) else None,
                'reason': ('Edit registry/models.json and registry/routes.json, or constitution.md; saving rebuilds generated files.'
                           if name in self.generated() else 'Large catalogs and executable source are view-only. Use the CLI/editor for these changes.') if not result['editable'] else ''}

    def staged(self, edits):
        payload = self.payload()
        payload.update(edits)
        with tempfile.TemporaryDirectory() as folder:
            # macOS exposes its OS temporary directory through /var -> /private/var.
            # Canonicalize our newly created scratch root, not user-selected paths.
            candidate = Path(folder).resolve()
            for name, data in payload.items():
                atomic_bytes(kit.safe_path(candidate, name), data)
            # These are trusted imported functions. No subprocess/import from the draft.
            try:
                kit.validate(candidate)
                components = candidate / 'templates/architecture-components.json'
                if components.exists():
                    items = kit.read_json(components)
                    architecture.validate({'schema_version': 1, 'id': 'catalog', 'name': 'Catalog', 'version': '1.0.0',
                                           'description': 'Reusable components', 'components': items['components']})
                for name, body in kit.render(candidate).items():
                    payload[name] = body.encode('utf-8')
            except (KeyError, TypeError, IndexError, UnicodeError) as error:
                raise ValueError('Invalid library structure. Check required fields and references in this file.') from error
        return payload

    def file_plan(self, name, content, expected):
        path = self.file_path(name)
        if not isinstance(content, str) or not self.editable(name, len(content.encode('utf-8'))):
            raise ValueError('This file is view-only or exceeds the 512 KiB editor limit')
        before = path.read_bytes() if path.exists() else None
        if expected != (digest(before) if before is not None else None):
            raise ValueError('File changed since opening. Reload it before saving.')
        architecture.clean_text(content)
        if path.suffix == '.json':
            try: json.loads(content)
            except ValueError as error: raise ValueError('Invalid JSON: ' + str(error)) from error
        payload = self.staged({name: content.encode('utf-8')})
        current = self.payload()
        writes = {self.file_path(n): b for n,b in payload.items() if current.get(n) != b}
        signature = {'before': releases.manifest(current), 'after': releases.manifest(payload)}
        return {'plan': digest(json_bytes(signature)), 'changes': [difference(n, current.get(n), b) for n,b in payload.items() if current.get(n) != b],
                'note': 'Save to your private draft. Generated routing and adapters are rebuilt with this change.'}, writes

    def save(self, body):
        preview, writes = self.file_plan(body.get('path'), body.get('content'), body.get('sha256'))
        if not body.get('plan') or body['plan'] != preview['plan']:
            raise ValueError('Library changed since preview. Review the change again.')
        return kit.transaction(self.history, writes)

    def templates(self):
        result = []
        for path in sorted((self.draft / 'templates/architectures').glob('*.json')):
            kit.no_links(path)
            value = architecture.validate(kit.read_json(path))
            result.append({'template': value, 'sha256': digest(path.read_bytes()), 'review': architecture.review(value)})
        return {'templates': result, 'components': kit.read_json(self.draft / 'templates/architecture-components.json')['components'],
                'roles': architecture.ROLES}

    def template_body(self, body):
        value = architecture.validate(body.get('template'))
        return {**body, 'path': 'templates/architectures/' + value['id'] + '.json',
                'content': json_bytes(value).decode('utf-8')}

    def refresh_plan(self):
        """Merge a new application bundle into untouched draft files, preserving edits."""
        source, current = releases.files(self.source), self.payload()
        origin_path = self.base / 'origin.json'
        origin = kit.read_json(origin_path)
        edits, conflicts = {}, []
        generated = self.generated()
        for name, after in source.items():
            before = current.get(name)
            if before == after or name in generated:
                continue
            if before is None or digest(before) == origin['files'].get(name):
                edits[name] = after
            elif digest(after) != origin['files'].get(name):
                conflicts.append(name)
        payload = self.staged(edits)
        writes = {self.file_path(n): b for n,b in payload.items() if current.get(n) != b}
        writes[origin_path] = json_bytes(releases.manifest(source))
        return {'plan': digest(json_bytes({'before': releases.manifest(current), 'source': releases.manifest(source), 'origin': origin})),
                'changes': [difference(n, current.get(n), b) for n,b in payload.items() if current.get(n) != b and Path(n).suffix != '.png'],
                'conflicts': conflicts, 'retained': sorted(set(current) - set(source)),
                'note': 'Refresh unchanged files from this application version. Customized files and removed upstream files stay in your draft.'}, writes

    def dispatch(self, operation, body=None, query=None):
        query = query or {}
        # Serialize edits, initialization and previews across browser tabs/processes.
        with kit.state_lock(self.history):
            self.initialize()
            if body is None:
                if operation == 'files': return self.files()
                if operation == 'file': return self.read(query.get('path', [''])[0], int(query.get('offset', ['0'])[0]))
                if operation == 'templates': return self.templates()
                if operation == 'history':
                    items = []
                    for path in sorted((self.history / 'transactions').glob('*.json'), reverse=True)[:20]:
                        record = kit.read_json(path)
                        items.append({'snapshot': path.stem, 'state': record['state'], 'files': len(record['files'])})
                    return {'snapshots': items}
                raise ValueError('Unknown studio read operation')
            if operation == 'file-preview': return self.file_plan(body.get('path'), body.get('content'), body.get('sha256'))[0]
            if operation == 'file-save': return self.save(body)
            if operation == 'template-validate':
                value = architecture.validate(body.get('template'))
                return {'template': value, 'review': architecture.review(value)}
            if operation == 'template-preview':
                b = self.template_body(body)
                return {**self.file_plan(b['path'], b['content'], b.get('sha256'))[0], 'review': architecture.review(body['template'])}
            if operation == 'template-save': return self.save(self.template_body(body))
            if operation in {'project-preview', 'project-apply'}:
                value = architecture.validate(body.get('template'))
                if not isinstance(body.get('project'), str) or not Path(body['project']).is_absolute():
                    raise ValueError('Enter the full path to an existing project directory')
                if operation == 'project-preview':
                    return architecture.plan(kit, self.draft, self.state, Path(body['project']), value, body.get('name'))[0]
                return architecture.apply(kit, self.draft, self.state, Path(body['project']), value, body.get('name'), body.get('plan'))
            if operation == 'activation-preview': return kit.upgrade(self.draft, self.state, dry_run=True)
            if operation == 'activate':
                if not isinstance(body.get('plan'), str): raise ValueError('Preview activation first')
                return kit.upgrade(self.draft, self.state, expected_plan=body['plan'])
            if operation in {'refresh-preview', 'refresh-apply'}:
                preview, writes = self.refresh_plan()
                if operation == 'refresh-preview': return preview
                if preview['conflicts']:
                    raise ValueError('Customized files also changed upstream. Reconcile these files in your editor before refreshing: ' + ', '.join(preview['conflicts']))
                if body.get('plan') != preview['plan']: raise ValueError('Library changed. Preview the refresh again.')
                return kit.transaction(self.history, writes)
            if operation == 'rollback':
                return kit._rollback(self.history, body.get('snapshot', ''))
            raise ValueError('Unknown studio operation')
