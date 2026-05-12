"""Pytest fixtures for apps/api.

Sets a deterministic JWT_SECRET for tests BEFORE importing app.main, so the
Settings model's min_length=16 validation passes in CI environments that don't
provide it.

The DB-backed tests in this conftest do not require a live Postgres; the
health endpoint reports `db: "degraded"` when the DB is unreachable, which
the smoke tests accept. M0.5+ adds a transactional Postgres fixture
(pytest-postgresql) for integration tests that exercise the schema.

Python-3.9 sandbox shim (M1.14+): the API imports `engine.*` modules
which declare StrEnum subclasses. StrEnum landed in stdlib Python 3.11.
CI runs Python 3.14 (per ADR-0007) — no shim runs there because the
attribute already exists. The shim is a defensive no-op on 3.11+.
"""

from __future__ import annotations

import datetime as _dt
import enum
import os

# 3.9 sandbox StrEnum shim — must run BEFORE any engine import.
if not hasattr(enum, "StrEnum"):
    # noqa UP042: the whole point of this shim is to provide `enum.StrEnum`
    # ON Python 3.9 where it doesn't exist; we can't "inherit from enum.StrEnum"
    # by definition. CI runs Python 3.14 and skips this branch entirely.
    class _StrEnumShim(str, enum.Enum):  # noqa: UP042
        """`enum.StrEnum` substitute for Python 3.9 sandbox testing."""

    enum.StrEnum = _StrEnumShim  # type: ignore[attr-defined]

# 3.9 sandbox `datetime.UTC` shim — landed in Python 3.11. `app.core.security`
# and other API modules `from datetime import UTC`; on the 3.9 sandbox this
# would ImportError without the back-port.
if not hasattr(_dt, "UTC"):
    # ruff UP017 wants `_dt.UTC` but UP017 only fires when the attribute exists
    # (Python 3.11+). On 3.9 we explicitly back-port; suppress the spurious lint.
    _dt.UTC = _dt.timezone.utc  # type: ignore[attr-defined]  # noqa: UP017

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
