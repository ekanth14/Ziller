"""Bounded local public-form validation, abuse control and operator cookies."""
from collections import deque
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from urllib.parse import urlsplit


def operator_cookie(passcode, now=None):
    if not passcode:
        raise ValueError('Operator authentication is not configured')
    stamp = str(int(time.time() if now is None else now))
    nonce = secrets.token_hex(16)
    payload = stamp + '.' + nonce
    signature = hmac.new(passcode.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return payload + '.' + signature


def valid_operator_passcode(value, passcode):
    return bool(passcode) and isinstance(value, str) and hmac.compare_digest(value.strip().encode(), passcode.encode())


def valid_operator_cookie(value, passcode, now=None):
    if not passcode or not isinstance(value, str):
        return False
    try:
        stamp, nonce, signature = value.split('.')
        if not re.fullmatch(r'\d+', stamp) or not re.fullmatch(r'[a-f0-9]{64}', signature):
            return False
        age = (time.time() if now is None else now) - int(stamp)
        if not 0 <= age <= 604800 or not re.fullmatch(r'[a-f0-9]{32}', nonce):
            return False
        expected = hmac.new(passcode.encode(), (stamp + '.' + nonce).encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)
    except (ValueError, TypeError):
        return False


def validate_proposal(body):
    if not isinstance(body, dict):
        raise ValueError('Proposal must be a JSON object')
    limits = {'name': 120, 'email': 254, 'github': 300, 'linkedin': 300,
              'website': 512, 'track': 120, 'message': 4000, 'fax': 0}
    for key, value in body.items():
        if key not in limits or not isinstance(value, str) or len(value) > limits[key]:
            raise ValueError('Invalid or oversized proposal field')
        if any(ord(c) < 32 and c not in '\r\n\t' for c in value):
            raise ValueError('Proposal contains unsupported control characters')
    result = {key: body.get(key, '').strip() for key in limits if key != 'fax'}
    if not result['name'] or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', result['email']):
        raise ValueError('Name and valid email are required')
    if len(result['message']) < 10:
        raise ValueError('A substantive proposal message is required')
    for key, host in (('github', 'github.com'), ('linkedin', 'linkedin.com')):
        value = result[key]
        if not value:
            raise ValueError('Required profile is missing')
        if '://' in value:
            url = urlsplit(value)
            if url.scheme != 'https' or url.hostname not in {host, 'www.' + host} or url.username or url.password:
                raise ValueError('Profile URL must use its expected HTTPS host')
        elif not re.fullmatch(r'@?[A-Za-z0-9][A-Za-z0-9_-]{0,79}', value):
            raise ValueError('Invalid profile handle')
    if result['website']:
        url = urlsplit(result['website'])
        if url.scheme != 'https' or not url.hostname or url.username or url.password:
            raise ValueError('Website must be an HTTPS URL')
    result['email'] = result['email'].lower()
    return result


class FormGuard:
    """Per-process quotas; serverless deployments still need shared edge limits."""
    def __init__(self):
        self.lock = threading.Lock()
        self.events = deque()
        self.duplicates = {}

    def accept(self, body, client, now=None):
        now = time.monotonic() if now is None else now
        digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        with self.lock:
            while self.events and now - self.events[0][0] >= 60:
                self.events.popleft()
            self.duplicates = {k: v for k, v in self.duplicates.items() if now - v < 900}
            if len(self.events) >= 100 or sum(c == client for _, c in self.events) >= 5:
                return False
            if (client, digest) in self.duplicates or len(self.duplicates) >= 10000:
                return False
            self.events.append((now, client))
            self.duplicates[(client, digest)] = now
            return True
