#!/usr/bin/env python3
"""Update dynamic statistics in parasite6.svg without touching the ASCII portrait."""
import argparse
import calendar
from collections import Counter
from datetime import datetime, date, timezone
from html import escape
import json
import os
from pathlib import Path
import re
from urllib.request import Request, urlopen

USER = 'parasite6'
SVG_PATH = Path(__file__).resolve().parents[1] / 'parasite6.svg'
TOKEN = os.environ['GH_TOKEN']
HEADERS = {
    'Authorization': f'Bearer {TOKEN}',
    'Accept': 'application/vnd.github+json',
    'Content-Type': 'application/json',
    'X-GitHub-Api-Version': '2022-11-28',
    'User-Agent': 'profile-svg-refresh',
}

def api(url, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    with urlopen(Request(url, data=body, headers=HEADERS), timeout=30) as response:
        return json.load(response)

def stats():
    query = '''query($login: String!) {
      user(login: $login) {
        createdAt
        followers { totalCount }
        pullRequests { totalCount }
        issues { totalCount }
        repositoriesContributedTo(first: 1) { totalCount }
        contributionsCollection {
          totalCommitContributions
          totalPullRequestReviewContributions
          contributionCalendar {
            totalContributions
            weeks { contributionDays { contributionCount } }
          }
        }
      }
    }'''
    data = api('https://api.github.com/graphql', {'query': query, 'variables': {'login': USER}})
    if data.get('errors'):
        raise RuntimeError(f'GitHub GraphQL failed: {data["errors"]}')
    return data['data']['user']

def contributions_all_time(created_at, now=None):
    """Sum public and anonymous private activity over disjoint calendar years."""
    now = now or datetime.now(timezone.utc)
    first_year = datetime.fromisoformat(created_at.replace('Z', '+00:00')).year
    query = '''query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          restrictedContributionsCount
          contributionCalendar { totalContributions }
          totalCommitContributions
          totalPullRequestReviewContributions
        }
      }
    }'''
    total = dict(public=0, private=0, commits=0, reviews=0)
    for year in range(first_year, now.year + 1):
        start = datetime(year, 1, 1, tzinfo=timezone.utc)
        end = min(datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc), now)
        variables = {
            'login': USER,
            'from': start.isoformat().replace('+00:00', 'Z'),
            'to': end.isoformat().replace('+00:00', 'Z'),
        }
        data = api('https://api.github.com/graphql', {'query': query, 'variables': variables})
        if data.get('errors'):
            raise RuntimeError(f'GitHub GraphQL failed for contributions in {year}: {data["errors"]}')
        collection = data['data']['user']['contributionsCollection']
        private = collection['restrictedContributionsCount']
        total['private'] += private
        total['public'] += collection['contributionCalendar']['totalContributions'] - private
        total['commits'] += collection['totalCommitContributions']
        total['reviews'] += collection['totalPullRequestReviewContributions']
    return total

def repositories():
    repos = []
    for page in range(1, 21):
        batch = api(f'https://api.github.com/users/{USER}/repos?type=owner&per_page=100&page={page}')
        repos += [repo for repo in batch if not repo['private'] and not repo['fork']]
        if len(batch) < 100:
            break
    return repos

def languages(repos):
    tally = Counter()
    for repo in repos:
        tally.update(api(repo['languages_url']))
    total = sum(tally.values())
    if not total:
        return 'No language data'
    return ', '.join(f'{lang} {round(count * 100 / total)}%' for lang, count in tally.most_common(3))

def account_age(created_at):
    created = datetime.fromisoformat(created_at.replace('Z', '+00:00')).date()
    now = datetime.now(timezone.utc).date()
    months = (now.year - created.year) * 12 + now.month - created.month
    def advance(n):
        year, m = divmod((created.year * 12 + created.month - 1) + n, 12)
        month = m + 1
        return date(year, month, min(created.day, calendar.monthrange(year, month)[1]))
    if advance(months) > now:
        months -= 1
    return f'{months} months, {(now - advance(months)).days} days'

def replace_spans(svg, label, fill, values):
    """Replace text values in one SVG line; leave layout, portrait, and labels unchanged."""
    lines = svg.splitlines(keepends=True)
    matches = [i for i, line in enumerate(lines) if label in line]
    if len(matches) != 1:
        raise ValueError(f'Expected exactly one line for {label!r}, got {len(matches)}')
    i = matches[0]
    expression = re.compile(r'(<tspan fill="' + re.escape(fill) + r'">)([^<]*)(</tspan>)')
    found = list(expression.finditer(lines[i]))
    if len(found) != len(values):
        raise ValueError(f'Expected {len(values)} value spans for {label}, got {len(found)}')
    iterator = iter(values)
    lines[i] = expression.sub(lambda m: m.group(1) + escape(str(next(iterator)), quote=False) + m.group(3), lines[i])
    return ''.join(lines)

def main(include_pending_commit=False):
    user = stats()
    repos = repositories()
    lifetime = contributions_all_time(user['createdAt'])
    contributions = user['contributionsCollection']
    calendar_data = contributions['contributionCalendar']
    totals = [sum(day['contributionCount'] for day in w['contributionDays']) for w in calendar_data['weeks'][-52:]]
    highest = max(totals, default=0)
    blocks = '▁▂▃▄▅▆▇█'
    sparkline = ''.join(blocks[min(7, round(n * 7 / highest))] if n and highest else ' ' for n in totals)
    top = max(repos, key=lambda r: (r['stargazers_count'], r['name']), default=None)

    content = SVG_PATH.read_text(encoding='utf-8')
    content = replace_spans(content, 'Uptime:', '#c9d1d9', [account_age(user['createdAt'])])
    content = replace_spans(content, 'Languages:', '#c9d1d9', [languages(repos)])
    content = replace_spans(content, 'Repos:', '#79c0ff', [len(repos), sum(r['stargazers_count'] for r in repos)])
    content = replace_spans(content, 'Forks:', '#79c0ff', [sum(r['forks_count'] for r in repos), user['followers']['totalCount']])
    # Derive from the API each time so unchanged reruns never accumulate commits.
    # This display adjustment does not change GitHub contribution credit or authorship.
    content = replace_spans(content, 'Commits:', '#79c0ff', [lifetime['commits'] + int(include_pending_commit), user['repositoriesContributedTo']['totalCount']])
    content = replace_spans(content, 'PRs:', '#79c0ff', [user['pullRequests']['totalCount'], user['issues']['totalCount']])
    content = replace_spans(content, 'Top repo:', '#c9d1d9', [f'{top["name"]} ({top["stargazers_count"]} ★)' if top else 'None'])
    content = replace_spans(content, 'Public total:', '#79c0ff', [lifetime['public'], lifetime['reviews']])
    content = replace_spans(content, 'Private total:', '#79c0ff', [lifetime['private']])
    content = replace_spans(content, 'fill="#39d353"', '#39d353', [' ' * 3 + sparkline])

    if content != SVG_PATH.read_text(encoding='utf-8'):
        SVG_PATH.write_text(content, encoding='utf-8')
        print('Updated SVG stats')
    else:
        print('No SVG stats changed')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--include-pending-commit', action='store_true',
                        help='Include the upcoming refresh commit in the displayed commit count.')
    args = parser.parse_args()
    main(include_pending_commit=args.include_pending_commit)
