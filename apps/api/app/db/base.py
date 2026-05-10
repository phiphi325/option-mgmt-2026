"""SQLAlchemy declarative base.

Models are added in M0.6+ alongside the engine types. The base exists in M0.2
so future migrations can switch from hand-written SQL to Alembic autogenerate
without restructuring.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Root SQLAlchemy declarative base for all ORM models."""
