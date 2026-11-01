import importlib.util
import json
import pathlib
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('autonomy', HERE / 'autonomy.py')
assert spec is not None and spec.loader is not None
a = importlib.util.module_from_spec(spec)
if (HERE / 'autonomy.py').exists():
    spec.loader.exec_module(a)

class ConfigTests(unittest.TestCase):
    def test_protected_json_rejects_world_readable_and_symlinks(self):
        self.assertTrue(hasattr(a, 'protected_json'), 'protected config loader missing')
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / 'config'
            p.write_text('{"ok":true}')
            p.chmod(0o644)
            with self.assertRaises(ValueError): a.protected_json(p)
            p.chmod(0o600)
            self.assertEqual(a.protected_json(p), {'ok': True})
            link = pathlib.Path(d) / 'link'
            link.symlink_to(p)
            with self.assertRaises(ValueError): a.protected_json(link)

class BackupTests(unittest.TestCase):
    def test_missing_restic_reaps_source(self):
        import os, signal, sys, time
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d); root.chmod(0o700)
            pidfile = root / 'pid'
            cfg = dict(state=str(root), restic='/no-such-restic337', restic_env={}, timeout=1,
                       source=[sys.executable, '-c', 'import os,pathlib,sys,time;pathlib.Path(sys.argv[1]).write_text(str(os.getpid()));time.sleep(30)', str(pidfile)])
            try:
                with self.assertRaises(Exception): a.backup(cfg)
                time.sleep(0.3)
                if pidfile.exists():
                    pid = int(pidfile.read_text())
                    with self.assertRaises(ProcessLookupError): os.kill(pid, 0)
            finally:
                if pidfile.exists():
                    try: os.kill(int(pidfile.read_text()), signal.SIGKILL)
                    except ProcessLookupError: pass

    def test_stream_backup_authenticated_readback_and_failed_source(self):
        import os, subprocess, sys
        self.assertTrue(hasattr(a, 'backup'), 'live stream collector missing')
        restic = os.environ.get('AUTONOMY_RESTIC', '/Users/tmaerz/.hermes/cache/scratch/restic337')
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            env = {'RESTIC_REPOSITORY': str(root / 'repo'), 'RESTIC_PASSWORD': 'disposable-test-only'}
            subprocess.run([restic, 'init'], env={**os.environ, **env}, capture_output=True, check=True)
            state = root / 'state'; state.mkdir(mode=0o700)
            cfg = dict(restic=restic, restic_env=env, state=str(state), timeout=30,
                       source=[sys.executable, '-c', 'import sys;sys.stdout.buffer.write(b"PGDMP"+b"x"*100000)'])
            result = a.backup(cfg)
            self.assertTrue(result['verified'])
            self.assertEqual(result['bytes'], 100005)
            self.assertEqual(a.protected_json(state / 'latest-backup.json')['snapshot'], result['snapshot'])
            self.assertEqual(len(list(state.glob('backup-*.json'))), 1)
            cfg['source'] = [sys.executable, '-c', 'import sys;sys.stdout.write("partial");sys.exit(7)']
            with self.assertRaises(Exception): a.backup(cfg)
            self.assertEqual(len(list(state.glob('backup-*.json'))), 1)
            cfg['source'] = [sys.executable, '-c', 'import time;time.sleep(30)']
            cfg['timeout'] = 0.2
            with self.assertRaises(Exception): a.backup(cfg)
            self.assertEqual(len(list(state.glob('backup-*.json'))), 1)

class GuestTests(unittest.TestCase):
    def test_identity_guard_pins_cluster_database_oid_and_pg17(self):
        self.assertTrue(hasattr(a, 'validate_identity'), 'identity guard missing')
        cfg = dict(system_identifier='7701229561420400865', database='jobs_sync_20261101', database_oid=299919)
        a.validate_identity(cfg, ['7701229561420400865', 'jobs_sync_20261101', '299919', '170011'])
        for values in (['wrong', 'jobs_sync_20261101', '299919', '170011'],
                       ['7701229561420400865', 'jobs', '299919', '170011'],
                       ['7701229561420400865', 'jobs_sync_20261101', '7', '170011'],
                       ['7701229561420400865', 'jobs_sync_20261101', '299919', '180001']):
            with self.assertRaises(ValueError): a.validate_identity(cfg, values)

