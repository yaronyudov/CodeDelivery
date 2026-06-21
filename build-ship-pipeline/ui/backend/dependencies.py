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
    """Validates the httpOnly JWT cookie and confirms the account is still active."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token_data = decode_token(token)

    # Re-check active status so deactivated accounts can't coast on unexpired tokens
    db = get_db()
    user = db.get_user_by_username(token_data.username)
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    return token_data
