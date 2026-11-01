import unittest
from restore_support import canonical_order, prepare_globals


class CatalogOrderTests(unittest.TestCase):
    def test_order_only_and_duplicate_fields_preserved(self):
        a = {'constraints': [{'relation': 'a_b', 'validated': False}, {'relation': 'ab', 'validated': True}]}
        b = {'constraints': [dict(row) for row in reversed(a['constraints'])]}
        self.assertEqual(canonical_order(a), canonical_order(b))
        b['constraints'][0]['validated'] = False
        self.assertNotEqual(canonical_order(a), canonical_order(b))


class GlobalsRecoveryTests(unittest.TestCase):
    def test_omit_only_existing_bootstrap_create_preserve_grantor_and_attributes(self):
        sql = (b'CREATE ROLE postgres;\nALTER ROLE postgres WITH SUPERUSER;\n'
               b'CREATE ROLE reader;\nGRANT reader TO postgres GRANTED BY postgres;\n')
        self.assertEqual(prepare_globals(sql), sql.split(b'\n', 1)[1])

    def test_reject_passwords_and_missing_or_repeated_bootstrap(self):
        for sql in [b'CREATE ROLE reader;', b'CREATE ROLE postgres;\n'*2,
                    b'CREATE ROLE postgres;\nALTER ROLE reader PASSWORD NULL;']:
            with self.assertRaises(ValueError):
                prepare_globals(sql)
