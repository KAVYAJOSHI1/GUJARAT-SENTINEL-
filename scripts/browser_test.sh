#!/bin/sh
# Phase 16 — real headless-browser UI validation against the running dev
# server (default http://localhost:3000). Builds the runner image once.
#
#   ./scripts/browser_test.sh                 # run frontend/e2e/*.mjs
#   ./scripts/browser_test.sh smoke.mjs       # run one spec
set -e
cd "$(dirname "$0")/.."

BASE_URL="${E2E_BASE_URL:-http://localhost:3000}"
API_URL="${E2E_API_URL:-http://localhost:8001}"
SPEC="${1:-run-all.mjs}"

if ! docker image inspect sentinel-e2e >/dev/null 2>&1; then
  echo "[e2e] building runner image (one time)…"
  docker build -q -f Dockerfile.e2e -t sentinel-e2e . >/dev/null
fi

# admin password for the login step
ADMIN_PASSWORD="$(grep -E '^ADMIN_PASSWORD=' .env 2>/dev/null | cut -d= -f2 || true)"

docker run --rm --network host \
  -e E2E_BASE_URL="$BASE_URL" \
  -e E2E_API_URL="$API_URL" \
  -e E2E_ADMIN_PASSWORD="$ADMIN_PASSWORD" \
  -e E2E_TRACE_AUTH="${E2E_TRACE_AUTH:-}" \
  -v "$PWD/frontend/e2e":/runner/specs:ro \
  sentinel-e2e "/runner/specs/$SPEC"
