"""Local-dev seed script.

M0.2 stub. The full Helen-shaped seed (5000 MSFT shares, 60d IV history with
OHLC, short call position, 4 events, chain snapshot covering 3 expiries) lands
in M1.x once the engine exists to validate that the seed produces a coherent
DailyDecision. Reference: plan v1.2 §21 + §22.5.

Run after applying migrations:

    docker compose up -d postgres
    cd apps/api && uv run alembic upgrade head
    uv run python scripts/seed_local.py
"""

from __future__ import annotations

import sys


def main() -> int:
    print("[M0.2] seed_local.py: stub — full Helen-shaped seed lands in M1.x")
    print()
    print("       Schema is in place; once engines exist (M1.x) this script will:")
    print("         - create user helen@example.test (argon2 password 'changeme')")
    print("         - persist Helen's UserStrategyProfile (balanced)")
    print("         - insert 5000 MSFT shares @ $400.12 cost basis")
    print("         - insert 1 short call (5x C415 expiring 2026-05-16 @ $2.85)")
    print("         - insert 60 days iv_history with OHLC for trend_strength")
    print("         - insert 4 events (earnings, FOMC, OpEx weekly, OpEx monthly)")
    print("         - insert chain snapshot (3 expiries, ~120 strikes)")
    print()
    print("       The first /engine/daily-plan call against this seed should")
    print("       return a coherent DailyDecision in < 5s on a M3 MacBook.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
