#!/bin/sh
# scripts/hackathon_demo.sh
#
# Phase 20 Part J -- one deterministic command that gets the demo into a
# known-good state and PROVES it, end to end, before an evaluator ever
# touches the keyboard. Every line of the final summary is read back from
# a real, just-executed check -- nothing below is printed unconditionally.
#
#   ./scripts/hackathon_demo.sh          # fast path: reset + reseed + verify (~15s)
#   ./scripts/hackathon_demo.sh --full   # also onboard 50 mock cameras + a
#                                         # real short AI pipeline burst (~60s)
set -e
cd "$(dirname "$0")/.."

PYTHON=".venv/bin/python"
TMP_JSON="$(mktemp)"
trap 'rm -f "$TMP_JSON"' EXIT

echo "=== SENTINEL Hackathon Demo Setup ==="

# --- 1. verify docker/services ------------------------------------------- #
echo "\n[1/5] verifying docker services..."
if ! docker compose ps --format json >/dev/null 2>&1; then
  echo "  FAIL: docker compose is not available / stack not found."
  exit 1
fi
NOT_UP=$(docker compose ps --status running --services 2>/dev/null | wc -l | tr -d ' ')
echo "  running services: $(docker compose ps --services --status running 2>/dev/null | tr '\n' ' ')"
if [ "$NOT_UP" -lt 3 ]; then
  echo "  services look incomplete -- starting the stack (docker compose up -d)..."
  docker compose up -d
  echo "  waiting for backend health..."
  for i in $(seq 1 30); do
    curl -fsS "${SENTINEL_BACKEND_URL:-http://localhost:8001}/health" >/dev/null 2>&1 && break
    sleep 2
  done
fi
curl -fsS "${SENTINEL_BACKEND_URL:-http://localhost:8001}/health" >/dev/null || {
  echo "  FAIL: backend did not become healthy."
  exit 1
}
echo "  PASS: backend responding."

# --- 2/3. reset + reseed deterministic demo state ------------------------ #
echo "\n[2/5] resetting + reseeding deterministic demo data..."
./scripts/reset_demo.sh
echo "  PASS: demo dataset reset (production seed code path, not fixtures)."

# --- 4. optional: 50-camera onboarding + real pipeline burst ------------- #
if [ "$1" = "--full" ]; then
  echo "\n[3/5] full rehearsal: 50-camera onboarding + real AI pipeline burst..."
  "$PYTHON" scripts/hackathon_rehearsal.py \
    --backend-url "${SENTINEL_BACKEND_URL:-http://localhost:8001}" \
    --admin-user "${ADMIN_USERNAME:-admin}" \
    --admin-password "${ADMIN_PASSWORD:-local-admin-pass}" \
    --ingest-key "${INGEST_API_KEY:-local-hackathon-ingest-key}" \
    --pipeline-cameras "${REHEARSAL_PIPELINE_CAMERAS:-5}" \
    --pipeline-duration "${REHEARSAL_PIPELINE_DURATION:-20}" \
    --json-out "$TMP_JSON" || { echo "  FAIL: rehearsal reported failing checks -- see above."; exit 1; }
else
  echo "\n[3/5] verifying the demo scenario (API checks only -- pass --full for a real 50-camera + pipeline rehearsal)..."
  "$PYTHON" scripts/hackathon_rehearsal.py \
    --backend-url "${SENTINEL_BACKEND_URL:-http://localhost:8001}" \
    --admin-user "${ADMIN_USERNAME:-admin}" \
    --admin-password "${ADMIN_PASSWORD:-local-admin-pass}" \
    --skip-pipeline-burst \
    --json-out "$TMP_JSON" || { echo "  FAIL: verification reported failing checks -- see above."; exit 1; }
fi

# --- 5. read-only infrastructure health check ----------------------------- #
echo "\n[4/5] infrastructure health check..."
"$PYTHON" scripts/hackathon_health_check.py \
  --backend-url "${SENTINEL_BACKEND_URL:-http://localhost:8001}" \
  --admin-user "${ADMIN_USERNAME:-admin}" \
  --admin-password "${ADMIN_PASSWORD:-local-admin-pass}" || {
  echo "  FAIL: infrastructure health check reported failures -- see above."
  exit 1
}

# --- final summary, built ONLY from what was actually verified ----------- #
echo "\n[5/5] building summary from verified results..."
"$PYTHON" - "$TMP_JSON" <<'PYEOF'
import json, sys

with open(sys.argv[1]) as f:
    data = json.load(f)

by_name = {c["name"]: c for c in data["checks"]}

def ok(key_substr):
    for name, c in by_name.items():
        if key_substr in name:
            return c["passed"], c.get("detail", "")
    return False, ""

cams_ok, cams_detail = ok("bulk onboarding")
sight_ok, sight_detail = ok("designated vehicle search")
wl_ok, _ = ok("watchlist:")
alert_ok, _ = ok("alert:")
journey_ok, journey_detail = ok("journey:")
inv_ok, _ = ok("investigation workspace")
inc_ok, inc_detail = ok("incident exists")
case_ok, case_detail = ok("case exists")
report_ok, _ = ok("report generation")

n_cams = cams_detail.split(" ")[0] if cams_ok and cams_detail else "n/a"
n_sightings = sight_detail.split(" ")[0] if sight_ok and sight_detail else "0"

print()
print("SENTINEL DEMO READY" if data["all_passed"] else "SENTINEL DEMO -- NOT READY (see failing checks above)")
print()
print(f"Cameras: {n_cams}")
print("Vehicle: GJ18TC0450")
print(f"Sightings: {n_sightings}")
print(f"Watchlist: {'MATCH' if wl_ok else 'NOT VERIFIED'}")
print(f"Alert: {'GENERATED' if alert_ok else 'NOT VERIFIED'}")
print(f"Journey: {'READY' if journey_ok else 'NOT VERIFIED'}")
print(f"Investigation: {'READY' if inv_ok else 'NOT VERIFIED'}")
print(f"Incident: {'READY' if inc_ok else 'NOT VERIFIED'} {inc_detail}")
print(f"Case: {'READY' if case_ok else 'NOT VERIFIED'} {case_detail}")
print(f"Report: {'READY' if report_ok else 'NOT VERIFIED'}")
print()
print(f"({data['passed']}/{data['total']} rehearsal checks passed -- frontend at http://localhost:{__import__('os').environ.get('FRONTEND_HOST_PORT', '3000')})")
sys.exit(0 if data["all_passed"] else 1)
PYEOF
