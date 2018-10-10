from __future__ import division
import os
import argparse
import json
import logging
import tempfile
import shutil
from datetime import datetime
try:
    import ConfigParser as configparser
except ImportError:
    import configparser
import requests
import dateutil.parser
import xmltodict
import jenkins
import pickledb


MERGE_FIELDS_REQUIRED = [
    'basehead',
    'baserepo',
    'patchwork_',
]
BUILD_FIELDS_REQUIRED = [
    'cfgurl',
    'buildurl|buildlog',
]


class MissingAUTH_TOKEN(Exception):
    """Exception raised when the varenv AUTH_TOKEN is missing"""


class MissingSQUAD_HOST(Exception):
    """Exception raised when the varenv SQUAD_HOST is missing"""


class MissingJENKINS_HOST(Exception):
    """Exception raised when the varenv JENKINS_HOST is missing"""


class MissingJENKINS_USERNAME(Exception):
    """Exception raised when the varenv JENKINS_USERNAME is missing"""


class MissingJENKINS_PASSWORD(Exception):
    """Exception raised when the varenv JENKINS_PASSWORD is missing"""


class MissingField(Exception):
    """Exception raised when a field is missing into the data to be send"""


def get_varenv_or_raise(name, exception):
    varenv = os.getenv(name)
    if not varenv:
        raise exception
    return varenv


def do_request(url, test_result, metadata, files=None, metrics=None):
    files = files or ()
    metrics = metrics or {}
    AUTH_TOKEN = get_varenv_or_raise('AUTH_TOKEN', MissingAUTH_TOKEN)
    SQUAD_HOST = get_varenv_or_raise('SQUAD_HOST', MissingSQUAD_HOST)
    headers = {
        "Auth-Token": AUTH_TOKEN,
    }
    data = {
        'tests': json.dumps(test_result),
        'metadata': json.dumps(metadata),
        'metrics': json.dumps(metrics),
    }
    attachments = []
    for file in files:
        attachments.append(('attachment', file))
    full_url = '{SQUAD_HOST}/{url}'.format(SQUAD_HOST=SQUAD_HOST, url=url)
    logging.debug('Posting the following payload\ndata:\t%r\nfiles:\t%r',
                  data, attachments)
    response = requests.post(full_url, headers=headers, data=data, files=attachments)
    if 'There is already a test run with' in response.content:
        logging.warning(response.content)
        return
    response.raise_for_status()


def _is_field_required(field, expected_key):
    for key in expected_key.split('|'):
        if field.startswith(key):
            return True
    return False


def _build_new_dict_from(data, expected_keys, check_missing_fields):
    """Return a dict with the keys listed on expected_keys"""
    result = {}
    for expected_key in expected_keys:
        for field in data:
            if _is_field_required(field, expected_key):
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
    """A ConfigParser subclass with an extra method to get the data as dict"""
    def as_dict(self):
        d = dict(self._sections)
        for k in d:
            d[k] = dict(self._defaults, **d[k])
            d[k].pop('__name__', None)
        return d


def read_skt_rc_state(skt_rc_path):
    """Get the skt state section as dict"""
    ini_parser = IniParser()
    ini_parser.read(skt_rc_path)
    return ini_parser.as_dict()['state']


def post_merge_info(project, arch, source_id, state, skt_rc_path, metadata):
    """tightly coupled to skt"""
    # group name KERNELCI hardcoded for now
    url = 'api/submit/KERNELCI/{project}/{source_id}/{arch}'.format(**locals())
    check_missing_fields = True if state.lower() == 'skip' else False
    data = read_skt_rc_state(skt_rc_path)
    metadata.update(get_merge_metadata(data, check_missing_fields))
    test_result = {'/merge/': state}
    do_request(url, test_result, metadata)


def post_build_info(project, arch, source_id, state, skt_rc_path, metadata):
    """tightly coupled to skt"""
    url = 'api/submit/KERNELCI/{project}/{source_id}/{arch}'.format(**locals())
    data = read_skt_rc_state(skt_rc_path)
    metadata.update(get_merge_metadata(data, False))
    metadata.update(get_build_metadata(data, arch, True))
    test_result = {'/build/': state}
    do_request(url, test_result, metadata)


def _fetch_log(name, url, tmpdir):
    filepath = os.path.join(tmpdir, name)
    with open(filepath, 'wb') as fh:
        response = requests.get(url)
        fh.write(response.content)
    return filepath


def _get_log_files(task_logs, beaker_host, tmpdir):
    files = []
    for log in task_logs:
        url = '{}/{}'.format(beaker_host, log['href'])
        filepath = _fetch_log(log['path'], url, tmpdir)
        files.append(open(filepath, 'rb'))
    return files


