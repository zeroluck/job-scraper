import importlib.util
import json
import os
import pathlib
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('autonomy_security', pathlib.Path(__file__).with_name('autonomy.py'))
assert spec is not None and spec.loader is not None
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


class BoundaryTests(unittest.TestCase):
    def test_guest_oid_resolution_and_existing_owner_use_fixed_runuser(self):
        calls = []
        class Result:
            returncode = 0
            stdout = b''
        def run(argv, **kwargs):
            calls.append(argv)
            r = Result()
            if 'select datname from pg_database where oid=299919' in argv:
                r.stdout = b'jobs\n'
            elif '-F' in argv:
                r.stdout = b'7701229561420400865|jobs|299919|170011\n'
            return r
        cfg = dict(database='obsolete_name', database_oid=299919, system_identifier='7701229561420400865',
                   timeout=10, existing_owner_dump=True, resolve_database_oid=True)
        with patch.object(a.os, 'geteuid', return_value=0), patch.object(a.subprocess, 'run', side_effect=run):
            a.guest_dump(cfg)
        self.assertEqual(len(calls), 4)
        self.assertTrue(all(c[:4] == ['/usr/sbin/runuser', '-u', 'postgres', '--'] for c in calls))
        self.assertEqual(calls[-2][calls[-2].index('-d')+1], 'jobs')

    def test_nonroot_cannot_opt_into_existing_owner_dump(self):
        cfg = dict(database='jobs', existing_owner_dump=True)
        with patch.object(a.os, 'geteuid', return_value=999), patch.object(a.subprocess, 'run') as run:
            with self.assertRaises(ValueError):
                a.guest_dump(cfg)
            run.assert_not_called()

    def test_signer_rejects_hardlink_before_openssl(self):
        with tempfile.TemporaryDirectory() as d:
            key = pathlib.Path(d)/'key';key.write_bytes(b'not-key');key.chmod(0o600)
            os.link(key, pathlib.Path(d)/'linked')
            with patch.object(a.subprocess, 'run') as run:
                with self.assertRaises(ValueError):
                    a.issue(dict(role='job_runner', private_key=str(key)))
                run.assert_not_called()

    def test_invalid_backup_artifact_never_starts_source(self):
        with patch.object(a.subprocess, 'Popen') as popen:
            with self.assertRaises(ValueError):
                a.backup(dict(artifact='../secrets'))
            popen.assert_not_called()

    def test_root_can_read_explicit_owner_receipts_not_wrong_owner(self):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)/'receipt';p.write_text(json.dumps({'verified':True}));p.chmod(0o600)
            self.assertEqual(a.protected_json(p, os.geteuid()), {'verified':True})
            with self.assertRaises(ValueError):
                a.protected_json(p, os.geteuid()+1)
