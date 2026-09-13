"""Autenticación: Google Sign-In (OIDC), sesión y modo demo."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from .. import db
from ..config import settings
from ..permissions import effective_matrix, normalize_role
from ..security import (Principal, clear_session_cookie, create_session_token, current_principal, public_user,
                        rate_limit, set_session_cookie)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class GoogleBody(BaseModel):
    credential: str            # ID token que entrega el botón de Google


class DemoBody(BaseModel):
    userId: str


@router.get("/config")
async def auth_config():
    """Público: le dice al front qué métodos de login están disponibles."""
    return {"google": bool(settings.GOOGLE_CLIENT_ID), "googleClientId": settings.GOOGLE_CLIENT_ID or None,
            "demo": settings.ALLOW_DEMO_LOGIN, "allowedDomains": settings.ALLOWED_EMAIL_DOMAINS}


@router.post("/google")
async def login_google(body: GoogleBody, request: Request, response: Response):
    rate_limit(request)
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=400, detail="Google Sign-In no está configurado (GOOGLE_CLIENT_ID)")
    try:
        from google.auth.transport import requests as g_requests
        from google.oauth2 import id_token
        info = id_token.verify_oauth2_token(body.credential, g_requests.Request(), settings.GOOGLE_CLIENT_ID, clock_skew_in_seconds=10)
    except Exception:
        raise HTTPException(status_code=401, detail="Token de Google inválido o expirado")
    email = str(info.get("email", "")).lower()
    if not info.get("email_verified", False) or not email:
        raise HTTPException(status_code=401, detail="Correo de Google no verificado")
    if settings.ALLOWED_EMAIL_DOMAINS and email.split("@")[-1] not in settings.ALLOWED_EMAIL_DOMAINS:
        raise HTTPException(status_code=403, detail=f"Solo se permiten cuentas de {', '.join(settings.ALLOWED_EMAIL_DOMAINS)}")
    user = await db.find_user_by_email(email)
    if not user:
        raise HTTPException(status_code=403, detail=f"{email} no está registrado en Timia Hub. Pide al PM que te agregue en Administración › Equipo.")
    set_session_cookie(response, create_session_token(user, "google"))
    return {"user": public_user(user), "provider": "google"}


@router.get("/demo-accounts")
async def demo_accounts():
    """Cuentas disponibles para el login demo (solo si está activo). No expone nada sensible."""
    if not settings.ALLOW_DEMO_LOGIN:
        raise HTTPException(status_code=403, detail="El acceso demo está desactivado")
    out = []
    async for doc in db.db()[db.USERS_KEY].find({}, {"item": 1}).sort("_ord", 1):
        u = doc["item"]
        if u.get("active", True):
            out.append(public_user(u))
    return out


@router.post("/demo")
async def login_demo(body: DemoBody, request: Request, response: Response):
    """Login sin contraseña con una cuenta del panel. Solo si ALLOW_DEMO_LOGIN (por defecto: cuando no hay Google)."""
    rate_limit(request)
    if not settings.ALLOW_DEMO_LOGIN:
        raise HTTPException(status_code=403, detail="El acceso demo está desactivado; usa Google")
    user = await db.find_user_by_id(body.userId)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado o inactivo")
    set_session_cookie(response, create_session_token(user, "demo"))
    return {"user": public_user(user), "provider": "demo"}


@router.get("/me")
async def me(p: Principal = Depends(current_principal)):
    if p.kind == "service":
        return {"user": None, "service": True}
    user = await db.find_user_by_id(p.id)
    if not user:
        raise HTTPException(status_code=401, detail="Sesión inválida (usuario eliminado o inactivo)")
    matrix = effective_matrix(await db.read_key("timia_role_permissions"))
    return {"user": public_user(user), "provider": p.user.get("prv"), "exp": p.user.get("exp"),
            "permissions": matrix.get(normalize_role(user.get("role")), [])}


@router.post("/logout")
async def logout(response: Response):
    clear_session_cookie(response)
    return {"ok": True}
