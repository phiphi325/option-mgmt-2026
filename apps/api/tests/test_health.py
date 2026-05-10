"""Smoke tests for /health, /healthz, /version."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_endpoint(client: TestClient) -> None:
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["uptime_seconds"] >= 0
    # DB may be unreachable in unit-test environments; "degraded" is acceptable.
    assert body["db"] in ("ok", "degraded")
    assert body["version"]
    assert body["engine_version"]
    assert body["weights_version"]


def test_healthz_alias(client: TestClient) -> None:
    """/healthz is an alias for /health (per v1.2 §22.7)."""
    r = client.get("/api/v1/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_version_endpoint(client: TestClient) -> None:
    r = client.get("/api/v1/version")
    assert r.status_code == 200
    body = r.json()
    assert body["version"]
    assert body["engine_version"]
    assert body["weights_version"] == "v2.0"  # per v1.2 §22.13 multiplicative penalties
    assert "git_sha" in body
