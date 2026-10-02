"""Bounded coding fixture evaluation without executing model-supplied Python."""
import ast
import json
import platform
import tempfile
import time
from pathlib import Path
from . import compatibility, hardware
from .storage import atomic
from .transport import connect

TASK = '''Fix clamp.py. Return only a JSON object with keys path and content. path must be clamp.py.
The file currently contains:
def clamp(value, lower, upper):
    return value
Correct it so values below lower return lower, above upper return upper, and otherwise return value.
Use one function named clamp with the three given arguments, return, if/else, comparisons, min/max only. No imports or other functions.'''


def check_patch(text, directory):
    value = json.loads(text)
    if not isinstance(value, dict) or set(value) != {'path', 'content'} or value['path'] != 'clamp.py' or not isinstance(value['content'], str) or len(value['content']) > 8192:
        raise ValueError('Fixture patch must contain exactly clamp.py and bounded source text')
    tree = ast.parse(value['content'])
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        raise ValueError('Fixture permits one function only')
    function = tree.body[0]
    if (function.name != 'clamp' or [a.arg for a in function.args.args] != ['value', 'lower', 'upper']
            or function.decorator_list or function.args.defaults or function.args.kwonlyargs or function.args.vararg or function.args.kwarg or function.args.posonlyargs):
        raise ValueError('Unexpected fixture function signature')
    permitted = (ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return, ast.If, ast.IfExp,
                 ast.Compare, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq, ast.Name, ast.Load, ast.Call, ast.Constant)
    nodes = list(ast.walk(tree))
    if len(nodes) > 160 or any(not isinstance(n, permitted) for n in nodes):
        raise ValueError('Patch is outside the bounded fixture grammar')
    def expression(node, env):
        if isinstance(node, ast.Name) and node.id in env:
            return env[node.id]
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return node.value
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ('min', 'max') and 1 <= len(node.args) <= 3 and not node.keywords:
            values = [expression(a, env) for a in node.args]
            return min(values) if node.func.id == 'min' else max(values)
        if isinstance(node, ast.Compare):
            left = expression(node.left, env)
            for operation, right_node in zip(node.ops, node.comparators):
                right = expression(right_node, env)
                passed = {ast.Lt: lambda: left < right, ast.LtE: lambda: left <= right,
                          ast.Gt: lambda: left > right, ast.GtE: lambda: left >= right,
                          ast.Eq: lambda: left == right, ast.NotEq: lambda: left != right}[type(operation)]()
                if not passed: return False
                left = right
            return True
        if isinstance(node, ast.IfExp):
            return expression(node.body if expression(node.test, env) else node.orelse, env)
        raise ValueError('Unsupported fixture expression')
    def statements(body, env):
        for statement in body:
            if isinstance(statement, ast.Return):
                return True, expression(statement.value, env)
            if isinstance(statement, ast.If):
                returned, value = statements(statement.body if expression(statement.test, env) else statement.orelse, env)
                if returned: return returned, value
            else:
                raise ValueError('Unsupported fixture statement')
        return False, None
    cases = [(-5,0,10,0),(5,0,10,5),(15,0,10,10),(0,0,10,0),(10,0,10,10),(-2,-5,-1,-2),(-10,-5,-1,-5),(4,3,3,3)]
    passes = sum(statements(function.body, dict(zip(('value','lower','upper'), case[:3]))) == (True, case[3]) for case in cases)
    (directory / 'clamp.py').write_text(value['content'], encoding='utf-8')
    return {'passed': passes, 'total': len(cases), 'method': 'bounded AST interpreter; model code was not executed'}


def benchmark(control, endpoint, progress=lambda _: None):
    from .core import model_name
    model_name(endpoint['model'])
    record = {'schema': 1, 'model': endpoint['model'], 'node': endpoint['node'], 'created': time.time(),
              'level': 'unverified', 'status': 'failed', 'context': control.config['context'], 'fixture_version': 1}
    try:
        progress('Testing function calls and full-history tool results')
        contract = compatibility.qualify(control, endpoint)
        record.update(contract, level='protocol-tested')
        try:
            h = hardware.run_fit(control.root, ['--json','system']) if endpoint['node'] in ('local','local-cpu') else control.rpc(control.node(endpoint['node']), '/hardware', timeout=100)
            h = h.get('system', h)
            record['hardware'] = {k: h.get(k) for k in ('cpu_name','gpu_name','gpu_vram_gb','total_ram_gb')}
        except (ValueError, OSError):
            record['hardware'] = {'status': 'unavailable'}
        progress('Running a disposable coding fixture; no model-generated code is executed')
        start, first_token, chunks, usage = time.monotonic(), None, [], {}
        conn, response = connect(control.node(endpoint['node']), '/v1/responses', {'model': endpoint['model'], 'input': TASK,
            'stream': True, 'store': False, 'max_output_tokens': 1024, 'reasoning': {'effort': 'low'}, 'truncation': 'disabled'}, timeout=240)
        try:
            total = 0
            for line in response:
                total += len(line)
                if total > 2 * 1024 * 1024 or time.monotonic() - start > 240:
                    raise ValueError('Evaluation exceeded its output or time budget')
                if not line.startswith(b'data: ') or line.strip() == b'data: [DONE]': continue
                event = json.loads(line[6:])
                if event.get('type') == 'response.output_text.delta':
                    if first_token is None: first_token = time.monotonic() - start
                    chunks.append(event.get('delta',''))
                if event.get('type') == 'response.completed': usage = event.get('response',{}).get('usage',{})
        finally:
            conn.close()
        elapsed = time.monotonic() - start
        record.update(first_text_seconds=round(first_token,3) if first_token is not None else None, elapsed_seconds=round(elapsed,3),
                      output_tokens=usage.get('output_tokens'), output_tokens_per_second=round(usage['output_tokens']/elapsed,2) if usage.get('output_tokens') else None)
        with tempfile.TemporaryDirectory(prefix='constitution-eval-') as folder:
            record['coding'] = check_patch(''.join(chunks).strip(), Path(folder))
        resident = next((m for m in control.rpc(control.node(endpoint['node']), '/api/ps').get('models',[]) if m['name'] == endpoint['model']), {})
        record['resident_gpu_bytes_after'] = resident.get('size_vram')
        record['peak_memory'] = 'not sampled; residency after the request is reported separately'
        if record['coding']['passed'] == record['coding']['total']:
            record.update(status='passed', level='coding-tested', coding_quality='bounded clamp fixture only; not a general coding ranking')
    except Exception as error:
        record['failure'] = type(error).__name__
    identity = __import__('uuid').uuid4().hex
    atomic(control.root / 'evaluations' / (identity + '.json'), record)
    return record
