"""CSV import endpoints — 5 endpoints, one per resource (M1.17).

Per plan v1.2 §7 + §10 (canonical CSV formats) + §17 M1.17.

  POST /data/positions/import-csv         (multipart file)
  POST /data/option-positions/import-csv  (multipart file)
  POST /data/chain/import-csv             (multipart file)
  POST /data/iv/import-csv                (multipart file)
  POST /data/events/import-csv            (multipart file)

All require authentication. Body is `multipart/form-data` with a
single `file` field. Response shape is uniform — see
`app/schemas/data_import.py::CsvImportResponse`.

V1 file-size cap: 10 MB enforced at the router layer. Above that → 413.

§22.12 enforcement: `import_iv_history` raises ValueError on
post-insert counts below 30; this router maps that to HTTP 422.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_authenticated_user_id, get_session
from app.schemas.data_import import CsvImportResponse
from app.services.csv_import_service import (
    import_chain,
    import_events,
    import_iv_history,
    import_option_positions,
    import_positions,
)

router = APIRouter(prefix="/data", tags=["data"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
AuthedUserDep = Annotated[str, Depends(get_authenticated_user_id)]

_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB


async def _read_upload(file: UploadFile) -> bytes:
    """Read the upload into memory with a size cap. 413 on overflow."""
    data = await file.read()
    if len(data) > _MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"file exceeds {_MAX_FILE_BYTES // 1024 // 1024} MB limit",
        )
    return data


@router.post(
    "/positions/import-csv",
    response_model=CsvImportResponse,
    summary="Upload positions.csv (upsert into positions)",
)
async def import_positions_endpoint(
    session: SessionDep,
    user_id: AuthedUserDep,
    file: Annotated[UploadFile, File(description="positions.csv per master plan §10")],
) -> CsvImportResponse:
    data = await _read_upload(file)
    return await import_positions(session=session, user_id=user_id, file_bytes=data)


@router.post(
    "/option-positions/import-csv",
    response_model=CsvImportResponse,
    summary="Upload option_positions.csv (upsert into option_positions)",
)
async def import_option_positions_endpoint(
    session: SessionDep,
    user_id: AuthedUserDep,
    file: Annotated[UploadFile, File(description="option_positions.csv per master plan §10")],
) -> CsvImportResponse:
    data = await _read_upload(file)
    return await import_option_positions(session=session, user_id=user_id, file_bytes=data)


@router.post(
    "/chain/import-csv",
    response_model=CsvImportResponse,
    summary="Upload chain.csv (append-only into option_chain_snapshots; dedupes exact matches)",
)
async def import_chain_endpoint(
    session: SessionDep,
    user_id: AuthedUserDep,
    file: Annotated[UploadFile, File(description="chain.csv per master plan §10")],
) -> CsvImportResponse:
    data = await _read_upload(file)
    return await import_chain(session=session, user_id=user_id, file_bytes=data)


@router.post(
    "/iv/import-csv",
    response_model=CsvImportResponse,
    summary="Upload iv_history.csv (upsert; §22.12 row-count validation)",
)
async def import_iv_endpoint(
    session: SessionDep,
    user_id: AuthedUserDep,
    file: Annotated[UploadFile, File(description="iv_history.csv per master plan §10 + §22.5")],
) -> CsvImportResponse:
    data = await _read_upload(file)
    try:
        return await import_iv_history(session=session, user_id=user_id, file_bytes=data)
    except ValueError as exc:
        # §22.12 — count(*) < 30 after the upload.
        if "insufficient_iv_history" in str(exc):
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/events/import-csv",
    response_model=CsvImportResponse,
    summary="Upload events.csv (insert; dedupes on (ticker, kind, scheduled_at, source))",
)
async def import_events_endpoint(
    session: SessionDep,
    user_id: AuthedUserDep,
    file: Annotated[UploadFile, File(description="events.csv per master plan §10")],
) -> CsvImportResponse:
    data = await _read_upload(file)
    return await import_events(session=session, user_id=user_id, file_bytes=data)
