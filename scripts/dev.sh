#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -d frontend/node_modules ]]; then
  (cd frontend && npm ci --cache .cache/npm)
fi
python3 -m backend.server &
backend_pid=$!
trap 'kill "$backend_pid" 2>/dev/null || true' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
sleep 0.3
if ! kill -0 "$backend_pid" 2>/dev/null; then
  echo "Backend indisponible. Vérifier que le port 8010 est libre." >&2
  exit 1
fi
cd frontend
npm start
