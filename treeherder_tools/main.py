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
    parser.add_argument('--revision', action='store', default=None, help="Revision to search against. Obtain from Treeherder push. Defaults to obtain latest push for given platform.")
    parser.add_argument('--branch', action='store', default='try', help="Treeherder branch. Defaults to try.")
    parser.add_argument('--platform', action='store', default=None, required=True, help="Platform to check against.")
    parser.add_argument('--ran', action='store_true', default=False, help='Checks if test was run, and which chunk.')
    parser.add_argument('--exact', action='store_true', default=False, help='Require exact match with the test name.')

    args, _ = parser.parse_known_args(argv)
    return args


def get_list_of_log_urls(branch, revision, platform):
    client = thclient.TreeherderClient()

    if revision:
        pushes = client.get_pushes(
            branch, **{"revision": revision})
    else:
        pushes = client.get_pushes(branch)[0]

    log_urls = {}

    count = 30
    if branch is not 'try':
        count = 10000

    start_time = time.perf_counter()

    for push in pushes:
        jobs = client.get_jobs(branch, push_id=push['id'], count=count)
        for job in jobs:
            if platform in job['platform'] and job['job_type_name'].startswith('test'):
                job_name = job['job_type_name']

                job_id = job['id']

                response = client.get_job_log_url(branch, **{"job_id": job_id})

                log_urls[job_name] = [entry['url']
                            for entry in response if entry.get('url', None) is not None]

    api_query_time = round(time.perf_counter() - start_time, 5)
    print(f'Finished querying Treeherder API in {api_query_time} seconds.')

    return log_urls


def process_logs(log_urls, keywords, ran):
    start_time = time.perf_counter()
    matches = {keyword: [] for keyword in keywords}
    expression = [(re.compile(r".*{}.*".format(keyword)), keyword) for keyword in keywords]

    for job_name in log_urls:
        for url in log_urls[job_name]:
            response = requests.get(url)
            assert response.status_code == 200
            assert response.text

            separated_log = list(filter(None, response.text.split('\n')))

            if ran:
                if not url.endswith('live_backing.log'):
                    continue
                tests_ran = [
                    line for line in separated_log if 'TEST-OK' in line]
                for regex, keyword in expression:
                    if any([regex.match(line) for line in tests_ran]):
                        matches[keyword].append(job_name)

            else:
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

    finish_time = round(time.perf_counter() - start_time, 5)

    print(f'Finished processing task logs in {finish_time} seconds.')
    return matches


def process_results(matches, revision):
    print(f'Keywords found in {revision}:')
    for key in matches.keys():
        print('-->', key)
        if matches[key]:
            list(map(print, matches[key]))
        else:
            print('None found')
        print('\n')


def main():
    args = parse_arguments(sys.argv[1:])
    log_urls = get_list_of_log_urls(args.branch, args.revision, args.platform)
    matches = process_logs(log_urls, args.keywords, args.ran)
    process_results(matches, args.revision)

if __name__ == '__main__':
    main()
