"""Build the illustrated manual from reviewed capture captions and metadata."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def managed(path, key, body, *, before=None):
    text = path.read_text(encoding='utf-8')
    start, end = f'<!-- screenshots:{key}:begin -->', f'<!-- screenshots:{key}:end -->'
    block = start + '\n\n' + body.strip() + '\n\n' + end
    if start in text:
        text = re.sub(re.escape(start) + r'.*?' + re.escape(end), lambda _: block, text, flags=re.S)
    elif before:
        if before not in text:
            raise ValueError(f'Missing documentation insertion point in {path.name}: {before}')
        text = text.replace(before, block + '\n\n' + before, 1)
    else:
        text = text.rstrip() + '\n\n' + block + '\n'
    path.write_text(text, encoding='utf-8')


def build(root=ROOT):
    manifest = json.loads((root / 'docs/assets/screenshots/manifest.json').read_text(encoding='utf-8'))
    directory = root / 'docs/manual'
    directory.mkdir(exist_ok=True)
    intro = (f"Actual Local Control UI **{manifest['ui_version']}**, captured with fictional accounts, paths, "
             "models and usage. Performance numbers and update versions are examples, not benchmarks or release announcements. "
             "CLI images are rendered transcripts from real isolated commands. [How these images are made](../screenshot-maintenance.md).\n")
    index = ['# Illustrated manual', '', intro, 'Choose a workflow. Each chapter shows the controls, the next step and the relevant limitation. Click an image to inspect its original size.', '', '| Workflow | Images | Detailed guide |', '| --- | ---: | --- |']
    for chapter, (title, guide) in manifest['chapters'].items():
        entries = [v for v in manifest['entries'] if v['chapter'] == chapter]
        index.append(f'| [{title}]({chapter}.md) | {len(entries)} | [Instructions](../{guide}) |')
        lines = [f'# {title}', '', '[All workflows](README.md) · ' + f'[Detailed instructions](../{guide})', '', intro]
        for entry in entries:
            lines.extend([f"## {entry['title']}", '', entry['caption'], '', f"![{entry['title']} — demonstration data, UI {manifest['ui_version']}](../assets/screenshots/{entry['id']}.png)", ''])
        if chapter == 'toolkit':
            lines.extend(['## External application captures', '', 'The dashboard shows connection instructions; these external interfaces still need actual application or OS screenshots. They are **pending**, not represented by mockups.', '', '| Interface | Status | Instructions |', '| --- | --- | --- |'])
            for capture in manifest['external_captures']:
                lines.append(f"| {capture['title']} | {capture['status']} | [Guide](../../{capture['guide']}) |")
            lines.extend(['', 'Use the linked guides now. See the [capture checklist](../screenshot-maintenance.md#external-applications) to contribute a reviewed screenshot.', ''])
        lines.extend(['---', '', '[Back to all workflows](README.md)', ''])
        (directory / (chapter + '.md')).write_text('\n'.join(lines), encoding='utf-8')
    index.extend(['', f"**{len(manifest['entries'])} images · {len(manifest['pages'])} dashboard pages · desktop, tablet and small-screen layouts.**", '', 'For copyable installation commands, use [Getting started](../getting-started.md). For failures, use [Progress and recovery](recovery.md). External application and native OS captures remain [explicitly pending](toolkit.md#external-application-captures).', '', 'These images explain workflows. They do not verify real hardware, subscriptions, installers or a running agent’s instruction loading. See the [acceptance matrix](../compatibility-matrix.md) for that evidence.', ''])
    (directory / 'README.md').write_text('\n'.join(index), encoding='utf-8')
    managed(root / 'docs/README.md', 'manual-summary', f"**[Illustrated manual](manual/README.md)** · {len(manifest['entries'])} images of the actual UI, with fictional data and step-by-step captions.", before='| I want to… | Guide |')
    managed(root / 'docs/provenance.md', 'capture-summary', f"The current [illustrated manual](manual/README.md) contains **{len(manifest['entries'])} captures of UI {manifest['ui_version']}**. Dashboard images use synthetic data; CLI images render real isolated commands.", before='## Dashboard screenshots and CLI transcripts')
    lookup = {v['id']: v for v in manifest['entries']}
    def tile(id):
        value = lookup[id]
        return f"**[{value['title']}](docs/manual/{value['chapter']}.md)**<br>[![{value['title']} — demonstration data](docs/assets/screenshots/{id}.png)](docs/assets/screenshots/{id}.png)"
    cards = ['## See it before setting it up', '', f"Actual UI **{manifest['ui_version']}**, with fictional data. Open an image at full size, or follow the **[80-image illustrated manual](docs/manual/README.md)**. Example releases and performance figures are simulated.", '', '| Models and projects | Maintenance and visibility |', '| --- | --- |']
    for a, b in [('overview', 'architectures'), ('accounts', 'workers'), ('updates', 'vault')]:
        cards.append('| ' + tile(a) + ' | ' + tile(b) + ' |')
    cards[2] = cards[2].replace('80-image', f"{len(manifest['entries'])}-image")
    cards.extend(['', '<details>', f"<summary>Explore all {len(manifest['pages'])} dashboard pages</summary>", ''])
    for id, title in manifest['pages'].items():
        cards.extend([f"### [{title}](docs/manual/{id}.md)", '', f"![{title} — fictional documentation data, UI {manifest['ui_version']}](docs/assets/screenshots/{id}.png)", ''])
    cards.extend(['</details>', '', '[Capture provenance](docs/provenance.md) · [Refresh screenshots](docs/screenshot-maintenance.md) · [External application checklist](docs/manual/toolkit.md#external-application-captures)'])
    managed(root / 'README.md', 'gallery', '\n'.join(cards), before='## Five-minute start')
    # Keep focused images beside copyable instructions, rather than a disconnected picture appendix.
    placements = {
        'getting-started.md': [('check', 'toolkit-check', '## Confirm activation'), ('onboard', 'project-preview', '## Grok Bots')],
        'local-control.md': [('overview', 'overview', '## Codex and Cursor'), ('connect', 'connect-launch', '## What Gaming mode guarantees'), ('gaming', 'gpu-draining', '## Choose models using evidence'), ('fit', 'model-fit', '## Add machines')],
        'project-templates.md': [('editor', 'template-editor', '## What a project receives'), ('revisions', 'template-revisions', '## Revision policies and inheritance')],
        'constitution-studio.md': [('edit', 'constitution-edit', '## What can be edited'), ('history', 'constitution-history', '## Upgrade and recovery')],
        'control-center.md': [('projects', 'projects', '## Applications, subscriptions and logins'), ('accounts', 'accounts', '## Storage and worker installation'), ('storage', 'storage-preview', '## Central private configuration and backups'), ('vault', 'vault', '## Capture a reusable architecture')],
        'windows-worker.md': [('commands', 'worker-windows', '## Stop, update or remove')],
        'driver-maintenance.md': [('update', 'driver-update', '## Platform coverage')],
        'encrypted-backups.md': [('encryption', 'backup-encryption', '## Retention'), ('restore', 'backup-restore-preview', '## Schedules and recovery')],
        'workspace-upgrades.md': [('updates', 'updates', '## Maintain the model catalog'), ('measurements', 'insights', '## Progress and recovery'), ('notifications', 'notifications', None)],
        'local-models.md': [('fit', 'model-fit', None)],
        'updates.md': [('restart', 'update-restart', None)],
        'desktop-preview.md': [('packages', 'worker-download', None)],
    }
    for filename, slots in placements.items():
        for key, id, before in slots:
            value = lookup[id]
            body = (f"**In the dashboard · {value['title']}.** {value['caption']}\n\n"
                    f"![{value['title']} — demonstration data, UI {manifest['ui_version']}](assets/screenshots/{id}.png)\n\n"
                    f"[Illustrated walkthrough](manual/{value['chapter']}.md) · Fictional data; UI {manifest['ui_version']}.")
            managed(root / 'docs' / filename, key, body, before=before)
    print(f"Built {len(manifest['chapters'])} illustrated chapters from {len(manifest['entries'])} captures.")


if __name__ == '__main__':
    build()
