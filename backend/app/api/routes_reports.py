"""Report download routes — PDF and Excel block plans."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services import reports

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/pdf")
def report_pdf(period: str = "weekly", db: Session = Depends(get_db)):
    data = reports.build_pdf(db, period)
    return StreamingResponse(
        iter([data]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=block_plan_{period}.pdf"},
    )


@router.get("/excel")
def report_excel(period: str = "weekly", db: Session = Depends(get_db)):
    data = reports.build_excel(db, period)
    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=block_plan_{period}.xlsx"},
    )
