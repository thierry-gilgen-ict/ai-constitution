"""Bounded Claude instruction resolution; importing content never grants access."""
import fnmatch
from pathlib import Path
import re
import os
import platform
if __package__:
    from .clients import version_tuple
else:
    from clients import version_tuple


def imports(body):
    text = re.sub(r'```.*?```|~~~.*?~~~|`[^`]*`|<!--.*?-->', '', body, flags=re.S)
    return [p.replace('\\ ', ' ').rstrip('.,;)') for p in
            re.findall(r'(?<![\w])@((?:\\ |[^\s`"<>])+)', text)]


def rule_paths(body):
    front = re.match(r'^---\s*\n(.*?)\n---', body, re.S)
    if not front or not re.search(r'^paths:', front[1], re.M):
        return []
    field = re.search(r'^paths:\s*(.*?)(?=\n\w+:|\Z)', front[1], re.M | re.S)[1].strip()
    if field.startswith('[') and field.endswith(']'):
        return [p.strip().strip('"\'') for p in field[1:-1].split(',') if p.strip()]
    if field.startswith('-'):
        return [p.strip().strip('"\'') for p in re.findall(r'^\s*-\s*(.+)$', field, re.M)]
    return [field.strip('"\'')] if field else []


def resolve(profile, entry, cfg, report, add, gap, finding, contents, absolute, fingerprint, document, identity):
    base = absolute(profile['home'])
    allowed = [absolute(v) for v in [*cfg['roots'], *cfg['projects'], profile['home']]]
    explicit = {absolute(v) for v in [*cfg['files'], *profile.get('files', [])]}
    if profile.get('account_rules'): explicit.add(absolute(profile['account_rules']))
    options, config_hashes = {}, []

    def permitted(path):
        return path in explicit or any(path.is_relative_to(root) for root in allowed)

    def settings(path, managed=False):
        try:
            value = document(path)
            if not isinstance(value, dict): raise ValueError()
            config_hashes.append([str(path), fingerprint(path)])
            # Never expose env, hooks, credential helpers or arbitrary config values.
            for key in ('claudeMdExcludes',):
                if key in value:
                    items = value[key]
                    if not isinstance(items, list) or len(items)>100 or any(not isinstance(p,str) or len(p)>1000 for p in items): raise ValueError()
                    options.setdefault(key, []).extend(items)
            for plugin in ('agents-md@builtin', 'cc-plugin-agents-md@builtin'):
                mode = value.get('pluginConfigs', {}).get(plugin, {}).get('options', {}).get('instructionFiles')
                if mode and (path.parent == base or managed): options['mode'] = mode
        except (OSError, ValueError, TypeError, AttributeError): gap(path, 'Claude settings are unavailable or invalid')

    settings(base/'settings.json')
    if not base.is_dir():gap(base,'Claude profile directory is unavailable')
    managed_base = Path(os.environ.get('ProgramFiles','C:/Program Files'))/'ClaudeCode' if platform.system()=='Windows' else Path('/Library/Application Support/ClaudeCode') if platform.system()=='Darwin' else Path('/etc/claude-code')
    managed_file = managed_base/'CLAUDE.md'
    entry['account_managed_settings']='unknown; no account database collection'
    if managed_file.exists() and not permitted(managed_file):gap(managed_file,'Organization instructions outside approved scope')
    if permitted(managed_base/'managed-settings.json'):settings(managed_base/'managed-settings.json',managed=True)
    def rules(directory):
        found=[]
        try:absolute(directory)
        except (ValueError,OSError):gap(directory,'Linked Claude rules directory');return []
        if not directory.is_dir():return []
        count=0
        for folder,dirs,files in os.walk(directory,followlinks=False):
            count+=1
            if count>1000 or len(found)>1000:gap(directory,'Claude rule discovery truncated');break
            safe=[]
            for name in dirs:
                try:absolute(Path(folder)/name);safe.append(name)
                except (ValueError,OSError):gap(Path(folder)/name,'Linked Claude rule directory excluded')
            dirs[:]=safe
            found.extend(Path(folder)/name for name in files if name.endswith('.md'))
            if len(found)>1000:found=found[:1000];gap(directory,'Claude rule source limit reached');break
        return sorted(found)
    global_paths = [base/'CLAUDE.md', *rules(base/'rules')]
    for project in report['projects'] or [{'id':None,'path':str(base)}]:
        root = absolute(project.get('resolution_root', project['path']))
        cwd = absolute(profile.get('cwd', project['path']))
        if not cwd.is_relative_to(root) or not cwd.is_dir(): gap(cwd, 'Working directory unavailable or outside this project'); continue
        local_options = dict(options); local_options['claudeMdExcludes'] = list(options.get('claudeMdExcludes', []))
        # Keep each project's configuration independent.
        options.clear(); options.update(local_options)
        settings(root/'.claude/settings.json'); settings(root/'.claude/settings.local.json')
        chain, visited, stack = [], set(), set()

        def include(path, status='expected', depth=0, external=False):
            try: path = absolute(path)
            except (OSError, ValueError): gap(path, 'Linked or invalid Claude source'); return
            if not permitted(path):
                if path.exists(): gap(path, 'Claude source or import outside approved scope')
                return
            if path!=managed_file and any(fnmatch.fnmatch(str(path).replace('\\','/'), p.replace('\\','/')) for p in options.get('claudeMdExcludes', [])): status = 'excluded'
            if path in visited: return
            src = add(path, root if path.is_relative_to(root) else base, 'project' if path.is_relative_to(root) else 'global')
            if not src: return
            visited.add(path)
            body = contents.get(src['id'], '')
            if path==managed_file:src['classification']='managed-policy'
            if 'rules' in path.parts and ('.claude' in path.parts or path.is_relative_to(base/'rules')):
                paths = rule_paths(body)
                if paths: status = 'conditional' if status == 'expected' else status
                src['rule'] = {'paths': paths}
            if external and path.is_relative_to(root) is False and status == 'expected': status = 'requires-approval'
            chain.append({'source':src['id'], 'status':status, 'bytes':src['bytes']})
            if status in ('excluded', 'shadowed'): return
            stack.add(path)
            for name in imports(body):
                if depth >= 4:
                    finding('import-depth', 'Claude import exceeds four hops', src); continue
                dest = Path(name).expanduser()
                if not dest.is_absolute(): dest = path.parent/dest
                try: dest = absolute(dest)
                except (OSError, ValueError): gap(dest, 'Invalid or linked Claude import'); continue
                if not dest.exists(): finding('missing-reference', 'Missing Claude import', src); continue
                if dest in stack:finding('import-cycle','Claude import cycle',src);continue
                child_status = status
                src['references'].append({'path':str(dest),'kind':'import'})
                include(dest, child_status, depth+1, external=path.is_relative_to(root) and not dest.is_relative_to(cwd))
            stack.discard(path)

        mode = options.get('mode', 'claude-md-or-agents-md')
        if mode not in ('claude-md-or-agents-md','claude-md-and-agents-md','claude-md','managed-only'):
            gap(base, 'Unknown Claude instruction selection'); mode = 'claude-md'
        include(managed_file)
        if mode != 'managed-only':
            for path in global_paths: include(path)
        for path in explicit: include(path, 'referenced; loading unknown')
        ancestors = list(reversed(cwd.parents)) + [cwd]
        inside = [p for p in ancestors if p.is_relative_to(root)]
        outside = [p for p in ancestors if not p.is_relative_to(root)]
        for parent in outside:
            for name in ('CLAUDE.md','CLAUDE.local.md','.claude/CLAUDE.md','AGENTS.md'):
                candidate=parent/name
                if candidate.is_file(): gap(candidate, 'Ancestor Claude instruction outside selected scope')
        has_claude = any((p/name).is_file() for p in ancestors for name in ('CLAUDE.md','.claude/CLAUDE.md','CLAUDE.local.md'))
        for directory in inside:
            status = 'excluded' if mode == 'managed-only' else 'expected'
            for name in ('CLAUDE.md','.claude/CLAUDE.md','CLAUDE.local.md'): include(directory/name, status)
            agents = mode == 'claude-md-and-agents-md' or mode == 'claude-md-or-agents-md' and not has_claude
            for name in ('AGENTS.md','.claude/AGENTS.md'):
                include(directory/name, 'expected' if agents and version_tuple(profile.get('client_version')) >= (2,1,277) else 'version-dependent' if agents else 'shadowed')
            for path in rules(directory/'.claude/rules'): include(path, status)
        for src in list(report['sources']):
            path = Path(src['path'])
            if path.is_relative_to(cwd) and path not in visited and src['name'] in ('CLAUDE.md','CLAUDE.local.md'):
                include(path, 'conditional')
        config_fingerprint = identity([profile, config_hashes])
        report['chains'].append({'profile':profile['id'],'client':'claude-code','project':project['id'],'cwd':str(cwd),
                                'sources':chain,'expected_bytes':sum(s['bytes'] for s in chain if s['status']=='expected'),
                                'limit':None,'configuration_fingerprint':config_fingerprint,'loading':'unverified'})
        entry['configuration_fingerprint'] = config_fingerprint
        options.clear(); options.update(local_options)
