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


def test_version_endpoint_engine_version_sourced_from_package(client: TestClient) -> None:
    """M1.24 (Settings consolidation): `engine_version` reported by /version
    matches `engine.version.__version__` from the engine package, NOT a
    Settings literal default that has drifted.

    Per docs/phased-design/phase-1/m1.24-master-decision-goldens.md
    § 'Bundled companion tooling'.
    """
    from engine.version import __version__ as engine_version  # noqa: PLC0415

    r = client.get("/api/v1/version")
    assert r.status_code == 200
    body = r.json()
    assert body["engine_version"] == engine_version, (
        f"/version reports engine_version={body['engine_version']!r} but the "
        f"engine package reports {engine_version!r}. Settings.engine_version "
        f"is supposed to source from engine.version (per M1.24)."
    )


def test_version_endpoint_weights_version_sourced_from_package(client: TestClient) -> None:
    """M1.24: `weights_version` reported by /version matches
    `engine.confidence.DEFAULT_WEIGHTS.version`. Closes the same drift
    class as the engine_version test above.
    """
    from engine.confidence import DEFAULT_WEIGHTS  # noqa: PLC0415

    r = client.get("/api/v1/version")
    body = r.json()
    assert body["weights_version"] == DEFAULT_WEIGHTS.version, (
        f"/version reports weights_version={body['weights_version']!r} but the "
        f"engine package's DEFAULT_WEIGHTS.version is "
        f"{DEFAULT_WEIGHTS.version!r}. Settings.weights_version is supposed "
        f"to source from engine.confidence.DEFAULT_WEIGHTS (per M1.24)."
    )
