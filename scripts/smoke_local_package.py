"""Exercise the bundled dashboard/library using disposable state and projects."""
import http.client
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import os


def smoke(binary):
    with tempfile.TemporaryDirectory(prefix='constitution-package-') as folder:
        root = Path(folder).resolve()
        state = root / 'control'
        state.mkdir()
        # Background reconciliation has its own tests; keep this exact-preview
        # packaging smoke deterministic while it exercises activation explicitly.
        (state / 'synchronization.json').write_text(json.dumps({'schema':1,'enabled':False,'paused_projects':[]}))
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        with (root / 'service.log').open('wb') as log:
            child = subprocess.Popen([str(binary), '--state-dir', str(state), 'serve', '--port', str(port)],
                                     stdout=log, stderr=log,
                                     **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
        def request(path, body=None, token=''):
            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=20)
            connection.request('GET' if body is None else 'POST', path,
                               json.dumps(body) if body is not None else None,
                               {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
            response = connection.getresponse()
            status, data = response.status, response.read()
            connection.close()
            return status, data
        try:
            for _ in range(60):
                if child.poll() is not None:
                    raise RuntimeError('Packaged server failed: ' + (root / 'service.log').read_text()[-3000:])
                try:
                    if request('/')[0] == 200: break
                except OSError: time.sleep(.2)
            else: raise RuntimeError('Packaged server startup timeout')
            token = json.loads((state / 'config.json').read_text())['token']
            def api(path, body=None):
                status, data = request('/api/studio/' + path, body, token)
                if status != 200: raise RuntimeError('Packaged studio check failed: ' + data.decode()[:1000])
                return json.loads(data)
            assert request('/api/studio/templates')[0] == 401
            assert request('/studio.js')[0] == 200
            templates = api('templates')['templates']
            assert len(templates) >= 3
            opened = api('file?path=constitution.md')
            body = {'path': 'constitution.md', 'sha256': opened['sha256'], 'content': opened['content'] + '\nKeep a short decision log.\n'}
            preview = api('file-preview', body)
            api('file-save', {**body, 'plan': preview['plan']})
            project = root / 'project'; project.mkdir()
            body = {'project': str(project), 'name': 'package-demo', 'template': templates[0]['template']}
            preview = api('project-preview', body)
            api('project-apply', {**body, 'plan': preview['plan']})
            assert (project / '.ai/architecture.md').is_file()
            preview = api('activation-preview', {})
            api('activate', {'plan': preview['plan']})
            assert request('/api/stop', {'acknowledge_external': True}, token)[0] == 200
            assert child.wait(10) == 0
            return {'authenticated_studio': True, 'bundled_templates': True, 'draft_save': True,
                    'project_apply': True, 'library_activation': True, 'isolated_state': True}
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(10)
