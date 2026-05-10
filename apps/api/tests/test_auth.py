"""Tests for the M0.3 auth stubs.

Both /auth/login and /auth/register return RFC 7807 envelopes with status 501.
The third test confirms Pydantic validation runs BEFORE the handler — a
malformed body returns 422 (validation error), not 501 (unreached handler).

M1.x rewrites these tests against the real auth flow.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _valid_body() -> dict[str, str]:
    return {"email": "helen@example.test", "password": "changeme123"}


def test_login_returns_501_with_problem_envelope(client: TestClient) -> None:
    r = client.post("/api/v1/auth/login", json=_valid_body())
    assert r.status_code == 501
    body = r.json()
    # RFC 7807 envelope per plan v1.2 §7
    assert body["status"] == 501
    assert body["title"]
    assert body["instance"] == "/api/v1/auth/login"
    # Detail mentions M1.x so reviewers immediately see why it's a stub.
    assert "M1.x" in (body.get("detail") or body["title"])


def test_register_returns_501_with_problem_envelope(client: TestClient) -> None:
    r = client.post("/api/v1/auth/register", json=_valid_body())
    assert r.status_code == 501
    body = r.json()
    assert body["status"] == 501
    assert body["instance"] == "/api/v1/auth/register"


def test_register_validation_runs_before_501(client: TestClient) -> None:
    """Malformed body should trip Pydantic validation (422), not reach the 501 handler."""
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "h@example.test", "password": "short"},  # password < 8 chars
    )
    assert r.status_code == 422


def test_login_missing_field_returns_422(client: TestClient) -> None:
    """Missing required fields are caught by FastAPI's validator (422)."""
    r = client.post("/api/v1/auth/login", json={"email": "h@example.test"})
    assert r.status_code == 422


def test_auth_endpoints_appear_in_openapi(client: TestClient) -> None:
    """Both stubs must show up in the OpenAPI schema with the documented response shape."""
    r = client.get("/api/v1/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/auth/register" in paths
    # Both expose POST and document a 501 response.
    assert "post" in paths["/api/v1/auth/login"]
    assert "501" in paths["/api/v1/auth/login"]["post"]["responses"]
