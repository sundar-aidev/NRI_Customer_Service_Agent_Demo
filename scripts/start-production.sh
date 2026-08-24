#!/bin/sh
set -eu

umask 077

STATE_ROOT=${NRI_STATE_ROOT:-${RAILWAY_VOLUME_MOUNT_PATH:-/data}}
export CODEX_HOME=${CODEX_HOME:-"${STATE_ROOT}/codex"}
mkdir -p "$CODEX_HOME"
chmod 700 "$CODEX_HOME"

AUTH_FILE="$CODEX_HOME/auth.json"
if [ ! -s "$AUTH_FILE" ] && [ -n "${CODEX_AUTH_JSON_B64:-}" ]; then
  python3 -c 'import base64, os, pathlib; pathlib.Path(os.environ["CODEX_HOME"], "auth.json").write_bytes(base64.b64decode(os.environ["CODEX_AUTH_JSON_B64"], validate=True))'
fi
unset CODEX_AUTH_JSON_B64

if [ ! -s "$AUTH_FILE" ]; then
  echo "Codex OAuth is not configured. Set CODEX_AUTH_JSON_B64 or attach a volume containing CODEX_HOME/auth.json." >&2
  exit 1
fi

chmod 600 "$AUTH_FILE"
python3 -c 'import json, os, pathlib; json.loads(pathlib.Path(os.environ["CODEX_HOME"], "auth.json").read_text(encoding="utf-8"))'

if ! codex login status >/dev/null 2>&1; then
  echo "Codex OAuth authentication failed. Refresh the Railway credential before starting the demo." >&2
  exit 1
fi

exec python3 -B serve.py --host "${NRI_HOST:-0.0.0.0}" --port "${PORT:-8080}"
