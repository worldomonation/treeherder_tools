import ast
import json
import requests
import sys
import time

from argparse import ArgumentParser

import thclient

def create_parser(args):

    parser = ArgumentParser()
    parser.add_argument('--keyword', action='store', default=None, nargs='?', help="Keyword to search in the logs.")
    parser.add_argument('--revision', action='store', default=None, nargs='1', help="Revision to search against. Obtain from Treeherder.")
    parser.add_argument('--branch', action='store', default='try', nargs='?', help="Treeherder branch.")

    args, _ = parser.parse_known_args()
    return args

def process_logs(args):
    client = thclient.TreeherderClient()

    keyword = args.keyword

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

    for job_name in logs_for_all_tests:
        for url in logs_for_all_tests[job_name]:
            response = requests.get(url)
            assert response.status_code == 200
            assert response.text

            separated_log = response.text.split('\n')
            if url.endswith('live_backlog.log'):
                unexpected_failures = [
                    line for line in separated_log if 'TEST-UNEXPECTED-FAIL' in line
                ]
                match = any(
                    [True for failure in unexpected_failures if keyword in failure]
                )
            elif url.endswith('errorsummary.log'):
                match = [
                    line for line in separated_log if keyword in line
                ]
            else:
                continue

            if match:
                print('Failure {} found in {}'.format(keyword, job_name))

    finish_time = round(time.perf_counter() - api_query_time, 5)
    print(f'Finished processing task logs in {finish_time} seconds.')


if __name__ == '__main__':
    create_parser(sys.argv([1:]))
    process_logs()