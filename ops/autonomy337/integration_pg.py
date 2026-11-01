"""Disposable PG17.11 -> encrypted restic -> fresh database restore.
Run explicitly; never contacts CT337. Docker has no published ports or volumes.
"""
import importlib.util
import json
import os
import pathlib
import subprocess
import tempfile
import time
import unittest
import uuid

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('autonomy', HERE / 'autonomy.py')
assert spec is not None and spec.loader is not None
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)

class RealPostgresTests(unittest.TestCase):
    def test_dump_encryption_restore_and_retention(self):
        restic = os.environ['AUTONOMY_RESTIC']
        name = 'autonomy337-test-' + uuid.uuid4().hex[:12]
        docker = ['docker', 'exec', '-u', 'postgres', name]
        def run(args, **kwargs):
            return subprocess.run(args, check=True, capture_output=True, timeout=90, **kwargs).stdout
        try:
            run(['docker', 'run', '-d', '--rm', '--name', name,
                 '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', 'postgres:17.11'])
            for _ in range(90):
                if subprocess.run(docker + ['pg_isready'], capture_output=True).returncode == 0: break
                time.sleep(0.25)
            else: self.fail('disposable PostgreSQL failed readiness')
            run(docker + ['psql', '-v', 'ON_ERROR_STOP=1', '-c',
                "CREATE ROLE job_backup LOGIN BYPASSRLS; ALTER ROLE job_backup SET default_transaction_read_only=on; "
                "GRANT EXECUTE ON FUNCTION pg_control_system() TO job_backup; "
                "CREATE TABLE public.proof(id bigint generated always as identity primary key, note text); "
                "INSERT INTO proof(note) SELECT 'row-'||i FROM generate_series(1,1000) i; "
                "GRANT USAGE ON SCHEMA public TO job_backup; GRANT SELECT ON ALL TABLES IN SCHEMA public TO job_backup; "
                "GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO job_backup;"])
            fields = run(docker + ['psql', '-U', 'job_backup', '-d', 'postgres', '-At', '-F', '|', '-c',
                         "select (select system_identifier::text from pg_control_system()),current_database(),"
                         "(select oid::text from pg_database where datname=current_database()),current_setting('server_version_num')"]).decode().strip().split('|')
            a.validate_identity(dict(system_identifier=fields[0], database='postgres', database_oid=int(fields[2])), fields)
            with tempfile.TemporaryDirectory() as d:
                root = pathlib.Path(d); state = root / 'state'; state.mkdir(mode=0o700)
                env = dict(RESTIC_REPOSITORY=str(root / 'repo'), RESTIC_PASSWORD='disposable-not-production')
                run([restic, 'init'], env={**os.environ, **env})
                cfg = dict(state=str(state), restic=restic, restic_env=env, timeout=90,
                           source=docker + ['pg_dump', '-h', '/var/run/postgresql', '-U', 'job_backup', '-d', 'postgres', '-Fc'])
                receipts = []
                for _ in range(3): receipts.append(a.backup(cfg)); time.sleep(1)
                dump = run([restic, 'dump', receipts[-1]['snapshot'], '/jobs.dump'], env={**os.environ, **env})
                self.assertTrue(dump.startswith(b'PGDMP'))
                run(docker + ['createdb', 'restored'])
                run(['docker', 'exec', '-i', '-u', 'postgres', name, 'pg_restore', '-U', 'postgres', '-d', 'restored', '--exit-on-error'], input=dump)
                count = run(docker + ['psql', '-d', 'restored', '-Atqc', 'select count(*) from proof']).decode().strip()
                self.assertEqual(count, '1000')
                cfg.update(keep_last=2, keep_daily=0, keep_weekly=0, max_backup_age=93600, prune=True)
                result = a.retention(cfg)
                self.assertEqual(result['forgotten'], 1)
                self.assertEqual(result['retained'], 2)
                self.assertEqual(len(list(state.glob('backup-*.json'))), 2)
                snaps = json.loads(run([restic, 'snapshots', '--json'], env={**os.environ, **env}))
                self.assertEqual(len(snaps), 2)
                run([restic, 'check', '--read-data'], env={**os.environ, **env})
                # A read-only role cannot gain writes by disabling its session default.
                denied = subprocess.run(docker + ['psql', '-U', 'job_backup', '-d', 'postgres',
                          '-v', 'ON_ERROR_STOP=1', '-c', "SET transaction_read_only=off; INSERT INTO proof(note) VALUES ('forbidden')"], capture_output=True)
                self.assertNotEqual(denied.returncode, 0)
                self.assertIn(b'permission denied', denied.stderr)
                packs = list((root / 'repo' / 'data').glob('*/*'))
                self.assertTrue(packs)
                for pack in packs:
                    data = bytearray(pack.read_bytes()); data[len(data)//2] ^= 1
                    pack.chmod(0o600); pack.write_bytes(data)
                rejected = subprocess.run([restic, 'dump', receipts[-1]['snapshot'], '/jobs.dump'],
                           env={**os.environ, **env}, capture_output=True, timeout=90)
                self.assertNotEqual(rejected.returncode, 0)
        finally:
            subprocess.run(['docker', 'rm', '-f', '-v', name], capture_output=True)

if __name__ == '__main__': unittest.main()
