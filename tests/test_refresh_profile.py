import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/refresh_profile.sh'


class RefreshTests(unittest.TestCase):
    def test_remote_update_during_push_is_preserved_and_stats_regenerated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def git(cwd, *args):
                return subprocess.check_output(['git', *args], cwd=cwd, stderr=subprocess.STDOUT, text=True)
            git(root, 'init', '--bare', 'remote.git')
            git(root, 'clone', str(root / 'remote.git'), 'worker')
            worker = root / 'worker'
            git(worker, 'config', 'user.name', 'Fixture')
            git(worker, 'config', 'user.email', 'fixture@example.com')
            git(worker, 'switch', '-c', 'sanctuary')
            (worker / 'scripts').mkdir()
            (worker / 'scripts/update_profile.py').write_text("from pathlib import Path\nPath('parasite6.svg').write_text(Path('source').read_text())\n")
            (worker / 'source').write_text('initial data')
            (worker / 'parasite6.svg').write_text('old stats')
            git(worker, 'add', '.')
            git(worker, 'commit', '-m', 'initial')
            git(worker, 'push', 'origin', 'sanctuary')
            git(root, 'clone', '--branch', 'sanctuary', str(root / 'remote.git'), 'competitor')
            competitor = root / 'competitor'
            git(competitor, 'config', 'user.name', 'Fixture')
            git(competitor, 'config', 'user.email', 'fixture@example.com')
            hook = worker / '.git/hooks/pre-push'
            hook.write_text('#!/bin/bash\nset -e\nif [ ! -e "$RACE_MARKER" ]; then\n touch "$RACE_MARKER"\n printf "new data" > "$COMPETITOR/source"\n git -C "$COMPETITOR" add source\n git -C "$COMPETITOR" commit -m concurrent\n git -C "$COMPETITOR" push origin sanctuary\nfi\n')
            hook.chmod(0o755)
            env = dict(os.environ, PROFILE_BRANCH='sanctuary', COMPETITOR=str(competitor), RACE_MARKER=str(root / 'raced'))
            result = subprocess.run(['bash', str(SCRIPT)], cwd=worker, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(git(root, '--git-dir=remote.git', 'show', 'sanctuary:source'), 'new data')
            self.assertEqual(git(root, '--git-dir=remote.git', 'show', 'sanctuary:parasite6.svg'), 'new data')
            before = git(root, '--git-dir=remote.git', 'rev-parse', 'sanctuary')
            result = subprocess.run(['bash', str(SCRIPT)], cwd=worker, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(git(root, '--git-dir=remote.git', 'rev-parse', 'sanctuary'), before)
