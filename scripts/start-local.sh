#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$PROJECT_DIR"

if [ -z "${PYTHON_BIN:-}" ]; then
  if command -v python3.11 >/dev/null 2>&1; then
    PYTHON_BIN=python3.11
  else
    PYTHON_BIN=python3
  fi
fi
PORT=${PORT:-8765}

"$PYTHON_BIN" -B build.py
exec "$PYTHON_BIN" -B serve.py --host 127.0.0.1 --port "$PORT"
