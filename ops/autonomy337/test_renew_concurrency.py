"""Offline renewal concurrency regression; disposable keys and local hooks only."""
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('autonomy_concurrency', HERE / 'autonomy.py')
assert spec is not None and spec.loader is not None
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


class ConcurrentRenewalTests(unittest.TestCase):
    def test_invalid_role_cannot_run_issuer_or_select_common_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            root.chmod(0o700)
            marker = root / 'issued'
            for role in [None, '../job_runner', 'postgres']:
                with self.assertRaises(ValueError):
                    a.renew(dict(state=str(root), role=role, timeout=5,
                                 issue=[sys.executable, '-c',
                                        'import pathlib,sys;pathlib.Path(sys.argv[1]).touch()', str(marker)]))
                self.assertFalse(marker.exists(), 'invalid role reached issuer')
                self.assertFalse((root / '.lock').exists(), 'invalid role selected legacy lock')

    def test_same_role_overlap_never_reaches_issuer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            root.chmod(0o700)
            marker = root / 'issued'
            for role in sorted(a.ROLES):
                with a.locked(root, renewal_role=role):
                    with self.assertRaises(BlockingIOError):
                        a.renew(dict(state=str(root), role=role, timeout=5,
                                     issue=[sys.executable, '-c',
                                            'import pathlib,sys;pathlib.Path(sys.argv[1]).touch()', str(marker)]))
                self.assertFalse(marker.exists())
            with a.locked(root):
                with self.assertRaises(BlockingIOError):
                    with a.locked(root):
                        self.fail('backup/retention common lock no longer excludes overlap')

    def test_role_lock_rejects_symlink_and_hardlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            root.chmod(0o700)
            target = root / 'protected'
            target.write_bytes(b'unchanged')
            target.chmod(0o600)
            lock = root / '.lock-renew-job_runner'
            lock.symlink_to(target)
            with self.assertRaises(OSError):
                with a.locked(root, renewal_role='job_runner'):
                    self.fail('symlink accepted')
            lock.unlink()
            import os
            os.link(target, lock)
            with self.assertRaises(ValueError):
                with a.locked(root, renewal_role='job_runner'):
                    self.fail('hardlink accepted')
            self.assertEqual(target.read_bytes(), b'unchanged')

    def test_three_roles_renew_in_shared_state_and_restore_monitor_watchdog_health(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            state = root / 'state'
            state.mkdir(mode=0o700)
            key, public = root / 'key.pem', root / 'public.pem'
            subprocess.run(['openssl', 'genrsa', '-out', str(key), '2048'],
                           capture_output=True, check=True)
            key.chmod(0o600)
            subprocess.run(['openssl', 'rsa', '-in', str(key), '-pubout', '-out', str(public)],
                           capture_output=True, check=True)
            # Hold every successful installer until all three roles have entered.
            # This forces overlap without relying on scheduler timing or sleeps.
            hook = root / 'hook.py'
            hook.write_text('''import pathlib,sys,time
root, role = pathlib.Path(sys.argv[1]), sys.argv[2]
(root / (role + '.token')).write_bytes(sys.stdin.buffer.read())
(root / (role + '.entered')).touch()
deadline = time.monotonic() + 15
while not (root / 'release').exists():
    if time.monotonic() > deadline: sys.exit(2)
    time.sleep(0.01)
''')
            roles = sorted(a.ROLES)
            processes = []
            checks, statuses = [], []
            for role in roles:
                issuer = root / ('issuer-' + role + '.json')
                a.atomic_json(issuer, dict(role=role, private_key=str(key)))
                config = root / (role + '.json')
                a.atomic_json(config, dict(
                    role=role, state=str(state), public_key=str(public), timeout=20,
                    scope='staged-only-not-production',
                    issue=[sys.executable, str(HERE / 'autonomy.py'), 'issue', '--config', str(issuer)],
                    install=[sys.executable, str(hook), str(root), role],
                    verify=[sys.executable, '-c',
                            'import pathlib,sys;sys.exit(pathlib.Path(sys.argv[1]).read_bytes()!=sys.stdin.buffer.read())',
                            str(root / (role + '.token'))]))
                # Seed exactly the observed monitor failure: two failed operations.
                a.atomic_json(state / ('status-renew-' + role + '.json'),
                              dict(ok=role == 'freehire_publication_reader', at=int(time.time())))
                a.atomic_json(state / ('renew-' + role + '.json'),
                              dict(verified=True, at=int(time.time()), expires_at=int(time.time()) + 86400))
                statuses.append(dict(path=str(state / ('status-renew-' + role + '.json')), max_age=60))
                checks.append(dict(path=str(state / ('renew-' + role + '.json')),
                                   max_age=60, min_remaining=21600))
            monitor = dict(state=str(state), checks=checks, statuses=statuses,
                           probes=[], timeout=10, notify=[sys.executable, '-c', 'import sys;sys.stdin.read()'])
            before = a.monitor(monitor)
            self.assertEqual(before['errors'], ['failed-operation:1', 'failed-operation:2'])
            try:
                for role in roles:
                    processes.append(subprocess.Popen(
                        [sys.executable, str(HERE / 'autonomy.py'), 'renew', '--config', str(root / (role + '.json'))],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE))
                deadline = time.monotonic() + 10
                while len(list(root.glob('*.entered'))) < len(roles):
                    if ((any(p.poll() is not None for p in processes) and list(root.glob('*.entered')))
                            or time.monotonic() > deadline):
                        break
                    time.sleep(0.01)
                self.assertEqual(len(list(root.glob('*.entered'))), 3,
                                 'shared-state role renewals must not fail on another role lock')
            finally:
                (root / 'release').touch()
                outputs = [p.communicate(timeout=25) for p in processes]
            self.assertEqual([p.returncode for p in processes], [0, 0, 0])
            for role in roles:
                receipt = a.protected_json(state / ('renew-' + role + '.json'))
                self.assertEqual(receipt['role'], role)
                self.assertTrue(receipt['verified'])
                self.assertEqual(receipt['scope'], 'staged-only-not-production')
                token = (root / (role + '.token')).read_bytes()
                self.assertTrue(all(token not in out + err for out, err in outputs))
            monitor['checks'] = checks
            self.assertTrue(a.monitor(monitor)['ok'])
            # Run the real watchdog against that local monitor receipt, not a double.
            watchdog = root / 'watchdog'
            watchdog.mkdir(mode=0o700)
            config = root / 'watchdog.json'
            a.atomic_json(config, dict(
                state=str(watchdog), collect=[sys.executable, '-c',
                    'import pathlib,sys;sys.stdout.buffer.write(pathlib.Path(sys.argv[1]).read_bytes())',
                    str(state / 'status-monitor.json')],
                checks=[dict(path=str(watchdog / 'collector-heartbeat.json'), max_age=60)],
                statuses=[], probes=[], timeout=10, notify=monitor['notify']))
            result = subprocess.run([sys.executable, str(HERE / 'watchdog.py'), str(config)],
                                    capture_output=True, check=True)
            self.assertTrue(json.loads(result.stdout)['ok'])
            self.assertTrue(a.protected_json(watchdog / 'collector-heartbeat.json')['verified'])


if __name__ == '__main__':
    unittest.main()
