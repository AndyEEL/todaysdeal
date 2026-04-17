#!/bin/zsh
set -euo pipefail

REPO_DIR="/Users/andylee/dev/990won"
LOG_DIR="$REPO_DIR/logs"
LOG_FILE="$LOG_DIR/naver_special_deals.log"
PYTHON_BIN="$REPO_DIR/.venv/bin/python"
CHECK_SCRIPT="$REPO_DIR/scripts/check_snapshot.py"
TARGET_REF="${TODAYSDEAL_GIT_REF:-origin/main}"
PUSH_TARGET="${TODAYSDEAL_GIT_PUSH_TARGET:-HEAD:main}"
MAX_ATTEMPTS="${TODAYSDEAL_MAX_ATTEMPTS:-3}"
RETRY_SLEEP_SECONDS="${TODAYSDEAL_RETRY_SLEEP_SECONDS:-90}"
SKIP_PUSH="${TODAYSDEAL_SKIP_PUSH:-0}"
EXPECTED_DATE="${TODAYSDEAL_EXPECT_DATE:-$(TZ=Asia/Seoul date +%F)}"
RUN_DIR=""

if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

mkdir -p "$LOG_DIR"

cleanup() {
  if [ -n "$RUN_DIR" ] && [ -d "$RUN_DIR" ]; then
    cd "$REPO_DIR" >/dev/null 2>&1 || true
    git -C "$REPO_DIR" worktree remove --force "$RUN_DIR" >/dev/null 2>&1 || rm -rf "$RUN_DIR"
  fi
}
trap cleanup EXIT

exec >> "$LOG_FILE" 2>&1

echo ""
echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] === update_and_publish start ==="
echo "Repo: $REPO_DIR"
echo "Target ref: $TARGET_REF"
echo "Expected snapshot date: $EXPECTED_DATE"
echo "Max attempts: $MAX_ATTEMPTS"

git -C "$REPO_DIR" fetch origin main

RUN_DIR="$(mktemp -d "${TMPDIR:-/tmp}/todaysdeal-update.XXXXXX")"
git -C "$REPO_DIR" worktree add --force --detach "$RUN_DIR" "$TARGET_REF"

cd "$RUN_DIR"
git checkout -B automation/update "$TARGET_REF"

echo "Using Python: $PYTHON_BIN"
echo "Working directory: $RUN_DIR"

attempt=1
validated_summary=""
while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do
  echo "Attempt $attempt/$MAX_ATTEMPTS: collecting snapshot"
  if "$PYTHON_BIN" scripts/naver_special_deals.py --output-dir data --skip-history; then
    if validated_summary="$("$PYTHON_BIN" "$CHECK_SCRIPT" --snapshot-file data/latest.json --expect-date "$EXPECTED_DATE" --min-product-count 1)"; then
      echo "Snapshot validation passed: $validated_summary"
      break
    fi
    echo "Snapshot validation failed on attempt $attempt"
  else
    echo "Collector failed on attempt $attempt"
  fi

  if [ "$attempt" -lt "$MAX_ATTEMPTS" ]; then
    echo "Sleeping ${RETRY_SLEEP_SECONDS}s before retry"
    sleep "$RETRY_SLEEP_SECONDS"
  fi

  attempt=$((attempt + 1))
done

if [ -z "$validated_summary" ]; then
  echo "All collection attempts failed. Aborting publish."
  exit 1
fi

echo "Building derived analytics"
"$PYTHON_BIN" scripts/build_derived_data.py --data-dir data

echo "Syncing Airtable (if enabled)"
"$PYTHON_BIN" scripts/sync_airtable.py --data-dir data --env-file "$REPO_DIR/.env"

if [ -z "$(git status --porcelain -- data)" ]; then
  echo "No data changes detected."
  echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] === update_and_publish done (no changes) ==="
  exit 0
fi

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

git add data

git commit -m "Update special deals snapshot"

if [ "$SKIP_PUSH" = "1" ]; then
  echo "Push skipped because TODAYSDEAL_SKIP_PUSH=1"
else
  git push origin "$PUSH_TARGET"
  echo "Pushed changes to $PUSH_TARGET"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] === update_and_publish done ==="
