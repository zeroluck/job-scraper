#!/usr/bin/env python3
"""Monthly isolated PG17.11 restore from authenticated off-host snapshots.

Never reuses/removes a preexisting container. Never accesses the source database.
Initial source/catalog parity is a separate qualification receipt. Periodic drills
prove decryptability, complete owner/ACL-preserving restore and catalog scanning.
"""
import hashlib
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from restore_support import prepare_globals
spec = importlib.util.spec_from_file_location('autonomy', HERE / 'autonomy.py')
assert spec is not None and spec.loader is not None
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)
NAME = 'autonomy337-restore-proof'
IMAGE = 'postgres:17.11@sha256:31ba9c94a03ada9988f2bb493a22a75eef3a185884533e5cdbcd498ea835b08f'


def run(argv, **kwargs):
    return subprocess.run(argv, capture_output=True, check=True, timeout=600, **kwargs).stdout


def restore(cfg):
    with a.locked(cfg['state']):
        env = {'PATH': '/usr/bin:/bin', 'HOME': '/root', **cfg['restic_env']}
        # Reject stale/missing backups before creating any isolated resource.
        receipts = []
        for path in [cfg['jobs_receipt'], cfg['globals_receipt']]:
            r = a.protected_json(path, cfg['backup_owner_uid'])
            if r.get('verified') is not True or not 0 <= time.time()-r['at'] <= 93600:
                raise ValueError('restore requires fresh verified backups')
            receipts.append(r)
        existing = subprocess.run(['docker', 'inspect', NAME], capture_output=True, timeout=30)
        if existing.returncode == 0:
            raise ValueError('isolated restore resource already exists')
        created = False
        try:
            run(['docker', 'run', '-d', '--name', NAME, '--network', 'none',
                 '--memory=2g', '--cpus=2', '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', IMAGE])
            created = True
            d = ['docker', 'exec', NAME]
            for _ in range(120):
                if subprocess.run(d+['pg_isready', '-U', 'postgres'], capture_output=True, timeout=5).returncode == 0:
                    break
                time.sleep(0.5)
            else:
                raise ValueError('restore readiness failed')
            globals_sql = run(['/usr/bin/restic', 'dump', receipts[1]['snapshot'], '/roles.sql'], env=env)
            if hashlib.sha256(globals_sql).hexdigest() != receipts[1]['sha256']:
                raise ValueError('roles archive hash mismatch')
            run(['docker', 'exec', '-i', NAME, 'psql', '-U', 'postgres', '-d', 'postgres',
                 '-v', 'ON_ERROR_STOP=1'], input=prepare_globals(globals_sql))
            run(d+['createdb', '-U', 'postgres', '--template=template0', '--encoding=UTF8',
                   '--locale=C.UTF-8', '--owner=postgres', 'restored'])
            source = subprocess.Popen(['/usr/bin/restic', 'dump', receipts[0]['snapshot'], '/jobs.dump'],
                                      stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
            assert source.stdout is not None
            try:
                target = subprocess.run(['docker', 'exec', '-i', NAME, 'pg_restore', '-U', 'postgres',
                                         '-d', 'restored', '--exit-on-error'], stdin=source.stdout,
                                        capture_output=True, timeout=900)
                source.stdout.close()
                if target.returncode or source.wait(timeout=60):
                    raise ValueError('isolated full restore failed')
            finally:
                if source.poll() is None:
                    source.kill()
                source.wait()
            manifest = json.loads(run(['/usr/bin/python3', '-I', '/opt/autonomy337/catalog-proof.py']))
            if len(manifest['tables']) < 48 or len(manifest['sequences']) < 7:
                raise ValueError('incomplete restored inventory')
            result = dict(verified=True, at=int(time.time()), snapshot=receipts[0]['snapshot'],
                          globals_snapshot=receipts[1]['snapshot'], public_tables=sum(t['schema']=='public' for t in manifest['tables']),
                          all_tables=len(manifest['tables']), sequences=len(manifest['sequences']),
                          public_rows=sum(t['rows'] for t in manifest['tables'] if t['schema']=='public'),
                          scope='periodic offhost decryption/full restore/catalog scan, not live-source snapshot parity',
                          manifest_sha256=hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest())
            a.atomic_json(pathlib.Path(cfg['state'])/'periodic-restored-manifest.json', manifest)
            a.atomic_json(pathlib.Path(cfg['state'])/'restore-drill.json', result)
            return result
        finally:
            if created:
                run(['docker', 'rm', '-f', '-v', NAME])


def main():
    cfg = None
    try:
        cfg = a.protected_json(sys.argv[1])
        result = restore(cfg)
        a.atomic_json(pathlib.Path(cfg['state'])/'status-restore.json', dict(ok=True, at=result['at']))
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:
        if cfg is not None:
            a.atomic_json(pathlib.Path(cfg['state'])/'status-restore.json', dict(ok=False, at=int(time.time())))
        print('isolated restore drill failed', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
