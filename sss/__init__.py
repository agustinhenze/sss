import os
import argparse
import json
import logging
try:
    import ConfigParser as configparser
except ImportError:
    import configparser
import requests


MERGE_FIELDS_REQUIRED = [
    'basehead',
    'baserepo',
    'patchwork_',
]
BUILD_FIELDS_REQUIRED = [
    'cfgurl',
    'buildurl',
]


class MissingAUTH_TOKEN(Exception):
    """Exception raised when the varenv AUTH_TOKEN is missing"""


class MissingSQUAD_HOST(Exception):
    """Exception raised when the varenv SQUAD_HOST is missing"""


class MissingField(Exception):
    """Exception raised when a field is missing into the data to be send"""


def get_varenv_or_raise(name, exception):
    varenv = os.getenv(name)
    if not varenv:
        raise exception
    return varenv


def do_request(url, test_result, metadata, files):
    AUTH_TOKEN = get_varenv_or_raise('AUTH_TOKEN', MissingAUTH_TOKEN)
    SQUAD_HOST = get_varenv_or_raise('SQUAD_HOST', MissingSQUAD_HOST)
    headers = {
        "Auth-Token": AUTH_TOKEN,
    }
    data = {
        'tests': json.dumps(test_result),
        'metadata': json.dumps(metadata),
    }
    url = '{SQUAD_HOST}/{url}'.format(SQUAD_HOST=SQUAD_HOST, url=url)
    logging.debug('Posting the following payload\n%r', data)
    response = requests.post(url, headers=headers, data=data, files=files)
    # ToDo: check response


def _build_new_dict_from(data, expected_keys, check_missing_fields):
    """Return a dict with the keys listed on expected_keys"""
    result = {}
    for expected_key in expected_keys:
        for field in data:
            if field.startswith(expected_key):
                break
        else:
            if check_missing_fields:
                raise MissingField(expected_key)
            else:
                continue
        result[field] = data[field]
    return result


def get_merge_metadata(data, check_missing_fields=True):
    """Return a dict with the merge fields required in this step"""
    return _build_new_dict_from(data, MERGE_FIELDS_REQUIRED, check_missing_fields)


def get_build_metadata(data, arch, check_missing_fields=True):
    """Return a dict with the merge fields required in this step"""
    tmp = _build_new_dict_from(data, BUILD_FIELDS_REQUIRED, check_missing_fields)
    result = {}
    for k, v in tmp.items():
        result['{k}_{arch}'.format(**locals())] = v
    return result


class IniParser(configparser.ConfigParser):
    def as_dict(self):
        d = dict(self._sections)
        for k in d:
            d[k] = dict(self._defaults, **d[k])
            d[k].pop('__name__', None)
        return d


def post_merge_info(project, arch, source_id, state, skt_rc_path, metadata):
    """tightly coupled to skt"""
    # group name KERNELCI hardcoded for now
    url = 'api/submit/KERNELCI/{project}/{source_id}/{arch}'.format(**locals())
    check_missing_fields = True if state.lower() == 'skip' else False
    ini_parser = IniParser()
    ini_parser.read(skt_rc_path)
    data = ini_parser.as_dict()['state']
    metadata.update(get_merge_metadata(data, check_missing_fields))
    test_result = {'/merge/': state}
    do_request(url, test_result, metadata, ())


def post_build_info(project, arch, source_id, state, skt_rc_path, metadata):
    """tightly coupled to skt"""
    url = 'api/submit/KERNELCI/{project}/{source_id}/{arch}'.format(**locals())
    ini_parser = IniParser()
    ini_parser.read(skt_rc_path)
    data = ini_parser.as_dict()['state']
    metadata.update(get_build_metadata(data, arch, True))
    test_result = {'/build/': state}
    do_request(url, test_result, metadata, ())


def main():
    logging.basicConfig(format="%(created)10.6f:%(levelname)s:%(message)s")
    logging.getLogger().setLevel(os.environ.get('LOG_LEVEL', 'INFO'))
    parser = argparse.ArgumentParser(description='Push SKT steps to Squad.')
    parser.add_argument('--project', help='Same name that jenkins pipeline', required=True)
    parser.add_argument('--source-id', help='Githash plus patchids appendend by a _ or something similar', required=True)
    parser.add_argument('--arch', help='Architecture', required=True)
    parser.add_argument('--state', help='State of the action', required=True, choices=['skip', 'pass', 'fail'])
    parser.add_argument('--skt-rc-path', help='Path to skt rc file', required=True)
    parser.add_argument('--job-id', help='Unique id for the task, maybe jenkins_job+action e.g. 234+merge', required=True)
    parser.add_argument('--build-url', help='URL pointing to the jenkins job', required=True)
    parser.add_argument('--action', help='Actions', choices=['merge', 'build', 'test'], required=True)
    args = parser.parse_args()
    metadata = {
        'job_id': args.job_id,
        'build_url': args.build_url,
    }
    if args.action == 'merge':
        post_merge_info(args.project, args.arch, args.source_id, args.state, args.skt_rc_path, metadata)
    elif args.action == 'build':
        post_build_info(args.project, args.arch, args.source_id, args.state, args.skt_rc_path, metadata)
