import unittest


class TestRadixIndex(unittest.TestCase):
    def test_build_and_search(self):
        from backend.radix_index import build_index, lpm_search

        pairs = [
            ('198.51.100.0/24', 64501, 'test'),
            ('198.51.100.0/25', 64502, 'test'),
        ]
        try:
            idx = build_index(pairs)
        except RuntimeError:
            self.skipTest('no radix implementation available')
        r = lpm_search(idx, '198.51.100.66')
        self.assertIsNotNone(r)
        self.assertEqual(r['asn'], 64502)


if __name__ == '__main__':
    unittest.main()