class RenewalTests(unittest.TestCase):
    def test_fixed_claim_issuer_and_verified_install(self):
        import base64, os, subprocess, sys
        self.assertTrue(hasattr(a, 'issue'), 'bounded issuer missing')
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d); key = root / 'key.pem'; pub = root / 'public.pem'
            subprocess.run(['openssl', 'genrsa', '-out', str(key), '2048'], check=True, capture_output=True)
            key.chmod(0o600)
            subprocess.run(['openssl', 'rsa', '-in', str(key), '-pubout', '-out', str(pub)], check=True, capture_output=True)
            token = a.issue(dict(role='job_runner', private_key=str(key)))
            claims = json.loads(base64.urlsafe_b64decode(token.split('.')[1] + '==='))
            self.assertEqual(claims['role'], 'job_runner')
            self.assertEqual(claims['exp'] - claims['iat'], 86400)
            verifier = dict(role='job_runner', public_key=str(pub))
            self.assertEqual(a.verify_token(verifier, token)['role'], 'job_runner')
            wrong = token.rsplit('.', 1)[0] + '.' + base64.urlsafe_b64encode(b'wrong-signature').decode()
            with self.assertRaises(Exception): a.verify_token(verifier, wrong)
            with self.assertRaises(ValueError): a.verify_token(dict(role='job_web', public_key=str(pub)), token)
            with self.assertRaises(ValueError): a.issue(dict(role='postgres', private_key=str(key)))
            installed = root / 'installed'
            issuer = root / 'issuer.json'
            issuer.write_text(json.dumps(dict(role='job_runner', private_key=str(key)))); issuer.chmod(0o600)
            state = root / 'state'; state.mkdir(mode=0o700)
            cfg = dict(state=str(state), role='job_runner', public_key=str(pub), timeout=20,
                       issue=[sys.executable, str(HERE / 'autonomy.py'), 'issue', '--config', str(issuer)],
                       install=[sys.executable, '-c', 'import pathlib,sys;pathlib.Path(sys.argv[1]).write_bytes(sys.stdin.buffer.read())', str(installed)],
                       verify=[sys.executable, '-c', 'import pathlib,sys;sys.exit(0 if pathlib.Path(sys.argv[1]).read_bytes()==sys.stdin.buffer.read() else 1)', str(installed)])
            result = a.renew(cfg)
            self.assertTrue(result['verified'])
            self.assertNotIn(installed.read_text().strip(), json.dumps(result))
            cfg['verify'] = [sys.executable, '-c', 'import sys;sys.exit(1)']
            with self.assertRaises(Exception): a.renew(cfg)

class MonitorRetentionTests(unittest.TestCase):
    def test_monitor_expiry_staleness_failure_and_delivery(self):
        import sys, time
        self.assertTrue(hasattr(a, 'monitor'), 'monitor missing')
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d); now = int(time.time())
            receipt = root / 'renew.json'
            a.atomic_json(receipt, dict(at=now, verified=True, expires_at=now+9000))
            delivered = root / 'delivered'
            cfg = dict(checks=[dict(path=str(receipt), max_age=1000, min_remaining=3600)],
                       statuses=[], probes=[], timeout=10, state=str(root),
                       notify=[sys.executable, '-c', 'import pathlib,sys;pathlib.Path(sys.argv[1]).write_bytes(sys.stdin.buffer.read())', str(delivered)])
            self.assertTrue(a.monitor(cfg)['ok'])
            self.assertTrue(json.loads(delivered.read_text())['ok'])
            status = root / 'status.json'
            a.atomic_json(status, dict(ok=True, at=now-2000))
            cfg['statuses'] = [dict(path=str(status), max_age=1000)]
            self.assertIn('stale-operation:0', a.monitor(cfg)['errors'])
            cfg['statuses'] = []
            a.atomic_json(receipt, dict(at=now-2000, verified=True, expires_at=now+100))
            result = a.monitor(cfg)
            self.assertFalse(result['ok'])
            self.assertIn('stale:0', result['errors'])
            self.assertIn('expiring:0', result['errors'])
            receipt.unlink()
            self.assertFalse(a.monitor(cfg)['ok'])
            cfg['notify'] = [sys.executable, '-c', 'import sys;sys.exit(1)']
            self.assertIn('notification-failed', a.monitor(cfg)['errors'])

    def test_retention_keeps_floor_and_fails_closed_on_stale_backup(self):
        import time
        self.assertTrue(hasattr(a, 'retention_plan'), 'retention missing')
        now = int(time.time())
        rows = [dict(snapshot=str(i), at=now-i*86400, verified=True) for i in range(20)]
        cfg = dict(keep_last=14, keep_daily=0, keep_weekly=0, max_backup_age=93600)
        self.assertEqual(a.retention_plan(cfg, rows, now), [str(i) for i in range(14,20)])
        with self.assertRaises(ValueError): a.retention_plan(cfg, rows, now+100000)
        cfg['keep_last'] = 1
        with self.assertRaises(ValueError): a.retention_plan(cfg, rows, now)

if __name__ == '__main__': unittest.main()