def get_log_by_task(task, task_name):
    if 'logs' not in task:
        return {}
    test_name = task['@path']
    if task_name not in task['@path']:
        test_name = '{}/{}'.format(task_name, task['@path'])
    result = {
        'name': test_name,
        'result': task['@result'],
        'id': task['@id'],
        'url_log': task['logs']['log']['@href'],
    }
    return result


def get_test_results(beaker_host, recipe_id):
    response = requests.get('{beaker_host}/recipes/{recipe_id}.xml'.format(**locals()))
    result = xmltodict.parse(response.content)
    tests = []
    for task in result['job']['recipeSet']['recipe']['task']:
        if not task['@name'].startswith('/kernel'):
            continue
        task_name, subtasks = task['@name'], task['results']
        if type(subtasks['result']) == list:
            for subtask in subtasks['result']:
                test = get_log_by_task(subtask, task_name)
                if test:
                    tests.append(test)
        else:
            test = get_log_by_task(subtasks['result'], task_name)
            if test:
                tests.append(test)
    return tests


def post_task(beaker_host, url_squad, task, metadata, beaker_result):
    task_name = task['name']
    test_result = {}
    tmpdir = tempfile.mkdtemp()
    files = _get_log_files(task['logs'], beaker_host, tmpdir)
    # job_id must be unique, so it's better using beaker ids
    metadata['job_id'] = '{}-{}'.format(task['id'],
                                        task_name.strip('/').replace('/', '-'))
    if task['status'] == 'Completed':
        finish_time = dateutil.parser.parse(task['finish_time'])
        start_time = dateutil.parser.parse(task['start_time'])
        duration = finish_time - start_time
        metrics = {
            task_name + '/duration': duration.seconds,
        }
    else:
        metrics = {}
    for test in beaker_result:
        if task_name not in test['name']:
            continue
        subtask_name = test['name'].split(task_name)[1]
        subtask_name = '-'.join(subtask_name.lstrip('/').split('/'))
        subtask_name = subtask_name or os.path.basename(test['name'])
        filepath = _fetch_log(subtask_name + '.log', test['url_log'], tmpdir)
        files.append(open(filepath, 'rb'))
        subtask_fullname = task_name + '/' + subtask_name
        test_result[subtask_fullname] = test['result']
    do_request(url_squad, test_result, metadata, files, metrics)
    shutil.rmtree(tmpdir)


def post_test_info(project, arch, source_id, skt_rc_path, metadata):
    beaker_host = 'https://beaker.engineering.redhat.com'
    data = read_skt_rc_state(skt_rc_path)
    recipeset = data['recipesetid_0'].split(':')[1]
    url = '{beaker_host}/recipesets/{recipeset}'.format(**locals())
    response = requests.get(url)
    result = response.json()
    url_squad = 'api/submit/KERNELCI/{project}/{source_id}/{arch}'.format(**locals())
    metadata.update(get_merge_metadata(data, False))
    metadata.update(get_build_metadata(data, arch, True))
    recipe_id = result['machine_recipes'][0]['recipe_id']
    beaker_result = get_test_results(beaker_host, recipe_id)
    for task in result['machine_recipes'][0]['tasks']:
        if task['name'].startswith('/kernel'):
            post_task(beaker_host, url_squad, task, metadata, beaker_result)


def get_sections(console_text):
    sections = {}
    inside_section = False
    for line in console_text.splitlines():
        if line.startswith('BUILD STATE'):
            inside_section = True
            name = ' '.join(line.split()[3:])
            continue
        if line.startswith('[Pipeline] stage'):
            inside_section = False
        if inside_section:
            sections.setdefault(name, []).append(line)
    return sections


def parse_section(section):
    result = []
    next_line_arch = False
    payload = False
    content = []
    d = {}
    for line in section:
        if line.endswith('echo'):
            next_line_arch = True
            continue
        if next_line_arch:
           next_line_arch = False
           d['arch'] = line.strip(':')
           payload = True
           continue
        if payload and not line:
            payload = False
            if d and len(content) > 1:
                d['skt_rc'] = '\n'.join(content)
                result.append(d)
            d = {}
            content = []
            continue
        if payload:
            if 'configuration' in line:
                content = ['',]
                continue
            if content:
                content.append(line.strip())
            else:
                line_split = line.split(':')
                d[line_split[0].strip()] = line_split[1].strip()
    return result


def _build_source_id(skt_rc_path):
    skt_rc = read_skt_rc_state(skt_rc_path)
    source_id = skt_rc['basehead'][:8]
    for k, v in skt_rc.items():
        if k.startswith('patchwork'):
            source_id += '.patch.{}'.format(os.path.basename(v))
            break
    return source_id


