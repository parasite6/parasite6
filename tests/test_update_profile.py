from datetime import datetime, timezone
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('GH_TOKEN', 'test-token')
spec = importlib.util.spec_from_file_location('update_profile', Path(__file__).resolve().parents[1] / 'scripts/update_profile.py')
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


class ProfileTests(unittest.TestCase):
    def test_private_total_includes_every_year_without_overlapping_windows(self):
        responses = [
            {'data': {'user': {'contributionsCollection': {'restrictedContributionsCount': n, 'contributionCalendar': {'totalContributions': n + 100}, 'totalCommitContributions': 50, 'totalPullRequestReviewContributions': 2}}}}
            for n in (10, 20, 37)
        ]
        now = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)
        with patch.object(profile, 'api', side_effect=responses) as api:
            self.assertEqual(profile.contributions_all_time('2024-06-01T00:00:00Z', now=now), {'public': 300, 'private': 67, 'commits': 150, 'reviews': 6})
        windows = [call.args[1]['variables'] for call in api.call_args_list]
        self.assertEqual([w['from'] for w in windows], [f'{y}-01-01T00:00:00Z' for y in (2024, 2025, 2026)])
        self.assertEqual([w['to'] for w in windows], ['2024-12-31T23:59:59Z', '2025-12-31T23:59:59Z', '2026-11-05T12:00:00Z'])

    def test_private_total_rejects_partial_results(self):
        with patch.object(profile, 'api', return_value={'errors': [{'message': 'Unavailable'}]}):
            with self.assertRaises(RuntimeError):
                profile.contributions_all_time('2026-01-01T00:00:00Z')

    def test_pending_commit_and_private_total_are_stable(self):
        user = {
            'createdAt': '2026-01-01T00:00:00Z',
            'followers': {'totalCount': 1}, 'pullRequests': {'totalCount': 2},
            'issues': {'totalCount': 3}, 'repositoriesContributedTo': {'totalCount': 4},
            'contributionsCollection': {
                'totalCommitContributions': 121,
                'restrictedContributionsCount': 37,
                'totalPullRequestReviewContributions': 0,
                'contributionCalendar': {'totalContributions': 158, 'weeks': [{'contributionDays': [{'contributionCount': 0}]}, {'contributionDays': [{'contributionCount': 37}]}]},
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'profile.svg'
            target.write_text(profile.SVG_PATH.read_text())
            with patch.object(profile, 'SVG_PATH', target), patch.object(profile, 'stats', return_value=user), patch.object(profile, 'repositories', return_value=[]), patch.object(profile, 'contributions_all_time', return_value={'public': 300, 'private': 57, 'commits': 200, 'reviews': 6}):
                profile.main(include_pending_commit=True)
                first = target.read_text()
                self.assertIn('>201</tspan>', next(line for line in first.splitlines() if 'Commits:' in line))
                self.assertIn('>57</tspan>', next(line for line in first.splitlines() if 'Private total:' in line))
                self.assertIn('>300</tspan>', next(line for line in first.splitlines() if '. Public total:' in line))
                self.assertIn('    █</tspan>', next(line for line in first.splitlines() if 'fill="#39d353"' in line))
                self.assertNotIn('Public Contributions (all time)', first)
                self.assertIn('Activity (public + private)', first)
                profile.main(include_pending_commit=True)
                self.assertEqual(first, target.read_text())
                profile.main()
                self.assertIn('>200</tspan>', next(line for line in target.read_text().splitlines() if 'Commits:' in line))


if __name__ == '__main__':
    unittest.main()
