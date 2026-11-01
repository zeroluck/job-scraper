"""Offline publication checks; never contacts PostgreSQL or runs a restore."""
import ast
import pathlib
import subprocess
import sys
import tempfile
import unittest
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent


class PortableCatalogTests(unittest.TestCase):
    def test_standalone_cli_renders_both_targets_without_migration_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            for name in ('build_catalog_helper.py', 'catalog_manifest.py'):
                source = HERE / name
                self.assertTrue(source.is_file(), 'portable catalog source must be published')
                (root / name).write_bytes(source.read_bytes())
            for flags, prefix in (([], ['runuser', '-u', 'postgres', '--']),
                                  (['--container'], ['docker', 'exec', 'autonomy337-restore-proof'])):
                result = subprocess.run([sys.executable, str(root / 'build_catalog_helper.py'), *flags],
                                        capture_output=True, text=True, check=True)
                tree = ast.parse(result.stdout)
                assignment = tree.body[0]
                self.assertIsInstance(assignment, ast.Assign)
                assert isinstance(assignment, ast.Assign)
                self.assertEqual(ast.literal_eval(assignment.value), prefix)
                functions = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
                self.assertEqual(functions, {'sql', 'jsql', 'manifest'})
                self.assertNotIn('migration/recovery337', result.stdout)
                compile(result.stdout, '<rendered-helper>', 'exec')

    def test_render_rejects_missing_or_duplicate_manifest(self):
        import build_catalog_helper
        for source in ('x = 1', 'def manifest(db): pass\ndef manifest(db): pass'):
            with self.assertRaises(ValueError):
                build_catalog_helper.render(source)

    def test_manifest_collects_all_sections_hashes_and_sequence_state(self):
        calls = []

        def jsql(db, query, snapshot=None):
            calls.append((db, query, snapshot))
            if query.startswith('SELECT n.nspname AS schema'):
                return [{'schema': 'public', 'name': 'test"table'}]
            if query.startswith('SELECT count(*)'):
                return [{'rows': 3, 'sorted_row_md5': 'offline-test-hash'}]
            if 'FROM pg_sequence s' in query:
                return [{'nspname': 'public', 'relname': 'test_seq'}]
            if query.startswith('SELECT last_value'):
                return [{'last_value': 8, 'is_called': True}]
            return []

        namespace: dict[str, Any] = {'jsql': jsql}
        exec(compile((HERE / 'catalog_manifest.py').read_text(), '<catalog-template>', 'exec'), namespace)
        result = namespace['manifest']('offline_test', 'snapshot-test')
        self.assertEqual(set(result), {'tables', 'schemas', 'columns', 'constraints', 'policies',
                                      'functions', 'indexes', 'triggers', 'sequences',
                                      'sequence_dependencies', 'default_acl', 'views'})
        self.assertEqual(result['tables'][0]['rows'], 3)
        self.assertEqual(result['tables'][0]['sorted_row_md5'], 'offline-test-hash')
        self.assertEqual(result['sequences'][0]['last_value'], 8)
        self.assertTrue(result['sequences'][0]['is_called'])
        self.assertIn('"public"."test""table"', calls[1][1])
        self.assertTrue(all(db == 'offline_test' for db, _, _ in calls))
        self.assertTrue(all(snapshot == 'snapshot-test' for _, _, snapshot in calls[:-1]))
        # Sequence values retain the original non-MVCC collection behavior.
        self.assertIsNone(calls[-1][2])


if __name__ == '__main__':
    unittest.main()
