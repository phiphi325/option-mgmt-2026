#!/usr/bin/env bash
# M0.7 smoke-test runner. Brings up postgres via docker compose, applies the
# Alembic migration, starts the API in the background, and runs the smoke
# pytest. Tears down the API on exit.
#
# Per plan v1.2 §17 M0.7 + docs/engineering-principles.md (TDD).
#
# Usage:
#   bash scripts/run_smoke.sh
#
# Environment overrides (rare):
#   SMOKE_HOST_PORT  port the API listens on locally   (default: 8000)
#   SMOKE_TIMEOUT    seconds to wait for /health      (default: 30)
#
# CI uses a different path: GitHub Actions `services:` provides Postgres
# and the workflow starts uvicorn explicitly. See .github/workflows/ci.yml
# `smoke` job.

set -euo pipefail

PORT="${SMOKE_HOST_PORT:-8000}"
TIMEOUT="${SMOKE_TIMEOUT:-30}"
SMOKE_API_URL="http://localhost:${PORT}/api/v1"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

API_PID=""
cleanup() {
  local exit_code=$?
  if [[ -n "$API_PID" ]]; then
    echo "==> stopping api (pid $API_PID)..."
    kill "$API_PID" 2>/dev/null || true
    wait "$API_PID" 2>/dev/null || true
  fi
  exit "$exit_code"
}
trap cleanup EXIT INT TERM

echo "==> bringing up postgres via docker compose..."
docker compose up -d postgres

echo "==> waiting for postgres to be healthy..."
for i in $(seq 1 20); do
  if docker compose exec -T postgres pg_isready -U postgres -d msft_engine >/dev/null 2>&1; then
    echo "    postgres ready"
    break
  fi
  if [[ $i -eq 20 ]]; then
    echo "    postgres never became ready" >&2
    exit 1
  fi
  sleep 1
done

echo "==> running alembic upgrade head..."
(cd apps/api && uv run alembic upgrade head)

echo "==> starting api in background on :$PORT..."
(
  cd apps/api
  JWT_SECRET="${JWT_SECRET:-dev-secret-not-for-production}" \
  DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://postgres:dev@localhost:5432/msft_engine}" \
    uv run uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --log-level warning
) &
API_PID=$!

echo "==> waiting for api at $SMOKE_API_URL/health (timeout ${TIMEOUT}s)..."
for i in $(seq 1 "$TIMEOUT"); do
  if curl -fsS "$SMOKE_API_URL/health" >/dev/null 2>&1; then
    echo "    api up after ${i}s"
    break
  fi
  if [[ $i -eq "$TIMEOUT" ]]; then
    echo "    api never came up" >&2
    exit 1
  fi
  sleep 1
done

echo "==> running smoke pytest (-m smoke)..."
(cd apps/api && SMOKE_API_URL="$SMOKE_API_URL" uv run pytest -m smoke)
