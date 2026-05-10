"""End-to-end smoke tests for the API stack — M0.7.

These tests exercise a REAL FastAPI process running against a REAL Postgres
database. The M0.5 unit tests use TestClient + a degraded-DB acceptance;
this file does NOT — it requires the full stack to be up.

Per plan v1.2 §17 M0.7 (cross-stack smoke test), per
docs/engineering-principles.md (TDD), per ADR-0006 (RFC 7807).

Scope of assertions:
  - GET /health      200, status="ok", db="ok" (real DB, not "degraded")
  - GET /healthz     alias of /health (per v1.2 §22.7)
  - GET /version     locked version triplet + git_sha
  - POST /auth/login 501 with RFC 7807 envelope (regression check)
  - GET /openapi.json schema serves; key routes registered

Activation:
  - Skipped by default (when env var SMOKE_API_URL is unset).
  - Run via `make smoke` locally (docker compose path), or via the `smoke`
    job in CI (GitHub services + uvicorn-in-background path). Both set
    SMOKE_API_URL to point at the live API.

Failure means: the deployment artifacts are broken, the schema didn't
apply, or one of the M0.3 / M0.6 endpoints is wired wrong. There is no
mock here — that's the whole point.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import httpx
import pytest

# When SMOKE_API_URL is unset (default for `pytest -q`), the whole module
# skips. CI + Makefile set this to point at a running API.
SMOKE_API_URL = os.environ.get("SMOKE_API_URL")

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        not SMOKE_API_URL,
        reason=(
            "SMOKE_API_URL not set; M0.7 smoke tests need a live API. "
            "Run `make smoke` or set SMOKE_API_URL=http://localhost:8000/api/v1"
        ),
    ),
]


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    """Async HTTP client targeting the live API base URL."""
    assert SMOKE_API_URL  # pytestmark guards this; mypy-strict needs the assert
    async with httpx.AsyncClient(base_url=SMOKE_API_URL, timeout=10.0) as client:
        yield client


async def test_health_returns_db_ok(http: httpx.AsyncClient) -> None:
    """Real DB connection → /health reports db: 'ok' (not 'degraded')."""
    r = await http.get("/health")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok", (
        f"Expected db='ok' against a real Postgres; got {body['db']!r}. "
        "If 'degraded', either the DB is unreachable, alembic upgrade did "
        "not run, or the schema is broken."
    )
    assert body["uptime_seconds"] >= 0
    assert body["version"]
    assert body["engine_version"]
    assert body["weights_version"]


async def test_healthz_alias(http: httpx.AsyncClient) -> None:
    """/healthz alias works and reports the same db status (v1.2 §22.7)."""
    r = await http.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"


async def test_version_endpoint(http: httpx.AsyncClient) -> None:
    """/version returns the locked version triplet + git_sha."""
    r = await http.get("/version")
    assert r.status_code == 200
    body = r.json()
    assert body["version"]
    assert body["engine_version"]
    # weights_version is "v2.0" per v1.2 §22.13 (multiplicative penalties).
    assert body["weights_version"] == "v2.0"
    assert "git_sha" in body


async def test_auth_login_stub_returns_501(http: httpx.AsyncClient) -> None:
    """RFC 7807 envelope on /auth/login (M0.3 stub). Live regression check."""
    r = await http.post(
        "/auth/login",
        json={"email": "smoke@example.test", "password": "smoketest123"},
    )
    assert r.status_code == 501
    body = r.json()
    # Per ADR-0006 the envelope shape is: type, title, status, detail, instance.
    assert body["status"] == 501
    assert body["title"]
    assert body["instance"] == "/api/v1/auth/login"


async def test_openapi_schema_includes_all_m03_m06_routes(
    http: httpx.AsyncClient,
) -> None:
    """OpenAPI schema serves and lists every endpoint shipped through M0.6.

    Catches the regression where a router fails to register at app boot
    (e.g. an import error swallowed by FastAPI's lifespan handler).
    """
    r = await http.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    for required in (
        "/api/v1/health",
        "/api/v1/healthz",
        "/api/v1/version",
        "/api/v1/auth/login",
        "/api/v1/auth/register",
    ):
        assert required in paths, f"missing route in OpenAPI: {required}"
