"""FastAPI dependency injection — shared DB instance and current user."""
from __future__ import annotations

from fastapi import HTTPException, Request, status

from src.db.repo import PipelineRepo
from ui.backend.auth import COOKIE_NAME, decode_token
from ui.backend.models import TokenData

# Singleton DB repo (connection pool lives here)
_db: PipelineRepo | None = None


def get_db() -> PipelineRepo:
    global _db
    if _db is None:
        _db = PipelineRepo()
    return _db


async def get_current_user(request: Request) -> TokenData:
    """FastAPI dependency that validates the httpOnly JWT cookie."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return decode_token(token)
