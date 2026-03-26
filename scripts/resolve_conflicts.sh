#!/usr/bin/env bash
set -euo pipefail

# Auto-resolve currently conflicted files using either ours or theirs, then commit.
# Usage:
#   ./scripts/resolve_conflicts.sh ours   "Resolve conflicts"
#   ./scripts/resolve_conflicts.sh theirs "Resolve conflicts"

STRATEGY="${1:-}"
COMMIT_MSG="${2:-Resolve merge conflicts}"

if [[ "$STRATEGY" != "ours" && "$STRATEGY" != "theirs" ]]; then
  echo "Usage: $0 <ours|theirs> [commit-message]"
  exit 1
fi

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "Not inside a git repository."
  exit 1
fi

mapfile -t CONFLICTED < <(git diff --name-only --diff-filter=U)

if [[ ${#CONFLICTED[@]} -eq 0 ]]; then
  echo "No conflicted files found (git diff --name-only --diff-filter=U is empty)."
  exit 0
fi

echo "Resolving ${#CONFLICTED[@]} conflicted file(s) using --$STRATEGY..."
for file in "${CONFLICTED[@]}"; do
  git checkout "--$STRATEGY" -- "$file"
  git add "$file"
  echo "  resolved: $file"
done

git commit -m "$COMMIT_MSG"
echo "Done. Created commit: $(git rev-parse --short HEAD)"
