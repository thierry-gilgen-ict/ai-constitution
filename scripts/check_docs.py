"""Check local Markdown links without network access or external packages."""
from pathlib import Path
import re
import sys
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]
failures = []
for path in ROOT.rglob("*.md"):
    if any(p in {".git", ".local", "__pycache__"} for p in path.relative_to(ROOT).parts):
        continue
    content = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.S)
    for link in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", content):
        destination = link.split(' "', 1)[0].strip("<>")
        parsed = urllib.parse.urlsplit(destination)
        if parsed.scheme or destination.startswith("#"):
            continue
        target = path.parent / urllib.parse.unquote(parsed.path)
        if not target.exists():
            failures.append(f"{path.relative_to(ROOT)}: {destination}")
if failures:
    print("Broken local links:\n" + "\n".join(failures))
    sys.exit(1)
print("All local Markdown links resolve.")
