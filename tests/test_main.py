import unittest
import os
import mock
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

    def test_post_merge_info(self):
        with mock.patch('sss.do_request') as mock_do_request:
            sss.post_merge_info('prj', 'arm', 'e96d38e6e7', 'fail',
                                get_asset_path('skt_rc_0'), {})
            url, test_result, metadata = mock_do_request.mock_calls[0][1]
            self.assertEqual('api/submit/KERNELCI/prj/e96d38e6e7/arm', url)
            self.assertDictEqual({'/merge/': 'fail'}, test_result)
            metadata_expected = {
                'patchwork_00': 'http://patchwork.usersys.redhat.com/patch/229746',
                'basehead': 'e96d38e6e7ae0ee35656fc86a0668434648bb8e3',
                'baserepo': 'http://git.host.prod.eng.bos.redhat.com/git/rhel7.git',
            }
            self.assertDictEqual(metadata_expected, metadata)

    def test_post_build_info(self):
        with mock.patch('sss.do_request') as mock_do_request:
            sss.post_build_info('prj', 'arm', 'e96d38e6e7', 'pass',
                                get_asset_path('skt_rc_0'), {})
            url, test_result, metadata = mock_do_request.mock_calls[0][1]
            self.assertEqual('api/submit/KERNELCI/prj/e96d38e6e7/arm', url)
            self.assertDictEqual({'/build/': 'pass'}, test_result)
            metadata_expected = {
                'patchwork_00': 'http://patchwork.usersys.redhat.com/patch/229746',
                'basehead': 'e96d38e6e7ae0ee35656fc86a0668434648bb8e3',
                'baserepo': 'http://git.host.prod.eng.bos.redhat.com/git/rhel7.git',
                'buildlog_arm': '/home/worker/runner/workspace/rhel7-multiarch@3/ppc64le/workdir/build.log',
                'cfgurl_arm': 'http://xci33.lab.eng.rdu2.redhat.com/builds/ppc64le/ef7cec3e560720ddd2fde2bf824761087c025a32.csv.config',
            }
            self.assertDictEqual(metadata_expected, metadata)
