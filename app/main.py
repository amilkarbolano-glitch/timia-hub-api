"""
Timia Hub — API (FastAPI + MongoDB)

Estructura:
  config.py     variables de entorno
  db.py         Motor/Mongo: cada key `timia_*` del front es una colección (arrays → un doc por ítem)
  security.py   sesión JWT en cookie httpOnly, API key de servicio, roles, rate limit
  routers/auth  Google Sign-In (OIDC) · /me · logout · demo
  routers/state /api/state (GET/PUT/DELETE por key), /api/keys, /api/seed
  routers/tr    /api/tr registro público de capturas de TR (sin sesión)
  routers/cortes /api/cortes foto diaria del plan de trabajo
  cortes.py     el hilo que la toma a las 18:00 (ver su docstring)

Docs interactivas: /docs
"""
from __future__ import annotations

import asyncio

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import cortes as svc_cortes
from . import db
from .config import settings
from .routers import auth, cortes, state, tr

app = FastAPI(title="Timia Hub API", version="2.0.0", docs_url="/docs", redoc_url=None)

if settings.CORS_ORIGINS:
    # Solo hace falta cuando el front NO está detrás del mismo nginx (cookies ⇒ credentials + orígenes explícitos)
    app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.include_router(auth.router)
app.include_router(state.router)
# Registro público de TR: el único sin sesión (valida el correo contra el equipo).
app.include_router(tr.router)
# Corte diario del plan: la foto de cada día para la línea de tiempo.
app.include_router(cortes.router)


@app.on_event("startup")
async def startup():
    db.connect()
    await db.db()[db.KV].create_index("updatedAt")
    if settings._ephemeral_secret:
        print("[auth] SESSION_SECRET no definido: las sesiones caducan al reiniciar la API. Defínelo en producción.")
    print(f"[auth] google={'sí' if settings.GOOGLE_CLIENT_ID else 'no'} · demo={'sí' if settings.ALLOW_DEMO_LOGIN else 'no'}")
    if settings.SEED_ON_START:
        res = await db.seed_from_file(force=False)
        if res["seeded"]:
            print(f"[seed] keys cargadas: {', '.join(res['seeded'])}")
    if settings.BOOTSTRAP_ON_START:
        # Fusiona los datos de bootstrap/: agrega lo que falte, nunca pisa lo editado.
        try:
            res = await db.merge_bootstrap()
            if res["added"]:
                print(f"[bootstrap] agregado: {res['added']}")
        except Exception as e:
            print(f"[bootstrap] error (se ignora): {e}")
    if settings.CORTE_DIARIO:
        global _tarea_cortes
        _tarea_cortes = asyncio.create_task(svc_cortes.bucle_diario(_parar_cortes))
        print(f"[cortes] corte diario activo a las {svc_cortes.HORA_CORTE}:00 (Bogotá)")


_parar_cortes = asyncio.Event()
_tarea_cortes: asyncio.Task | None = None


@app.on_event("shutdown")
async def shutdown():
    _parar_cortes.set()
    if _tarea_cortes:
        _tarea_cortes.cancel()
    db.close()


@app.get("/api/health", tags=["health"])
async def health():
    try:
        await db.ping()
        return {"ok": True, "db": settings.MONGO_DB, "keys": len(await db.list_keys()), "auth": {"google": bool(settings.GOOGLE_CLIENT_ID), "demo": settings.ALLOW_DEMO_LOGIN}, "time": db.now_iso()}
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=503, detail=f"mongo no disponible: {e}")
