"""Authentication: bcrypt password verification + JWT cookie management."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from slowapi import Limiter
from slowapi.util import get_remote_address

from ui.backend.models import LoginRequest, TokenData

# Fail fast — refuse to start with the public fallback string.
_SECRET_KEY = os.environ.get("SECRET_KEY")
if not _SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY environment variable is not set. Generate one with: openssl rand -hex 32"
    )

_ALGORITHM = "HS256"
_ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Pin the bcrypt work factor explicitly rather than relying on passlib's default,
# so the security posture is independent of library version changes.
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


def _real_ip(request: Request) -> str:
    """Client IP that respects X-Real-IP set by the nginx reverse proxy."""
    return (
        request.headers.get("X-Real-IP")
        or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or get_remote_address(request)
    )


_limiter = Limiter(key_func=_real_ip)

router = APIRouter(tags=["auth"])

COOKIE_NAME = "access_token"


# ── Password helpers ──────────────────────────────────────────────────────────


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


# ── JWT helpers ───────────────────────────────────────────────────────────────


def create_access_token(user_id: int, username: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "username": username, "exp": expire}
    return jwt.encode(payload, _SECRET_KEY, algorithm=_ALGORITHM)


def decode_token(token: str) -> TokenData:
    try:
        payload = jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])
        return TokenData(user_id=int(payload["sub"]), username=payload["username"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,  # no JS access → XSS-safe
        secure=True,  # HTTPS only
        samesite="strict",  # CSRF-safe
        max_age=_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/login")
@_limiter.limit("5/15minute")
async def login(request: Request, body: LoginRequest, response: Response):
    """Rate-limited login: 5 attempts per 15 min per real client IP."""
    from ui.backend.dependencies import get_db

    db = get_db()
    user = db.get_user_by_username(body.username)
    if (
        user is None
        or not user.get("is_active")
        or not verify_password(body.password, user["password_hash"])
    ):
        # Same error for missing user vs wrong password (no enumeration)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token(user["id"], user["username"])
    _set_auth_cookie(response, token)
    return {"ok": True}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
async def me(request: Request):
    from ui.backend.dependencies import get_current_user

    user = await get_current_user(request)
    return {"username": user.username, "user_id": user.user_id}
