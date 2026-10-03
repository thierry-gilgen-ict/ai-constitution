"""Real CLI transcripts using disposable installation targets only."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def transcripts():
    with tempfile.TemporaryDirectory(prefix='constitution-docs-') as temporary:
        base = Path(temporary).resolve()
        state, demo_home = base / 'state', base / 'home'
        demo_home.mkdir()
        prefix = [sys.executable, str(ROOT / 'scripts/constitution.py'), '--state-dir', str(state)]
        def run(args):
            return json.loads(subprocess.check_output([*prefix, *args], cwd=ROOT, text=True, encoding='utf-8', timeout=60))
        checked = run(['check'])
        installation = run(['install', '--home', str(demo_home), '--dry-run'])
        changes = [file for platform in installation for file in platform['files']]
        def normalized(value):
            if isinstance(value, list):
                return [normalized(item) for item in value]
            if isinstance(value, dict):
                return {key: normalized(item) for key, item in value.items()}
            if not isinstance(value, str):
                return value
            value = value.replace('\\', '/')
            return value.replace(demo_home.as_posix(), '/home/demo').replace(base.as_posix(), '/home/demo/.config/ai-constitution').replace(ROOT.as_posix(), '/home/demo/source/ai-constitution')
        return {
            'check': {'command': 'python scripts/constitution.py check', 'output': json.dumps(checked, indent=2)},
            'install': {'command': 'python scripts/constitution.py install --dry-run', 'output': json.dumps({'status': 'preview', 'proposed_files': len(changes), 'files': normalized(changes[:6])}, indent=2), 'note': 'Summary of actual dry-run output. Paths normalized; six proposed files shown.'},
        }


if __name__ == '__main__':
    print(json.dumps(transcripts()))
