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

    def test_get_build_metadata(self):
        data = {}
        arch = 'x86_64'
        self.assertRaises(sss.MissingField, sss.get_build_metadata, data, arch)
        data = {
            'cfgurl': 'url',
            'buildurl': 'url',
            'foo': 'bar'
        }
        result = sss.get_build_metadata(data, arch)
        self.assertDictEqual(
            {'buildurl_x86_64': 'url', 'cfgurl_x86_64': 'url'},
            result,
        )

        data = {
            'cfgurl': 'url',
            'buildlog': 'url',
            'foo': 'bar'
        }
        result = sss.get_build_metadata(data, arch)
        self.assertDictEqual(
            {'buildlog_x86_64': 'url', 'cfgurl_x86_64': 'url'},
            result,
        )

        data = {
            'basehead': 'githash',
            'cfgurl': 'url',
            'foo': 'bar'
        }
        result = sss.get_build_metadata(data, arch, check_missing_fields=False)
        self.assertDictEqual(
            {"cfgurl_x86_64": "url"},
            result,
        )
