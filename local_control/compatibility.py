"""Small, explicit protocol checks; no claim of coding quality or exact tokenization."""
import json
import time


def qualify(control, endpoint):
    node = control.node(endpoint['node'])
    info = control.probe(endpoint)
    tags = control.rpc(node, '/api/tags').get('models', [])
    model = next((m for m in tags if m['name'] == endpoint['model']), None)
    version = control.rpc(node, '/api/version').get('version')
    resident = next((m for m in control.rpc(node, '/api/ps').get('models', []) if m['name'] == endpoint['model']), None)
    if not model or not model.get('digest') or not version:
        raise ValueError('Runtime did not return a model digest and version for compatibility evidence')
    if not resident or resident.get('context_length', 0) < control.config['context']:
        raise ValueError('Resident model context is smaller than the coding session contract')
    tool = {'type': 'function', 'name': 'constitution_probe', 'description': 'Return the requested harmless readiness value.',
            'parameters': {'type': 'object', 'properties': {'value': {'type': 'string'}}, 'required': ['value'], 'additionalProperties': False}}
    messages = [{'role': 'user', 'content': 'Call constitution_probe with value ready. Do not answer in text before calling it.'}]
    common = {'model': endpoint['model'], 'stream': False, 'store': False, 'tools': [tool],
              'max_output_tokens': 512, 'reasoning': {'effort': 'low'}, 'truncation': 'disabled'}
    start = time.monotonic()
    first = control.rpc(node, '/v1/responses', {**common, 'input': messages}, timeout=240)
    calls = [v for v in first.get('output', []) if v.get('type') == 'function_call']
    if len(calls) != 1 or calls[0].get('name') != tool['name'] or not calls[0].get('call_id'):
        raise ValueError('Model failed the function-call protocol check; choose another coding model')
    try:
        arguments = json.loads(calls[0]['arguments'])
    except (ValueError, KeyError, TypeError):
        raise ValueError('Model produced invalid tool arguments') from None
    if arguments != {'value': 'ready'}:
        raise ValueError('Model failed the tool-argument check')
    result = {'type': 'function_call_output', 'call_id': calls[0]['call_id'], 'output': 'LOCAL_TOOL_OK'}
    second = control.rpc(node, '/v1/responses', {**common, 'input': [*messages, *first['output'], result,
                         {'role': 'user', 'content': 'Reply with LOCAL_TOOL_OK from the tool result. Do not call more tools.'}]}, timeout=240)
    text = ''.join(c.get('text', '') for item in second.get('output', []) if item.get('type') == 'message' for c in item.get('content', []))
    if 'LOCAL_TOOL_OK' not in text:
        raise ValueError('Model failed the full-history tool-result replay check')
    return {'model_digest': model['digest'], 'runtime_version': version, 'context': resident['context_length'],
            'quantization': info.get('details', {}).get('quantization_level', model.get('details', {}).get('quantization_level')),
            'api': 'responses', 'function_tools': True, 'full_history': True,
            'cpu_verified': bool(endpoint.get('cpu')), 'verified_at': time.time(),
            'tool_round_trip_seconds': round(time.monotonic() - start, 3), 'level': 'protocol-tested',
            'coding_quality': 'not evaluated'}


def current(control, endpoint):
    contract = endpoint.get('contract')
    if not contract or contract.get('context', 0) < control.config['context'] or not contract.get('function_tools'):
        return False
    node = control.node(endpoint['node'])
    version = control.rpc(node, '/api/version', timeout=5).get('version')
    model = next((m for m in control.rpc(node, '/api/tags', timeout=8).get('models', []) if m['name'] == endpoint['model']), None)
    return bool(model and contract['model_digest'] == model.get('digest') and contract['runtime_version'] == version)
