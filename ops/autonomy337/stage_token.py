#!/usr/bin/env python3
"""Isolated token-install hooks. Never modifies a production consumer."""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('autonomy', HERE / 'autonomy.py')
assert spec is not None and spec.loader is not None
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


def main():
    try:
        action, role = sys.argv[1:]
        if action not in {'install', 'verify'} or role not in a.ROLES:
            raise ValueError('invalid staged installation')
        token = sys.stdin.buffer.read(4097).decode().strip()
        if len(token) > 4096:
            raise ValueError('invalid credential size')
        a.verify_token(dict(role=role, public_key='/opt/autonomy337/issuer-public.pem'), token)
        path = pathlib.Path('/var/lib/a337issuer/staged') / (role + '.json')
        if action == 'install':
            a.atomic_json(path, dict(role=role, token=token, scope='staged-only-not-production'))
        elif a.protected_json(path) != dict(role=role, token=token, scope='staged-only-not-production'):
            raise ValueError('staged credential readback mismatch')
        return 0
    except Exception:
        print('staged installation failed', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
