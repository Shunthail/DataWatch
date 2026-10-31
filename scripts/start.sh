#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -f frontend/dist/datawatch/browser/index.html ]]; then
  echo "Exécuter bash scripts/build.sh avant le démarrage." >&2
  exit 1
fi
exec python3 -m backend.server
