#!/usr/bin/env python3
"""Fail backup startup unless its systemd credential boundary is effective."""
import pathlib
import sys


def main():
    for name in ['/mnt/autonomy337-backups/repository',
                 '/etc/autonomy337/retention/config.json',
                 '/etc/autonomy337/repo/users.htpasswd',
                 '/var/lib/a337issuer']:
        try:
            p = pathlib.Path(name)
            if p.is_dir():
                list(p.iterdir())
            else:
                with p.open('rb') as source:
                    source.read(1)
        except (PermissionError, FileNotFoundError):
            continue
        print('collector boundary failed', file=sys.stderr)
        return 1
    print('collector boundary verified')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
