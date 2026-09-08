#!/bin/sh
# Reset the Sentinel AI demo dataset to a clean, deterministic state.
#
#   ./scripts/reset_demo.sh                 # in-place reset (running docker stack)
#   ./scripts/reset_demo.sh --full          # full teardown + rebuild + reseed
#
# In-place: removes only the AI-demo rows (8 cameras, GJ18TC0450 journey,
# INC-*-9001, CASE-*-9001, the stopped-vehicle anomaly) and re-seeds them
# via the real production code paths. Real data + the GJ18TC0450 watchlist
# entry are untouched.
set -e
cd "$(dirname "$0")/.."

if [ "$1" = "--full" ]; then
  echo "[reset_demo] full teardown + rebuild..."
  docker compose --profile ai down -v
  SEED_AI_DEMO=1 docker compose up -d --build
  echo "[reset_demo] done -- fresh stack, migrations 0001->latest, demo seeded."
  exit 0
fi

echo "[reset_demo] in-place reset via the backend container..."
docker compose exec -T -e PYTHONPATH=/app -e SEED_AI_DEMO=1 backend \
  python /scripts/seed_ai_demo.py --reset
echo "[reset_demo] done -- demo dataset is clean and re-seeded."
