#!/bin/zsh
set -euo pipefail

REPO_DIR="/Users/andylee/dev/990won"
LOG_DIR="$REPO_DIR/logs"
LOG_FILE="$LOG_DIR/naver_special_deals.log"
PYTHON_BIN="$REPO_DIR/.venv/bin/python"

if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

mkdir -p "$LOG_DIR"
cd "$REPO_DIR"

exec >> "$LOG_FILE" 2>&1

echo ""
echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] === update_and_publish start ==="

git fetch origin main
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Working tree is not clean. Aborting automated publish."
  exit 1
fi

git reset --hard origin/main

echo "Using Python: $PYTHON_BIN"
"$PYTHON_BIN" scripts/naver_special_deals.py --output-dir data --skip-history
"$PYTHON_BIN" scripts/build_derived_data.py --data-dir data

if [ -z "$(git status --porcelain -- data)" ]; then
  echo "No data changes detected."
  echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] === update_and_publish done (no changes) ==="
  exit 0
fi

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

git add data

git commit -m "Update special deals snapshot"
git push origin main

echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] === update_and_publish done (pushed) ==="
