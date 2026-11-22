"""Imágenes de las notas: tipo, tamaño, deduplicado por SHA y caché."""
from __future__ import annotations

import hashlib

from conftest import login

PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 64
WEBP = b"RIFF" + b"y" * 64


def test_sube_y_lee(client):
    login(client, "u-amilkar")
    r = client.post("/api/notas/imagenes", content=PNG, headers={"Content-Type": "image/png"})
    assert r.status_code == 200
    sha = hashlib.sha256(PNG).hexdigest()
    assert r.json()["id"] == sha and r.json()["nueva"] is True

    g = client.get(f"/api/notas/imagenes/{sha}")
    assert g.status_code == 200
    assert g.content == PNG
    assert g.headers["etag"] == f'"{sha}"'
    assert "immutable" in g.headers["cache-control"]


def test_deduplica_por_contenido(client):
    login(client, "u-amilkar")
    client.post("/api/notas/imagenes", content=WEBP, headers={"Content-Type": "image/webp"})
    r2 = client.post("/api/notas/imagenes", content=WEBP, headers={"Content-Type": "image/webp"})
    assert r2.status_code == 200 and r2.json()["nueva"] is False


def test_etag_evita_releer(client):
    login(client, "u-amilkar")
    sha = client.post("/api/notas/imagenes", content=PNG, headers={"Content-Type": "image/png"}).json()["id"]
    r = client.get(f"/api/notas/imagenes/{sha}", headers={"If-None-Match": f'"{sha}"'})
    assert r.status_code == 304 and not r.content


def test_rechaza_tipo_no_imagen(client):
    login(client, "u-amilkar")
    r = client.post("/api/notas/imagenes", content=b"<html>hola</html>", headers={"Content-Type": "text/html"})
    assert r.status_code == 415


def test_rechaza_contenido_que_no_coincide(client):
    """Un ejecutable diciendo que es png: el content-type lo pone el cliente."""
    login(client, "u-amilkar")
    r = client.post("/api/notas/imagenes", content=b"MZ\x90\x00" + b"z" * 32, headers={"Content-Type": "image/png"})
    assert r.status_code == 415


def test_rechaza_demasiado_grande(client):
    login(client, "u-amilkar")
    grande = b"\x89PNG\r\n\x1a\n" + b"g" * (9 * 1024 * 1024)
    r = client.post("/api/notas/imagenes", content=grande, headers={"Content-Type": "image/png"})
    assert r.status_code == 413


def test_id_invalido(client):
    login(client, "u-amilkar")
    assert client.get("/api/notas/imagenes/../../etc/passwd").status_code in (400, 404)
    assert client.get("/api/notas/imagenes/nohexnohex").status_code == 400


def test_sin_sesion_no_entra(client):
    r = client.post("/api/notas/imagenes", content=PNG, headers={"Content-Type": "image/png"})
    assert r.status_code == 401
    assert client.get(f"/api/notas/imagenes/{hashlib.sha256(PNG).hexdigest()}").status_code == 401
