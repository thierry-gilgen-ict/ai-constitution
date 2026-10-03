"""Immutable private template revisions and project migration previews."""
import re
from scripts import architecture, constitution as kit
from scripts.catalog import digest, json_bytes
from .storage import atomic


def archive(studio, value):
    value = architecture.validate(value)
    identity = digest(json_bytes(value))
    path = studio.base / 'template-versions' / value['id'] / (identity + '.json')
    kit.no_links(path)
    if path.exists() and kit.read_json(path) != value: raise ValueError('Stored template revision was changed')
    if not path.exists(): atomic(path, value)
    return identity


def versions(studio, identity):
    architecture.identifier(identity)
    results = []
    current = studio.draft / 'templates/architectures' / (identity + '.json')
    if current.exists(): archive(studio, kit.read_json(current))
    for path in (studio.base / 'template-versions' / identity).glob('*.json'):
        kit.no_links(path); value = architecture.validate(kit.read_json(path))
        sha = digest(json_bytes(value))
        if path.stem != sha: raise ValueError('Stored template revision integrity changed')
        results.append({'revision': sha, 'version': value['version'], 'description': value['description'], 'template': value})
    return {'versions': sorted(results, key=lambda r: tuple(map(int, r['version'].split('.'))), reverse=True)}
