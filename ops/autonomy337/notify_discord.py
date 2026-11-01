#!/usr/bin/env python3
"""Channel-scoped webhook notification with exact message readback.

Credential remains in a protected root-owned file. No bot credential is needed.
Unchanged healthy reports are coalesced for 24h; alerts repeat hourly.
This is NOT an independent absent-heartbeat watchdog.
"""
import importlib.util
import json
import pathlib
import re
import sys
import time
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('autonomy', HERE / 'autonomy.py')
assert spec is not None and spec.loader is not None
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


def deliver(config, status):
    if type(status.get('ok')) is not bool or type(status.get('at')) is not int:
        raise ValueError('invalid notification')
    errors = status.get('errors')
    if not isinstance(errors, list) or len(errors) > 100 or any(
            not isinstance(e, str) or not re.fullmatch('[a-z-]+(?::[0-9]+)?', e) for e in errors):
        raise ValueError('unsafe notification')
    url = config['url']
    if not re.fullmatch(r'https://discord\.com/api/v10/webhooks/[0-9]+/[A-Za-z0-9_-]+', url):
        raise ValueError('unsafe notification destination')
    content = 'pgsql337 operations: ' + ('HEALTHY' if status['ok'] else 'ALERT ' + ', '.join(errors))
    state = pathlib.Path(config['state'])
    now = int(time.time())
    previous = {}
    try:
        previous = a.protected_json(state / 'delivery.json')
    except Exception:
        pass
    interval = 86400 if status['ok'] else 3600
    if previous.get('content') == content and 0 <= now-previous.get('at', 0) < interval:
        return previous
    def request(method, endpoint, payload=None):
        headers = {'Content-Type': 'application/json', 'User-Agent': 'autonomy337/1.0'}
        req = urllib.request.Request(endpoint, method=method, headers=headers,
            data=json.dumps(payload).encode() if payload is not None else None)
        # Never forward a channel credential through a redirect.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        with urllib.request.build_opener(NoRedirect).open(req, timeout=20) as response:
            return json.load(response)
    created = request('POST', url+'?wait=true', {'content': content, 'allowed_mentions': {'parse': []}})
    message_id = created['id']
    if not re.fullmatch('[0-9]+', message_id):
        raise ValueError('invalid delivery identity')
    readback = request('GET', url+'/messages/'+message_id)
    if readback['id'] != message_id or readback['content'] != content:
        raise ValueError('delivery readback failed')
    receipt = dict(verified=True, at=now, content=content, message_id=message_id)
    a.atomic_json(state/'delivery.json', receipt)
    return receipt


def main():
    try:
        cfg = a.protected_json(sys.argv[1])
        status = json.loads(sys.stdin.buffer.read(16385))
        deliver(cfg, status)
        return 0
    except Exception:
        print('notification failed', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
