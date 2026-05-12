"""Market data read-through — `GET /market/{ticker}/latest` (M1.16b → M1.17).

Per plan v1.2 §7 v1.1 + §22.10 + §17 M1.17.

Convenience read-through powering the Today screen header without
invoking the engine pipeline. Computes max_pain / pcr / expected_move
on-the-fly from the latest chain + iv + hv + events rows.

Auth: NOT required for V1 (matches §7's "convenience endpoint" framing).
Future versions may add per-user rate limiting; the route can be moved
behind auth then.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.schemas.market import MarketLatestSnapshotResponse
from app.services.market_service import get_market_latest_snapshot

router = APIRouter(prefix="/market", tags=["market"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get(
    "/{ticker}/latest",
    response_model=MarketLatestSnapshotResponse,
    summary="Latest market snapshot for a ticker (no engine pipeline call)",
)
async def get_market_latest(
    ticker: str,
    session: SessionDep,
) -> MarketLatestSnapshotResponse:
    """Returns the most-recent chain + iv + hv + event roll-up.

    Raises 422 when prerequisites are missing per §22.10:
      - `iv_history` for ticker has < 30 rows
      - `option_chain_snapshots` empty for ticker
    """
    try:
        return await get_market_latest_snapshot(
            session=session, ticker=ticker.upper()
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
