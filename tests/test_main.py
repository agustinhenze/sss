import unittest
import os
import sss


def get_asset_path(filename):
    current_dir = os.path.realpath(os.path.dirname(__file__))
    return os.path.join(current_dir, 'assets', filename)


def get_asset_content(filename):
    asset_path = get_asset_path(filename)
    with open(asset_path) as fh:
        return fh.read()


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

    def test_read_skt_rc_state(self):
        rc_state = sss.read_skt_rc_state(get_asset_path('skt_rc_0'))
        self.assertEqual(rc_state['kernel_arch'], 'powerpc')
