"""Cortes del plan de trabajo: la foto de cada día. Requiere sesión."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from .. import cortes as svc
from ..security import Principal, current_principal, require_role

router = APIRouter(prefix="/api/cortes", tags=["cortes"])


@router.get("")
async def listar(p: Principal = Depends(current_principal)):
    """Qué días tienen foto, sin devolver los % — eso se lee por /api/state."""
    todos = await svc.db.read_key(svc.CORTES_KEY) or []
    if not isinstance(todos, list):
        todos = []
    return {
        "hoy": svc.hoy_bogota(),
        "cortes": [{"fecha": c.get("fecha"), "tomadoEn": c.get("tomadoEn"), "motivo": c.get("motivo"),
                    "planes": [x.get("planKey") for x in c.get("planes", [])]}
                   for c in todos if isinstance(c, dict)],
    }


@router.post("/tomar")
async def tomar(p: Principal = Depends(require_role("admin", "platform_admin", "account_manager", "pm", "tech_lead"))):
    """
    Guarda la foto de ahora mismo.

    El corte automático de las 18:00 lo hace la propia API; esto es para cuando
    se arma el seguimiento antes y se quiere dejar marcado ese momento.
    """
    quien = p.user.get("name") or p.user.get("email") or p.id
    return await svc.tomar_corte(motivo=f"manual · {quien}")
