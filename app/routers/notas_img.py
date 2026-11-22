"""
Imágenes de las notas.

Por qué un endpoint propio y no una key `timia_*` como todo lo demás: el front
descarga TODO el estado al iniciar sesión (`GET /api/state`, con 8 s de límite)
y lo copia a `localStorage`, que tiene unos 5 MB por origen. Una imagen metida
en cualquier key del estado se descargaría en cada arranque y reventaría el
cupo, y el `catch` que envuelve ese `setItem` se come el error: fallaría en
silencio y la aplicación entera dejaría de persistir. Así que las imágenes
viven en su propia colección, fuera del estado.

Direccionadas por contenido: el id es el SHA-256 de los bytes. Eso da tres
cosas gratis. La misma captura pegada en dos notas se guarda una vez. La URL
nunca cambia de contenido, así que se puede cachear para siempre. Y no hace
falta inventar ids ni limpiar huérfanos con prisa: una imagen que ya nadie
referencia no estorba más que su propio peso.

El navegador manda la imagen ya reducida (WebP, lado mayor 2000 px): aquí solo
se valida y se guarda, para no meter Pillow ni trabajo de CPU en el contenedor.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from bson import Binary
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from .. import db
from ..security import Principal, current_principal

router = APIRouter(prefix="/api/notas", tags=["notas"])

COLL = "notas_imagenes"

# Tras la reducción del navegador una captura típica pesa 200–400 KB. 8 MB deja
# margen de sobra para una foto grande y sigue lejos del límite de 16 MB por
# documento de Mongo/DocumentDB.
MAX_BYTES = 8 * 1024 * 1024

TIPOS = {
    "image/webp": b"RIFF",
    "image/jpeg": b"\xff\xd8\xff",
    "image/png":  b"\x89PNG\r\n\x1a\n",
    "image/gif":  b"GIF8",
}

SHA_RE = re.compile(r"^[0-9a-f]{64}$")


def _tipo_valido(mime: str, data: bytes) -> bool:
    """El content-type lo pone el cliente, así que se comprueba contra los
    primeros bytes del archivo: sin esto, cualquiera guardaría lo que quisiera
    diciendo que es un png."""
    firma = TIPOS.get(mime)
    return bool(firma) and data.startswith(firma)


@router.post("/imagenes")
async def subir_imagen(request: Request, p: Principal = Depends(current_principal)) -> dict[str, Any]:
    mime = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if mime not in TIPOS:
        raise HTTPException(status_code=415, detail=f"tipo no admitido: {mime or 'sin content-type'}")

    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="cuerpo vacío")
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"la imagen pesa {len(data) // 1024} KB y el máximo es {MAX_BYTES // 1024} KB")
    if not _tipo_valido(mime, data):
        raise HTTPException(status_code=415, detail="el contenido no corresponde al tipo declarado")

    sha = hashlib.sha256(data).hexdigest()
    d = db.db()
    ya = await d[COLL].find_one({"_id": sha}, {"_id": 1})
    if not ya:
        await d[COLL].insert_one({
            "_id": sha, "mime": mime, "bytes": Binary(data), "len": len(data),
            "by": p.id, "at": db.now_iso(),
        })
    return {"id": sha, "url": f"/api/notas/imagenes/{sha}", "mime": mime, "len": len(data), "nueva": not ya}


@router.get("/imagenes/{sha}")
async def leer_imagen(sha: str, request: Request, p: Principal = Depends(current_principal)) -> Response:
    if not SHA_RE.match(sha):
        raise HTTPException(status_code=400, detail="id inválido")

    # Si el navegador ya la tiene, no se vuelve a leer de Mongo: el contenido de
    # una URL direccionada por contenido no puede cambiar.
    if request.headers.get("if-none-match") == f'"{sha}"':
        return Response(status_code=304, headers={"ETag": f'"{sha}"', "Cache-Control": "private, max-age=31536000, immutable"})

    doc = await db.db()[COLL].find_one({"_id": sha})
    if not doc:
        raise HTTPException(status_code=404, detail="imagen no encontrada")
    return Response(
        content=bytes(doc["bytes"]),
        media_type=doc.get("mime", "application/octet-stream"),
        headers={"ETag": f'"{sha}"', "Cache-Control": "private, max-age=31536000, immutable"},
    )


@router.get("/imagenes")
async def listar_imagenes(p: Principal = Depends(current_principal)) -> dict[str, Any]:
    """Inventario sin bytes: para saber cuánto ocupan y quién las subió."""
    docs = await db.db()[COLL].find({}, {"bytes": 0}).to_list(length=None)
    return {"n": len(docs), "bytes": sum(int(x.get("len", 0)) for x in docs),
            "imagenes": [{"id": x["_id"], "mime": x.get("mime"), "len": x.get("len"), "by": x.get("by"), "at": x.get("at")} for x in docs]}
