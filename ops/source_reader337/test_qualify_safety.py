"""Qualification checks must remain active with Python optimization."""
import pathlib
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent


class QualificationSafety(unittest.TestCase):
    def test_optimized_check_rejects_false(self):
        result = subprocess.run(
            [sys.executable, '-O', '-c',
             'from qualify import require; require(False, "negative control")'],
            cwd=HERE, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('AssertionError: negative control', result.stderr)

    def test_optimized_importer_hash_rejection(self):
        with tempfile.TemporaryDirectory() as temp:
            importer = pathlib.Path(temp) / 'importer.py'
            importer.write_text('# wrong importer\n')
            result = subprocess.run(
                [sys.executable, '-O', str(HERE / 'qualify.py'),
                 '--importer', str(importer), '--receipt', str(pathlib.Path(temp) / 'receipt.json')],
                text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('AssertionError: deployed importer hash mismatch', result.stderr)


if __name__ == '__main__':
    unittest.main()