def sss_save_state(db, job_id):
    db.set(job_id, True)
    db.dump()


def process_build(job_name, build, build_info, sections, db):
    status_map = {
        'Created': 'Patching fail',
        'Merged': 'Building fail',
        'Built': 'Testing fail weirdly',
        'Tested': 'Testing fail',
        'Passed': 'OK',
    }
    merge_fail_status = {
        'Created': 'fail',
    }
    build_fail_status = {
        'Created': 'fail',
        'Merged': 'fail',
        'Built': 'fail',
    }
    for data_parsed in parse_section(sections['TESTING']):
        logging.info(
            'Parsing %s with status %s for arch %s',
            build['url'],
            status_map[data_parsed['status']],
            data_parsed['arch']
        )
        with tempfile.NamedTemporaryFile() as fh:
            fh.write(data_parsed['skt_rc'].encode('utf-8'))
            fh.flush()

            source_id = _build_source_id(fh.name)
            build_date = datetime.fromtimestamp(build_info['timestamp']/1000)
            metadata = {
                'build_url': build_info['url'],
                'datetime': build_date.isoformat(),
            }

            metadata['job_id'] = '{}-{}-{}'.format(build_info['id'],
                                                   data_parsed['arch'],
                                                   'merge')
            merge_status = merge_fail_status.get(data_parsed['status'], 'pass')
            if not db.get(metadata['job_id']):
                logging.info('Post step %s', metadata['job_id'])
                post_merge_info(job_name, data_parsed['arch'], source_id,
                                merge_status, fh.name, metadata)
            sss_save_state(db, metadata['job_id'])
            if merge_status == 'fail':
                continue

            metadata['job_id'] = '{}-{}-{}'.format(build_info['id'],
                                                   data_parsed['arch'],
                                                   'build')
            build_status = build_fail_status.get(data_parsed['status'], 'pass')
            if not db.get(metadata['job_id']):
                logging.info('Post step %s', metadata['job_id'])
                post_build_info(job_name, data_parsed['arch'], source_id,
                                build_status, fh.name, metadata)
            sss_save_state(db, metadata['job_id'])
            if build_status == 'fail':
                continue

            job_id = '{}-{}-{}'.format(build_info['id'],
                                       data_parsed['arch'],
                                       'test')
            if not db.get(job_id):
                logging.info('Post step %s', job_id)
                post_test_info(job_name, data_parsed['arch'], source_id,
                               fh.name, metadata)
            sss_save_state(db, job_id)


def process_jenkins_jobs():
    logging.basicConfig(format="%(created)10.6f:%(levelname)s: %(message)s")
    logging.getLogger().setLevel(os.environ.get('LOG_LEVEL', 'INFO'))
    parser = argparse.ArgumentParser(
        description='Fetch jenkins jobs then parse and push them to Squad.'
    )
    parser.add_argument(
        '--all-builds',
        help='If passed, all builds will be retrieved from Jenkins. Otherwise,'
        ' Jenkins will only return the most recent 100 builds per job name',
        action='store_true',
    )
    args = parser.parse_args()

    host = get_varenv_or_raise('JENKINS_HOST', MissingJENKINS_HOST)
    username = get_varenv_or_raise('JENKINS_USERNAME', MissingJENKINS_USERNAME)
    password = get_varenv_or_raise('JENKINS_PASSWORD', MissingJENKINS_PASSWORD)
    server = jenkins.Jenkins(host, username=username, password=password)
    db = pickledb.load('sss_cache.db', False)
    try:
        import config
    except ImportError:
        raise Exception('Missing config.py')
    for job_name in config.JOB_NAMES_TRACKED:
        job_info = server.get_job_info(job_name,
                                       fetch_all_builds=args.all_builds)
        builds = sorted(job_info['builds'], key=lambda x: x['number'])
        for build in builds:
            build_info = server.get_build_info(job_name, build['number'])
            if build_info['building'] or build_info['result'] == 'ABORTED':
                # Not processing pipelines unfinished neither aborted
                continue
            url = '{}/consoleText'.format(build['url'])
            response = requests.get(url)
            console_text = response.content
            sections = get_sections(console_text)
            if not sections or len(sections) != 3:
                # Discard broken pipelines
                job_id_broken = '{}-{}'.format(job_name, build_info['id'])
                if not db.get(job_id_broken):
                    logging.warning('Broken pipeline\n%r', console_text)
                    sss_save_state(db, job_id_broken)
                continue

            process_build(job_name, build, build_info, sections, db)


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
    elif args.action == 'test':
        post_test_info(args.project, args.arch, args.source_id, args.skt_rc_path, metadata)
