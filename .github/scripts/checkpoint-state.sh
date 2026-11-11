#!/usr/bin/env bash
# Save durable reservations before publishing, then save final results afterwards.
set -euo pipefail

: "${GH_TOKEN:?Missing GitHub workflow token}"
: "${THREADS_STATE_REPO:?Missing state checkout path}"
: "${THREADS_STATE_FILE:?Missing local state path}"

source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
python3 - "$THREADS_STATE_FILE" "$source_root" <<'PY'
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
if path.is_symlink() or not path.is_file():
    raise SystemExit("State must be an existing regular JSON file; refusing checkpoint.")
sys.path.insert(0, sys.argv[2])
from bot import BotError, State
try:
    State(path).validate()
except BotError as error:
    raise SystemExit(f"Invalid state; refusing checkpoint: {error}") from None
PY

test -d "$THREADS_STATE_REPO/.git"
auth_header="$(printf 'x-access-token:%s' "$GH_TOKEN" | base64 | tr -d '\n')"
echo "::add-mask::$auth_header"
export GIT_CONFIG_COUNT=1
export GIT_CONFIG_KEY_0='http.https://github.com/.extraheader'
export GIT_CONFIG_VALUE_0="AUTHORIZATION: basic $auth_header"

mkdir -p "$THREADS_STATE_REPO/state"
if test -L "$THREADS_STATE_REPO/state" || test -L "$THREADS_STATE_REPO/state/state.json"; then
  echo 'Refusing state checkout containing symbolic links.' >&2
  exit 1
fi
cp "$THREADS_STATE_FILE" "$THREADS_STATE_REPO/state/state.json"
git -C "$THREADS_STATE_REPO" add -- state/state.json
if ! git -C "$THREADS_STATE_REPO" diff --cached --quiet; then
  git -C "$THREADS_STATE_REPO" -c user.name='threads-comments[bot]' \
    -c user.email='threads-comments-bot@users.noreply.github.com' \
    commit -m 'Update Threads comment history'
fi
# No force push: a conflicting update must stop the worker.
# Push even with no new diff: an earlier commit may not have reached the remote.
git -C "$THREADS_STATE_REPO" push origin HEAD:refs/heads/bot-state
