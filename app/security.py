"""Sesión (JWT en cookie httpOnly), API key de servicio, autorización por rol y rate limit."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, Response, status

from .config import settings

from .permissions import ROLES, normalize_role  # noqa: F401


def public_user(u: dict) -> dict:
    """Forma que consume el front (AuthUser)."""
    name = str(u.get("name", ""))
    initials = u.get("initials") or "".join(p[0] for p in name.split()[:2]).upper()
    return {
        "id": u["id"], "name": name, "email": u.get("email", ""), "role": normalize_role(u.get("role")),
        "projectIds": u.get("projectIds", []), "initials": initials, "avatarColor": u.get("avatarColor", "#64748b"),
        "areaLabel": u.get("areaLabel"),
    }


# ─── JWT ─────────────────────────────────────────────────────────────────────

def create_session_token(user: dict, provider: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user["id"], "email": user.get("email"), "role": user.get("role"), "name": user.get("name"),
               "prv": provider, "iat": int(now.timestamp()), "exp": int((now + timedelta(hours=settings.SESSION_HOURS)).timestamp())}
    return jwt.encode(payload, settings.SESSION_SECRET, algorithm="HS256")


def decode_session_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.SESSION_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(settings.COOKIE_NAME, token, max_age=settings.SESSION_HOURS * 3600, httponly=True,
                        secure=settings.COOKIE_SECURE, samesite=settings.COOKIE_SAMESITE, path="/")


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(settings.COOKIE_NAME, path="/")


# ─── Dependencias ────────────────────────────────────────────────────────────

class Principal:
    """Quién hace la petición: un usuario con sesión o un servicio con API key."""
    def __init__(self, kind: str, user: dict | None = None):
        self.kind = kind            # 'user' | 'service'
        self.user = user or {}

    @property
    def id(self) -> str:
        return self.user.get("sub", "service") if self.kind == "user" else "service"

    @property
    def role(self) -> str:
        return "account_manager" if self.kind == "service" else normalize_role(self.user.get("role"))


async def current_principal(request: Request) -> Principal:
    api_key = request.headers.get("x-api-key")
    if settings.API_KEY and api_key == settings.API_KEY:
        return Principal("service")
    token = request.cookies.get(settings.COOKIE_NAME)
    if token:
        payload = decode_session_token(token)
        if payload:
            return Principal("user", payload)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")


def require_role(*roles: str):
    async def dep(p: Principal = Depends(current_principal)) -> Principal:
        if p.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin permiso para esta operación")
        return p
    return dep




# ─── Rate limit simple en memoria (por IP) ───────────────────────────────────

_hits: dict[str, deque] = defaultdict(deque)


def rate_limit(request: Request, limit: int | None = None, window: int = 60) -> None:
    limit = limit or settings.AUTH_RATE_LIMIT
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    q = _hits[ip]
    now = time.time()
    while q and q[0] < now - window:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(status_code=429, detail="Demasiadas peticiones, intenta en un minuto")
    q.append(now)
