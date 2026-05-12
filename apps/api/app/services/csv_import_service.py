"""CSV import service — 5 functions per plan v1.2 §10 canonical formats (M1.17).

Per plan v1.2 §7 + §10 + §17 M1.17 + §22.12 (IV history validation).

Five public functions, one per CSV resource. Each accepts a streaming
file handle, parses row-by-row, validates per-row, batches the upserts,
and returns `(inserted, updated, skipped, errors, warnings)`.

Canonical CSV headers (§10):

  positions.csv         : ticker,qty,avg_cost,opened_at
  option_positions.csv  : ticker,side,kind,strike,expiry,qty,opened_at,opened_price,status
  chain.csv             : ticker,fetched_at,expiry,strike,kind,bid,ask,last,oi,volume,iv,delta,gamma,theta,vega
  iv_history.csv        : ticker,ts,atm_iv_30d,iv_rank,iv_percentile,hv_30,high,low,close
  events.csv            : ticker,kind,scheduled_at,source,notes

Idempotency strategy per resource:
  positions          → ON CONFLICT (user_id, ticker, opened_at) DO UPDATE
  option_positions   → ON CONFLICT (user_id, ticker, side, kind, strike, expiry, opened_at) DO UPDATE
  chain              → append-only; dedupe exact (ticker, fetched_at, expiry, strike, kind) at upload
  iv_history         → ON CONFLICT (ticker, ts) DO UPDATE   (PK from 0001_init)
  events             → dedupe on (ticker, kind, scheduled_at, source) at upload (no DB UNIQUE)

§22.12 validation: after `import_iv_history`, count rows for the ticker.
If < 30, the upload is rejected and rows are rolled back (raises a
sentinel ValueError("insufficient_iv_history") for the router to map
to 422). 30–59 rows → soft warning (kept in DB but tagged in response).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.data_import import CsvImportError, CsvImportResponse

# ----------------------------------------------------------------------
# Generic helpers
# ----------------------------------------------------------------------


def _parse_decimal(raw: str, field: str, line: int) -> tuple[Decimal | None, CsvImportError | None]:
    s = (raw or "").strip()
    if s == "":
        return None, None
    try:
        return Decimal(s), None
    except (InvalidOperation, ValueError):
        return None, CsvImportError(line=line, column=field, message=f"invalid decimal: {raw!r}")


def _parse_int(raw: str, field: str, line: int) -> tuple[int | None, CsvImportError | None]:
    s = (raw or "").strip()
    if s == "":
        return None, None
    try:
        return int(s), None
    except ValueError:
        return None, CsvImportError(line=line, column=field, message=f"invalid integer: {raw!r}")


def _parse_required_str(raw: str, field: str, line: int) -> tuple[str | None, CsvImportError | None]:
    s = (raw or "").strip()
    if s == "":
        return None, CsvImportError(line=line, column=field, message="required field is empty")
    return s, None


def _parse_required_decimal(raw: str, field: str, line: int) -> tuple[Decimal | None, CsvImportError | None]:
    value, err = _parse_decimal(raw, field, line)
    if err is not None:
        return None, err
    if value is None:
        return None, CsvImportError(line=line, column=field, message="required field is empty")
    return value, None


def _parse_required_int(raw: str, field: str, line: int) -> tuple[int | None, CsvImportError | None]:
    value, err = _parse_int(raw, field, line)
    if err is not None:
        return None, err
    if value is None:
        return None, CsvImportError(line=line, column=field, message="required field is empty")
    return value, None


def _read_csv_rows(file_bytes: bytes) -> Iterable[tuple[int, dict[str, str]]]:
    """Yield (line_number, row_dict) tuples. Line 1 is the header; data
    starts at line 2."""
    text_data = file_bytes.decode("utf-8-sig")  # tolerate BOM
    reader = csv.DictReader(io.StringIO(text_data))
    yield from enumerate(reader, start=2)


# ----------------------------------------------------------------------
# positions
# ----------------------------------------------------------------------


async def import_positions(
    *,
    session: AsyncSession,
    user_id: str,
    file_bytes: bytes,
) -> CsvImportResponse:
    """Upsert positions.csv rows. ON CONFLICT (user_id, ticker, opened_at) DO UPDATE."""
    inserted = updated = skipped = 0
    errors: list[CsvImportError] = []

    for line, row in _read_csv_rows(file_bytes):
        ticker, err = _parse_required_str(row.get("ticker", ""), "ticker", line)
        if err is not None:
            errors.append(err)

            skipped += 1

            continue
        qty, err = _parse_required_decimal(row.get("qty", ""), "qty", line)
        if err is not None:
            errors.append(err)

            skipped += 1

            continue
        avg_cost, err = _parse_required_decimal(row.get("avg_cost", ""), "avg_cost", line)
        if err is not None:
            errors.append(err)

            skipped += 1

            continue
        opened_at, err = _parse_required_str(row.get("opened_at", ""), "opened_at", line)
        if err is not None:
            errors.append(err)

            skipped += 1

            continue

        result = await session.execute(
            text(
                """
                INSERT INTO positions (user_id, ticker, qty, avg_cost, opened_at)
                VALUES (:user_id, :ticker, :qty, :avg_cost, CAST(:opened_at AS timestamptz))
                ON CONFLICT (user_id, ticker, opened_at) DO UPDATE
                  SET qty = EXCLUDED.qty, avg_cost = EXCLUDED.avg_cost
                RETURNING (xmax = 0) AS inserted;
                """
            ),
            {
                "user_id": user_id,
                "ticker": ticker,
                "qty": qty,
                "avg_cost": avg_cost,
                "opened_at": opened_at,
            },
        )
        outcome = result.scalar()
        if outcome is True:
            inserted += 1
        else:
            updated += 1

    await session.commit()
    return CsvImportResponse(
        inserted=inserted, updated=updated, skipped=skipped, errors=errors
    )


# ----------------------------------------------------------------------
# option_positions
# ----------------------------------------------------------------------


async def import_option_positions(
    *,
    session: AsyncSession,
    user_id: str,
    file_bytes: bytes,
) -> CsvImportResponse:
    """Upsert option_positions.csv rows.

    ON CONFLICT (user_id, ticker, side, kind, strike, expiry, opened_at) DO UPDATE.
    """
    inserted = updated = skipped = 0
    errors: list[CsvImportError] = []

    for line, row in _read_csv_rows(file_bytes):
        # Required strings
        ticker, err = _parse_required_str(row.get("ticker", ""), "ticker", line)
        if err is not None:
            errors.append(err)

            skipped += 1

            continue
        side, err = _parse_required_str(row.get("side", ""), "side", line)
        if err is not None:
            errors.append(err)

            skipped += 1

            continue
        kind, err = _parse_required_str(row.get("kind", ""), "kind", line)
        if err is not None:
            errors.append(err)

            skipped += 1

            continue

        if side not in ("BUY", "SELL"):
            errors.append(CsvImportError(line=line, column="side", message=f"must be BUY or SELL; got {side!r}"))
            skipped += 1

            continue
        if kind not in ("PUT", "CALL"):
            errors.append(CsvImportError(line=line, column="kind", message=f"must be PUT or CALL; got {kind!r}"))
            skipped += 1

            continue

        strike, err = _parse_required_decimal(row.get("strike", ""), "strike", line)
        if err is not None:
            errors.append(err)

            skipped += 1

            continue
        expiry, err = _parse_required_str(row.get("expiry", ""), "expiry", line)
        if err is not None:
            errors.append(err)

            skipped += 1

            continue
        qty, err = _parse_required_int(row.get("qty", ""), "qty", line)
        if err is not None:
            errors.append(err)

            skipped += 1

            continue
        opened_at, err = _parse_required_str(row.get("opened_at", ""), "opened_at", line)
        if err is not None:
            errors.append(err)

            skipped += 1

            continue
        opened_price, err = _parse_required_decimal(row.get("opened_price", ""), "opened_price", line)
        if err is not None:
            errors.append(err)

            skipped += 1

            continue

        status = (row.get("status", "OPEN") or "OPEN").strip()

        result = await session.execute(
            text(
                """
                INSERT INTO option_positions (
                    user_id, ticker, side, kind, strike, expiry,
                    qty, opened_at, opened_price, status
                )
                VALUES (
                    :user_id, :ticker, CAST(:side AS option_side),
                    CAST(:kind AS option_kind), :strike,
                    CAST(:expiry AS date), :qty,
                    CAST(:opened_at AS timestamptz), :opened_price,
                    CAST(:status AS option_status)
                )
                ON CONFLICT (user_id, ticker, side, kind, strike, expiry, opened_at) DO UPDATE
                  SET qty = EXCLUDED.qty,
                      opened_price = EXCLUDED.opened_price,
                      status = EXCLUDED.status
                RETURNING (xmax = 0) AS inserted;
                """
            ),
            {
                "user_id": user_id,
                "ticker": ticker,
                "side": side,
                "kind": kind,
                "strike": strike,
                "expiry": expiry,
                "qty": qty,
                "opened_at": opened_at,
                "opened_price": opened_price,
                "status": status,
            },
        )
        outcome = result.scalar()
        if outcome is True:
            inserted += 1
        else:
            updated += 1

    await session.commit()
    return CsvImportResponse(
        inserted=inserted, updated=updated, skipped=skipped, errors=errors
    )


# ----------------------------------------------------------------------
# chain
# ----------------------------------------------------------------------


async def import_chain(
    *,
    session: AsyncSession,
    user_id: str,  # noqa: ARG001 - chain is shared across users; kept in signature for symmetry
    file_bytes: bytes,
) -> CsvImportResponse:
    """Insert chain.csv rows into option_chain_snapshots.

    The chain table is append-only (§6 schema). To prevent duplicate-exact
    re-uploads from doubling row counts, dedupe per upload on
    (ticker, fetched_at, expiry, strike, kind) BEFORE insert. Identical
    rows in the same CSV are also collapsed to one insert.
    """
    inserted = skipped = 0
    errors: list[CsvImportError] = []
    seen_in_csv: set[tuple[Any, ...]] = set()

    for line, row in _read_csv_rows(file_bytes):
        ticker, err = _parse_required_str(row.get("ticker", ""), "ticker", line)
        if err is not None:
            errors.append(err)

            skipped += 1

            continue
        fetched_at, err = _parse_required_str(row.get("fetched_at", ""), "fetched_at", line)
        if err is not None:
            errors.append(err)

            skipped += 1

            continue
        expiry, err = _parse_required_str(row.get("expiry", ""), "expiry", line)
        if err is not None:
            errors.append(err)

            skipped += 1

            continue
        strike, err = _parse_required_decimal(row.get("strike", ""), "strike", line)
        if err is not None:
            errors.append(err)

            skipped += 1

            continue
        kind, err = _parse_required_str(row.get("kind", ""), "kind", line)
        if err is not None:
            errors.append(err)

            skipped += 1

            continue
        if kind not in ("PUT", "CALL"):
            errors.append(CsvImportError(line=line, column="kind", message=f"must be PUT or CALL; got {kind!r}"))
            skipped += 1

            continue

        natural_key = (ticker, fetched_at, expiry, str(strike), kind)
        if natural_key in seen_in_csv:
            skipped += 1
            continue
        seen_in_csv.add(natural_key)

        # Check if exact-match row already exists in DB (dedupe vs prior uploads).
        existing = await session.execute(
            text(
                """
                SELECT 1 FROM option_chain_snapshots
                WHERE ticker = :ticker AND fetched_at = CAST(:fetched_at AS timestamptz)
                  AND expiry = CAST(:expiry AS date) AND strike = :strike
                  AND kind = CAST(:kind AS option_kind)
                LIMIT 1;
                """
            ),
            {
                "ticker": ticker, "fetched_at": fetched_at,
                "expiry": expiry, "strike": strike, "kind": kind,
            },
        )
        if existing.first() is not None:
            skipped += 1
            continue

        # Optional fields
        bid, _ = _parse_decimal(row.get("bid", ""), "bid", line)
        ask, _ = _parse_decimal(row.get("ask", ""), "ask", line)
        last_, _ = _parse_decimal(row.get("last", ""), "last", line)
        oi, _ = _parse_int(row.get("oi", ""), "oi", line)
        volume, _ = _parse_int(row.get("volume", ""), "volume", line)
        iv, _ = _parse_decimal(row.get("iv", ""), "iv", line)
        delta, _ = _parse_decimal(row.get("delta", ""), "delta", line)
        gamma, _ = _parse_decimal(row.get("gamma", ""), "gamma", line)
        theta, _ = _parse_decimal(row.get("theta", ""), "theta", line)
        vega, _ = _parse_decimal(row.get("vega", ""), "vega", line)
        source = (row.get("source", "csv") or "csv").strip()
        mark = bid + (ask - bid) / 2 if (bid is not None and ask is not None) else last_

        await session.execute(
            text(
                """
                INSERT INTO option_chain_snapshots (
                    ticker, fetched_at, expiry, strike, kind,
                    bid, ask, last, mark, oi, volume,
                    iv, delta, gamma, theta, vega, source
                )
                VALUES (
                    :ticker, CAST(:fetched_at AS timestamptz),
                    CAST(:expiry AS date), :strike,
                    CAST(:kind AS option_kind),
                    :bid, :ask, :last, :mark, :oi, :volume,
                    :iv, :delta, :gamma, :theta, :vega, :source
                );
                """
            ),
            {
                "ticker": ticker, "fetched_at": fetched_at, "expiry": expiry,
                "strike": strike, "kind": kind,
                "bid": bid, "ask": ask, "last": last_, "mark": mark,
                "oi": oi, "volume": volume,
                "iv": iv, "delta": delta, "gamma": gamma,
                "theta": theta, "vega": vega, "source": source,
            },
        )
        inserted += 1

    await session.commit()
    return CsvImportResponse(
        inserted=inserted, updated=0, skipped=skipped, errors=errors
    )


# ----------------------------------------------------------------------
# iv_history — with §22.12 validation
# ----------------------------------------------------------------------


async def import_iv_history(
    *,
    session: AsyncSession,
    user_id: str,  # noqa: ARG001 - iv_history is shared; kept in signature for symmetry
    file_bytes: bytes,
) -> CsvImportResponse:
    """Upsert iv_history.csv rows. ON CONFLICT (ticker, ts) DO UPDATE.

    §22.12 post-insert validation:
      - count(*) < 30 for the uploaded ticker  →  raises ValueError("insufficient_iv_history")
        (rolled back; router maps to 422)
      - 30 ≤ count < 60                        →  soft warning in response
      - 60 ≤ count < 252                       →  info-level warning
      - count ≥ 252                            →  no warning
    """
    inserted = updated = skipped = 0
    errors: list[CsvImportError] = []
    tickers_touched: set[str] = set()

    for line, row in _read_csv_rows(file_bytes):
        ticker, err = _parse_required_str(row.get("ticker", ""), "ticker", line)
        if err is not None:
            errors.append(err)

            skipped += 1

            continue
        ts, err = _parse_required_str(row.get("ts", ""), "ts", line)
        if err is not None:
            errors.append(err)

            skipped += 1

            continue

        atm_iv_30d, _ = _parse_decimal(row.get("atm_iv_30d", ""), "atm_iv_30d", line)
        atm_iv_60d, _ = _parse_decimal(row.get("atm_iv_60d", ""), "atm_iv_60d", line)
        iv_rank, _ = _parse_decimal(row.get("iv_rank", ""), "iv_rank", line)
        iv_percentile, _ = _parse_decimal(row.get("iv_percentile", ""), "iv_percentile", line)
        high, _ = _parse_decimal(row.get("high", ""), "high", line)
        low, _ = _parse_decimal(row.get("low", ""), "low", line)
        close, _ = _parse_decimal(row.get("close", ""), "close", line)

        result = await session.execute(
            text(
                """
                INSERT INTO iv_history (
                    ticker, ts, atm_iv_30d, atm_iv_60d,
                    iv_rank, iv_percentile,
                    high, low, close
                )
                VALUES (
                    :ticker, CAST(:ts AS timestamptz),
                    :atm_iv_30d, :atm_iv_60d,
                    :iv_rank, :iv_percentile,
                    :high, :low, :close
                )
                ON CONFLICT (ticker, ts) DO UPDATE
                  SET atm_iv_30d = EXCLUDED.atm_iv_30d,
                      atm_iv_60d = EXCLUDED.atm_iv_60d,
                      iv_rank = EXCLUDED.iv_rank,
                      iv_percentile = EXCLUDED.iv_percentile,
                      high = EXCLUDED.high,
                      low = EXCLUDED.low,
                      close = EXCLUDED.close
                RETURNING (xmax = 0) AS inserted;
                """
            ),
            {
                "ticker": ticker, "ts": ts,
                "atm_iv_30d": atm_iv_30d, "atm_iv_60d": atm_iv_60d,
                "iv_rank": iv_rank, "iv_percentile": iv_percentile,
                "high": high, "low": low, "close": close,
            },
        )
        outcome = result.scalar()
        if outcome is True:
            inserted += 1
        else:
            updated += 1
        # `ticker` was validated above (early-return on None); narrow for mypy.
        assert ticker is not None
        tickers_touched.add(ticker)

    # §22.12 post-insert count check
    warnings: list[str] = []
    for ticker in sorted(tickers_touched):
        count_result = await session.execute(
            text("SELECT COUNT(*) FROM iv_history WHERE ticker = :ticker;"),
            {"ticker": ticker},
        )
        count = count_result.scalar()
        if not isinstance(count, int):
            count = int(count or 0)
        if count < 30:
            # §22.12: insufficient — roll back the entire transaction
            await session.rollback()
            raise ValueError(
                f"insufficient_iv_history: ticker={ticker!r} has only {count} "
                f"rows after upload; IV rank/percentile require >= 30."
            )
        elif count < 60:
            warnings.append(
                f"{ticker}: only {count} iv_history rows present; "
                f"iv_percentile is less reliable with <60 days. (§22.12)"
            )
        elif count < 252:
            warnings.append(
                f"{ticker}: {count} iv_history rows; iv_rank uses {count}-day "
                f"lookback (target: 252). (§22.12 info)"
            )

    await session.commit()
    return CsvImportResponse(
        inserted=inserted, updated=updated, skipped=skipped,
        errors=errors, validation_warnings=warnings,
    )


# ----------------------------------------------------------------------
# events
# ----------------------------------------------------------------------


async def import_events(
    *,
    session: AsyncSession,
    user_id: str,  # noqa: ARG001 - events are shared; kept in signature for symmetry
    file_bytes: bytes,
) -> CsvImportResponse:
    """Insert events.csv rows. Dedupe on (ticker, kind, scheduled_at, source)
    at upload time — no DB-level UNIQUE constraint."""
    inserted = skipped = 0
    errors: list[CsvImportError] = []
    seen_in_csv: set[tuple[Any, ...]] = set()

    valid_kinds = {
        "earnings", "fomc", "build", "launch",
        "opex_monthly", "opex_weekly", "custom",
    }

    for line, row in _read_csv_rows(file_bytes):
        # ticker is OPTIONAL for events (e.g. FOMC has no ticker per §10)
        ticker_raw = (row.get("ticker", "") or "").strip()
        ticker: str | None = ticker_raw if ticker_raw else None

        kind, err = _parse_required_str(row.get("kind", ""), "kind", line)
        if err is not None:
            errors.append(err)

            skipped += 1

            continue
        if kind not in valid_kinds:
            errors.append(CsvImportError(line=line, column="kind", message=f"must be one of {sorted(valid_kinds)}; got {kind!r}"))
            skipped += 1

            continue
        scheduled_at, err = _parse_required_str(row.get("scheduled_at", ""), "scheduled_at", line)
        if err is not None:
            errors.append(err)

            skipped += 1

            continue
        source, err = _parse_required_str(row.get("source", ""), "source", line)
        if err is not None:
            errors.append(err)

            skipped += 1

            continue
        notes = (row.get("notes", "") or "").strip() or None

        natural_key = (ticker, kind, scheduled_at, source)
        if natural_key in seen_in_csv:
            skipped += 1
            continue
        seen_in_csv.add(natural_key)

        existing = await session.execute(
            text(
                """
                SELECT 1 FROM events
                WHERE (:ticker IS NULL AND ticker IS NULL OR ticker = :ticker)
                  AND kind = CAST(:kind AS event_kind)
                  AND scheduled_at = CAST(:scheduled_at AS timestamptz)
                  AND source = :source
                LIMIT 1;
                """
            ),
            {
                "ticker": ticker, "kind": kind,
                "scheduled_at": scheduled_at, "source": source,
            },
        )
        if existing.first() is not None:
            skipped += 1
            continue

        await session.execute(
            text(
                """
                INSERT INTO events (ticker, kind, scheduled_at, source, notes)
                VALUES (:ticker, CAST(:kind AS event_kind),
                        CAST(:scheduled_at AS timestamptz), :source, :notes);
                """
            ),
            {
                "ticker": ticker, "kind": kind,
                "scheduled_at": scheduled_at, "source": source, "notes": notes,
            },
        )
        inserted += 1

    await session.commit()
    return CsvImportResponse(
        inserted=inserted, updated=0, skipped=skipped, errors=errors
    )


# ----------------------------------------------------------------------
# Aliases for clean router imports
# ----------------------------------------------------------------------


__all__ = [
    "import_chain",
    "import_events",
    "import_iv_history",
    "import_option_positions",
    "import_positions",
]
