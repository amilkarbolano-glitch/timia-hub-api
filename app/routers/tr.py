"""
Registro de TR desde la vista pública.

Es el único endpoint sin sesión de toda la API, y lo es a propósito: la gente
sube sus capturas desde el celular, y pedirles iniciar sesión con Google para
eso haría que no lo hagan. A cambio, el correo se valida contra el equipo: si
no está en `timia_admin_users` y activo, no entra nada.

El Apps Script que lee las capturas lo mantiene otra persona. Su URL vive aquí
(variable de entorno), no en el navegador: así no queda en el bundle, no hay
problema de CORS, y el día que cambie se toca un sitio solo.
"""
from __future__ import annotations

import base64
import binascii
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .. import db
from ..config import settings
from ..security import rate_limit

router = APIRouter(prefix="/api/tr", tags=["tr"])

REGISTROS_KEY = "timia_tr_registros"

# Una captura de pantalla de un TR no pesa más que esto ni de lejos. El límite
# existe para que nadie use el endpoint abierto como depósito de archivos.
MAX_BYTES_IMAGEN = 6 * 1024 * 1024
MAX_IMAGENES = 10


class Captura(BaseModel):
    nombre: str = Field(max_length=200)
    # data URL del navegador: "data:image/png;base64,AAAA…"
    contenido: str


class RegistroBody(BaseModel):
    correo: str = Field(max_length=160)
    fecha: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    capturas: list[Captura]


def _bytes_de(data_url: str) -> bytes:
    """Los bytes de una data URL, o error si no lo es."""
    if "," not in data_url:
        raise HTTPException(status_code=400, detail="captura con formato inesperado")
    cabecera, b64 = data_url.split(",", 1)
    if not cabecera.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="solo se aceptan imágenes")
    try:
        return base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="captura ilegible")


async def _llamar_apps_script(correo: str, fecha: str, captura: Captura) -> dict[str, Any]:
    """
    Manda una captura al Apps Script y devuelve lo que responda.

    No se interpreta la respuesta: se guarda tal cual. Todavía no tenemos su
    contrato, así que inventarle una forma ahora sería adivinar; cuando llegue,
    se normaliza en un solo sitio.
    """
    if not settings.TR_SCRIPT_URL:
        return {"estado": "SIN_CONFIGURAR",
                "detalle": "Falta TR_SCRIPT_URL: la captura se guardó pero no se ha leído todavía."}
    try:
        async with httpx.AsyncClient(timeout=settings.TR_SCRIPT_TIMEOUT) as cli:
            r = await cli.post(settings.TR_SCRIPT_URL, json={
                "correo": correo, "fecha": fecha,
                "nombre": captura.nombre, "imagen": captura.contenido,
            })
        if r.status_code >= 400:
            return {"estado": "ERROR_SCRIPT", "detalle": f"HTTP {r.status_code}", "cuerpo": r.text[:500]}
        try:
            return {"estado": "OK", "respuesta": r.json()}
        except ValueError:
            return {"estado": "OK", "respuesta": r.text[:2000]}
    except httpx.TimeoutException:
        # Se distingue del error para que la vista pueda decir «tardó demasiado,
        # vuelve a intentarlo» en vez de «falló», que no es lo mismo.
        return {"estado": "TIMEOUT",
                "detalle": f"El lector no respondió en {settings.TR_SCRIPT_TIMEOUT}s."}
    except httpx.HTTPError as e:
        return {"estado": "ERROR_RED", "detalle": str(e)[:300]}


@router.get("/persona")
async def persona(correo: str, request: Request):
    """
    ¿Este correo pertenece al equipo? La vista pública lo usa para confirmar
    quién eres antes de dejarte subir nada, y para que un dedazo no mande las
    horas al limbo.

    Devuelve solo el nombre: nada de rol, proyectos ni identificadores. Es un
    endpoint abierto y no tiene por qué servir para averiguar quién trabaja
    aquí más allá de confirmar un correo que ya se conoce.
    """
    rate_limit(request, limit=30, window=60)
    u = await db.find_user_by_email((correo or "").strip().lower())
    if not u:
        raise HTTPException(status_code=404, detail="Ese correo no está en el equipo.")
    return {"nombre": u.get("name") or u.get("email")}


@router.post("/registro")
async def registrar(body: RegistroBody, request: Request):
    """Recibe las capturas, las manda a leer y guarda el resultado."""
    rate_limit(request, limit=12, window=300)

    correo = body.correo.strip().lower()
    usuario = await db.find_user_by_email(correo)
    if not usuario:
        raise HTTPException(status_code=403, detail="Ese correo no está en el equipo.")

    if not body.capturas:
        raise HTTPException(status_code=400, detail="No llegó ninguna captura.")
    if len(body.capturas) > MAX_IMAGENES:
        raise HTTPException(status_code=400, detail=f"Máximo {MAX_IMAGENES} capturas por envío.")
    for c in body.capturas:
        if len(_bytes_de(c.contenido)) > MAX_BYTES_IMAGEN:
            raise HTTPException(status_code=413, detail=f"«{c.nombre}» pesa más de 6 MB.")

    ahora = datetime.now(timezone.utc).isoformat()
    resultados = []
    for c in body.capturas:
        lectura = await _llamar_apps_script(correo, body.fecha, c)
        resultados.append({"captura": c.nombre, **lectura})

    registro = {
        "id": f"tr-{int(datetime.now(timezone.utc).timestamp() * 1000)}-{len(resultados)}",
        "correo": correo,
        "persona": usuario.get("name") or correo,
        "userId": usuario.get("id"),
        "fecha": body.fecha,
        "enviadoEn": ahora,
        "capturas": [c.nombre for c in body.capturas],
        "resultados": resultados,
    }
    # Las imágenes no se guardan: pesan, y el Apps Script ya deja su copia en
    # Drive. Aquí queda la lectura, que es lo que se consulta.
    previos = await db.read_key(REGISTROS_KEY) or []
    if not isinstance(previos, list):
        previos = []
    await db.write_key(REGISTROS_KEY, [*previos, registro], by=correo)

    return {"ok": True, "persona": registro["persona"], "resultados": resultados}
