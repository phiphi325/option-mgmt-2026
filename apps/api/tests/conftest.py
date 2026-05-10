"""Pytest fixtures for apps/api.

Sets a deterministic JWT_SECRET for tests BEFORE importing app.main, so the
Settings model's min_length=16 validation passes in CI environments that don't
provide it.

The DB-backed tests in this conftest do not require a live Postgres; the
health endpoint reports `db: "degraded"` when the DB is unreachable, which
the smoke tests accept. M0.5+ adds a transactional Postgres fixture
(pytest-postgresql) for integration tests that exercise the schema.
"""

from __future__ import annotations

import os

# Set defaults BEFORE app imports so Settings validation passes.
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-at-least-16-chars-long")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:dev@localhost:5432/msft_engine_test",
)

from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    """A FastAPI TestClient that runs the app in-process (no real network)."""
    with TestClient(app) as c:
        yield c
