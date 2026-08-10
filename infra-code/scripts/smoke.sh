#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
KONG_URL="${KONG_URL:-http://localhost:8080}"
TOKEN="$(make -s token)"
echo "POST $KONG_URL/chat"
curl -sS --fail-with-body --max-time 180 -X POST "$KONG_URL/chat" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"Hello from the smoke test. What is 2+2?"}'
echo
echo "POST $KONG_URL/chat/sync"
curl -sS --fail-with-body --max-time 180 -X POST "$KONG_URL/chat/sync" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"Reply with exactly: SMOKE OK"}'
echo
