#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../frontend"
npm ci --cache .cache/npm
npm run build
