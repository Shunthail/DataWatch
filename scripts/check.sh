#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m unittest discover -s backend/tests -v
for script in scripts/*.sh; do bash -n "$script"; done
cd frontend
if [[ ! -d node_modules ]]; then npm ci --cache .cache/npm; fi
npm run build
