"""RFC 7807 Problem Details envelope.

Per plan v1.2 §7 every error response uses this shape:

    {
      "type":     "https://errors.msft-engine.local/insufficient-data",
      "title":    "Insufficient data to compute regime",
      "status":   422,
      "detail":   "IV history requires >= 60 trading days; only 12 found",
      "instance": "/api/v1/engine/daily-plan",
      "missing":  ["iv_history.atm_iv_30d (52 days)"]
    }

Additional context is allowed via arbitrary extra fields (`missing` above).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ProblemDetails(BaseModel):
    """RFC 7807 Problem Details — extra fields permitted alongside the standard ones."""

    model_config = ConfigDict(extra="allow")

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None

    def with_extras(self, **extras: Any) -> ProblemDetails:
        """Return a copy with additional fields merged in."""
        merged = self.model_dump(exclude_none=True)
        merged.update(extras)
        return ProblemDetails(**merged)
