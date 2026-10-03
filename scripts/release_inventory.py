"""Review or refresh the public release file inventory from Git's publishable set."""
import argparse
import json
from pathlib import Path
import subprocess
from releases import allowed, INVENTORY

ROOT = Path(__file__).resolve().parents[1]


def expected(root):
    result = subprocess.run(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'],
                            cwd=root, capture_output=True, check=True)
    names = {n for n in result.stdout.decode('utf-8').split('\0') if n and allowed(n)}
    names.add(INVENTORY)
    return {'schema_version': 1, 'files': sorted(names)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='Refresh names; review the diff before publishing')
    args = parser.parse_args()
    document = expected(ROOT)
    path = ROOT / INVENTORY
    if args.write:
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')
        print('Public release inventory refreshed; review the diff.')
    elif not path.exists() or json.loads(path.read_text()) != document:
        raise SystemExit('Public release inventory is stale; run python scripts/release_inventory.py --write and review.')
    else:
        print('Public release inventory matches the publishable source set.')
