from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readiness(session: Session = Depends(get_db)) -> dict[str, str]:
    try:
        session.execute(text("SELECT 1"))
    except Exception as error:
        raise HTTPException(status_code=503, detail="Database is unavailable.") from error
    return {"status": "ready"}
