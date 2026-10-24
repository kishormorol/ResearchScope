#!/usr/bin/env bash
set -euo pipefail

if [ "${GITHUB_REF:-}" != "refs/heads/main" ] || [ "$#" -ne 1 ]; then
  echo "Run from main with one commit message." >&2
  exit 1
fi
if git diff --cached --quiet; then
  echo "No changes to commit"
  exit 0
fi

git commit -m "$1"
# Save the original generated change before a retry can rebase or conflict.
mkdir -p publication-recovery
git rev-parse HEAD > publication-recovery/generated_commit_sha
git rev-parse HEAD^ > publication-recovery/base_commit_sha
git format-patch --binary --stdout HEAD^..HEAD > publication-recovery/generated.patch

for attempt in 1 2 3; do
  if git push origin HEAD:main; then
    exit 0
  fi
  if [ "$attempt" -eq 3 ]; then
    echo "Data publication failed. Recover the generated change from the artifact." >&2
    exit 1
  fi
  git fetch origin main
  git rebase origin/main
  sleep 5
done
