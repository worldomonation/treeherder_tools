import ast
import json
import re
import requests
import sys
import time

from argparse import ArgumentParser

import thclient


def parse_arguments(argv):
    parser = ArgumentParser()
    parser.add_argument('--keywords', action='store', default=None, required=True, nargs='+', help="One or more keywords to search in the logs.")
    parser.add_argument('--revision', action='store', default=None, required=True, help="Revision to search against. Obtain from Treeherder.")
    parser.add_argument('--branch', action='store', default='try', help="Treeherder branch.")
    parser.add_argument('--exact', action='store_true', default=False, help='Require exact match with the test name.')

    args, _ = parser.parse_known_args(argv)
    return args

def process_logs(args):
    client = thclient.TreeherderClient()

    keywords = args.keywords

    pushes = client.get_pushes(
        args.branch, **{"revision": args.revision})

    logs_for_all_tests = {}

    start_time = time.perf_counter()

    for push in pushes:
        jobs = client.get_jobs('try', push_id=push['id'], count=30)
        for job in jobs:
            if 'osx' in job['platform'] and job['job_type_name'].startswith('test'):
                job_name = job['job_type_name']

                job_id = job['id']

                response = client.get_job_log_url('try', **{"job_id": job_id})

                list_of_log_urls = [entry['url'] for entry in response if entry.get('url', None) is not None]
                logs_for_all_tests[job_name] = list_of_log_urls

    api_query_time = round(time.perf_counter() - start_time, 5)
    print(f'Finished querying Treeherder API in {api_query_time} seconds.')

    matches = {keyword: [] for keyword in keywords}

    expression = [(re.compile(r".*{}.*".format(keyword)), keyword) for keyword in args.keywords]

    for job_name in logs_for_all_tests:
        for url in logs_for_all_tests[job_name]:
            response = requests.get(url)
            assert response.status_code == 200
            assert response.text

            separated_log = list(filter(None, response.text.split('\n')))
            if url.endswith('live_backing.log'):
                unexpected_failures = [line for line in separated_log if 'TEST-UNEXPECTED-FAIL' in line]
                for regex, keyword in expression:
                    if any([regex.match(failure) for failure in unexpected_failures]):
                        matches[keyword].append(job_name)
            elif url.endswith('errorsummary.log'):
                separated_log = list(map(json.loads, separated_log[1:]))
                for regex, keyword in expression:
                    if any([regex.match(failure['test']) for failure in separated_log]):
                        matches[keyword].append(job_name)
            else:
                continue

    if matches:
        print('Failures found:')
        for key in matches.keys():
            print('-->', key)
            list(map(print, matches[key]))
            print('\n')

    finish_time = round(time.perf_counter() - api_query_time, 5)
    print(f'Finished processing task logs in {finish_time} seconds.')


def main():
    args = parse_arguments(sys.argv[1:])
    process_logs(args)

if __name__ == '__main__':
    main()
