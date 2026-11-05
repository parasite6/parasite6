#!/usr/bin/env bash
# Run only in the disposable Actions checkout.
set -euo pipefail
: "${PROFILE_BRANCH:?PROFILE_BRANCH must name the branch to update}"

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'

for attempt in 1 2 3; do
  # Queued runs can start with a stale checkout. Generate from the current tip.
  git fetch origin "refs/heads/$PROFILE_BRANCH"
  git switch --detach FETCH_HEAD
  python scripts/update_profile.py --include-pending-commit
  if git diff --quiet -- parasite6.svg; then
    echo 'No changes; skipping commit.'
    exit 0
  fi
  git add parasite6.svg
  git commit -m 'chore: update GitHub profile statistics'
  if git push origin "HEAD:refs/heads/$PROFILE_BRANCH"; then
    exit 0
  fi
  echo "Push failed on attempt $attempt; fetching and regenerating statistics."
done

echo 'Unable to push profile statistics after 3 attempts.' >&2
exit 1
