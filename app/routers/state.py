"""Estado del front: una key `timia_*` por colección. Requiere sesión (o API key de servicio)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .. import db
from ..permissions import DEFAULT_ROLE_PERMISSIONS, PERMISSIONS, ROLE_LABELS, check_write, effective_matrix
from ..security import Principal, current_principal, require_role

router = APIRouter(prefix="/api", tags=["state"])


class PutBody(BaseModel):
    value: Any


def valid_key(key: str) -> str:
    if not db.is_valid_key(key):
        raise HTTPException(status_code=400, detail="key inválida (debe empezar por timia_)")
    return key


@router.get("/state")
async def get_state(p: Principal = Depends(current_principal)):
    return {k: await db.read_key(k) for k in await db.list_keys()}


@router.get("/state/{key}")
async def get_key(key: str, p: Principal = Depends(current_principal)):
    v = await db.read_key(valid_key(key))
    if v is None:
        raise HTTPException(status_code=404, detail="key no encontrada")
    return v


async def current_matrix() -> dict[str, list[str]]:
    return effective_matrix(await db.read_key("timia_role_permissions"))


@router.get("/permissions")
async def permissions(p: Principal = Depends(current_principal)):
    """Catálogo de permisos + matriz vigente por rol (para el front)."""
    return {"permissions": [{"id": k, "module": m, "label": l} for k, (m, l) in PERMISSIONS.items()],
            "roles": ROLE_LABELS, "defaults": DEFAULT_ROLE_PERMISSIONS, "matrix": await current_matrix()}


@router.put("/state/{key}")
@router.post("/state/{key}")          # alias para navigator.sendBeacon
async def put_key(key: str, body: PutBody, p: Principal = Depends(current_principal)):
    valid_key(key)
    if p.kind == "user":
        user = await db.find_user_by_id(p.id)
        if not user:
            raise HTTPException(status_code=401, detail="Sesión inválida")
        old = await db.read_key(key)
        reason = check_write(key, old, body.value, role=user.get("role", "developer"), user_id=p.id,
                             project_ids=list(user.get("projectIds", [])), matrix=await current_matrix())
        if reason:
            raise HTTPException(status_code=403, detail=reason)
    await db.write_key(key, body.value, by=p.id)
    return {"key": key, "updatedAt": db.now_iso()}


@router.delete("/state/{key}")
async def delete_key(key: str, p: Principal = Depends(require_role("pm"))):
    await db.delete_key(valid_key(key))
    return {"key": key, "deleted": True}


@router.get("/keys")
async def keys(p: Principal = Depends(current_principal)):
    return await db.list_meta()


@router.post("/seed")
async def seed(force: bool = Query(default=False), p: Principal = Depends(require_role("pm"))):
    return await db.seed_from_file(force)
