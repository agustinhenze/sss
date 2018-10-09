import unittest
import sss



class TestMain(unittest.TestCase):
    def test_get_merge_metadata(self):
        data = {}
        self.assertRaises(sss.MissingField, sss.get_merge_metadata, data)
        data = {
            'basehead': 'githash',
            'baserepo': 'url',
            'patchwork_00': 'url',
            'foo': 'bar'
        }
        result = sss.get_merge_metadata(data)
        self.assertDictEqual(
            {"basehead": "githash", "baserepo": "url", "patchwork_00": "url"},
            result,
        )

        data = {
            'basehead': 'githash',
            'baserepo': 'url',
            'foo': 'bar'
        }
        result = sss.get_merge_metadata(data, check_missing_fields=False)
        self.assertDictEqual(
            {"basehead": "githash", "baserepo": "url"},
            result,
        )
