"""One-use pairing and revocable, separately scoped controller credentials."""
import hashlib
import hmac
import secrets
import time
import uuid


def hashed(token):
    return hashlib.sha256(token.encode()).hexdigest()


def create_pairing(config):
    code = secrets.token_urlsafe(32)
    expires = time.time() + 300
    config['pairing'] = {'sha256': hashed(code), 'expires': expires}
    return {'code': code, 'expires': expires}


def redeem(config, code, name):
    current = config.get('pairing')
    if (not isinstance(code, str) or not current or current['expires'] < time.time()
            or not hmac.compare_digest(current['sha256'], hashed(code))):
        raise ValueError('Pairing code expired, already used or invalid; create a new one on the worker')
    if not isinstance(name, str) or not 1 <= len(name) <= 60:
        raise ValueError('Controller name must have 1–60 characters')
    identity = uuid.uuid4().hex
    management, inference = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    config['controllers'][identity] = {'name': name, 'management_hash': hashed(management),
                                      'inference_hash': hashed(inference), 'created': time.time()}
    config['pairing'] = None
    return {'controller_id': identity, 'token': management, 'inference_token': inference}


def principal(config, token, *, inference=False):
    key = 'inference_hash' if inference else 'management_hash'
    for identity, record in config.get('controllers', {}).items():
        if hmac.compare_digest(record[key], hashed(token)):
            return identity
    return None


def rotate(config, identity):
    if identity not in config['controllers']:
        raise ValueError('Unknown controller')
    management, inference = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    config['controllers'][identity].update(management_hash=hashed(management), inference_hash=hashed(inference))
    return {'controller_id': identity, 'token': management, 'inference_token': inference}
