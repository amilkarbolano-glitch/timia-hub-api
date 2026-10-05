"""Escritura de colecciones: nunca dejar la colección vacía a mitad de camino.

El bug: write_key hacía delete_many({}) y después insert_many. Entre las dos
operaciones timia_admin_users quedaba vacía, y find_user_by_id lee esa misma
colección en cada petición autenticada. Cualquier petición que cayera en esa
ventana respondía 401 "Sesión inválida" y el front deslogueaba al usuario.

Se reproducía al aprobar un acceso: eso escribe timia_admin_users y
timia_access_requests casi al mismo tiempo.
"""
from __future__ import annotations

import asyncio

import pytest

from app import db

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ─── Mongo de mentiras, con await real en cada operación ──────────────────────
class FakeCollection:
    """Cada operación hace `await asyncio.sleep(0)` para ceder el control, de modo
    que otra tarea pueda leer la colección justo en medio de una escritura."""

    def __init__(self, registro: list[str]):
        self.docs: dict[str, dict] = {}
        self.registro = registro

    async def delete_many(self, filtro):
        await asyncio.sleep(0)
        if filtro == {}:
            self.registro.append("wipe")
            self.docs.clear()
            return
        nin = filtro.get("_id", {}).get("$nin")
        if nin is not None:
            self.registro.append("delete_sobrantes")
            for k in [k for k in self.docs if k not in set(nin)]:
                del self.docs[k]

    async def bulk_write(self, ops, ordered=True):
        await asyncio.sleep(0)
        self.registro.append("upsert")
        for op in ops:
            self.docs[op._filter["_id"]] = op._doc

    async def replace_one(self, filtro, doc, upsert=False):
        await asyncio.sleep(0)
        self.docs[filtro["_id"]] = doc

    async def insert_many(self, docs):
        await asyncio.sleep(0)
        self.registro.append("insert")
        for d in docs:
            self.docs[d["_id"]] = d

    async def drop(self):
        await asyncio.sleep(0)
        self.docs.clear()

    async def find_one(self, filtro, proj=None):
        await asyncio.sleep(0)
        return self.docs.get(filtro["_id"])

    async def create_index(self, *a, **k):
        await asyncio.sleep(0)


class FakeDB:
    def __init__(self):
        self.registro: list[str] = []
        self.cols: dict[str, FakeCollection] = {}

    def __getitem__(self, name):
        return self.cols.setdefault(name, FakeCollection(self.registro))


@pytest.fixture
def fake(monkeypatch):
    f = FakeDB()
    monkeypatch.setattr(db, "db", lambda: f)
    return f


USERS = db.USERS_KEY


async def test_no_borra_todo_antes_de_escribir(fake):
    await db.write_key(USERS, [{"id": "u-amilkar", "active": True}])
    assert "wipe" not in fake.registro, "no debe vaciar la colección con datos por escribir"
    assert fake.registro == ["upsert", "delete_sobrantes"], fake.registro


async def test_el_resultado_es_exactamente_la_lista(fake):
    await db.write_key(USERS, [{"id": "a"}, {"id": "b"}])
    await db.write_key(USERS, [{"id": "b"}, {"id": "c"}])
    assert set(fake[USERS].docs) == {"b", "c"}, "lo que ya no está en la lista se borra"


async def test_conserva_el_orden(fake):
    await db.write_key(USERS, [{"id": "c"}, {"id": "a"}, {"id": "b"}])
    ords = {k: v["_ord"] for k, v in fake[USERS].docs.items()}
    assert ords == {"c": 0, "a": 1, "b": 2}


async def test_lista_vacia_si_vacia_la_coleccion(fake):
    await db.write_key(USERS, [{"id": "a"}])
    await db.write_key(USERS, [])
    assert fake[USERS].docs == {}
    assert "wipe" in fake.registro, "una lista vacía sí debe vaciar (es la intención)"


async def test_la_sesion_sobrevive_a_una_escritura_concurrente(fake):
    """El caso real: mientras se reescribe la lista de usuarios, otra petición
    busca al usuario de la sesión. Antes devolvía None → 401 → deslogueo."""
    usuarios = [{"id": "u-amilkar", "active": True}, {"id": "u-santiago", "active": True}]
    await db.write_key(USERS, usuarios)

    encontrado: list[bool] = []

    async def mirando():
        # lee sin parar mientras la escritura ocurre
        for _ in range(40):
            encontrado.append(await db.find_user_by_id("u-amilkar") is not None)
            await asyncio.sleep(0)

    nuevos = usuarios + [{"id": "u-nuevo", "active": True}]
    await asyncio.gather(db.write_key(USERS, nuevos), mirando())

    assert all(encontrado), (
        f"la sesión se perdió en {encontrado.count(False)} de {len(encontrado)} lecturas "
        "durante la escritura")
    assert set(fake[USERS].docs) == {"u-amilkar", "u-santiago", "u-nuevo"}


async def test_aprobar_un_acceso_no_rompe_la_sesion(fake):
    """Reproducción del flujo de aprobación: dos escrituras casi simultáneas,
    y entre ellas una comprobación de sesión como la que hace put_key."""
    await db.write_key(USERS, [{"id": "u-amilkar", "active": True}])
    await db.write_key("timia_access_requests", [{"id": "r1", "status": "pending"}])

    sesion_ok: list[bool] = []

    async def escribir_solicitudes():
        # lo que hace put_key: primero valida la sesión, después escribe
        sesion_ok.append(await db.find_user_by_id("u-amilkar") is not None)
        await db.write_key("timia_access_requests", [{"id": "r1", "status": "approved"}])

    await asyncio.gather(
        db.write_key(USERS, [{"id": "u-amilkar", "active": True}, {"id": "u-santiago", "active": True}]),
        escribir_solicitudes(),
    )

    assert sesion_ok == [True], "la validación de sesión no debe fallar por la otra escritura"
    assert fake["timia_access_requests"].docs["r1"]["item"]["status"] == "approved", \
        "la aprobación queda guardada"


async def test_un_usuario_inactivo_si_invalida_la_sesion(fake):
    """El 401 legítimo tiene que seguir ocurriendo."""
    await db.write_key(USERS, [{"id": "u-x", "active": False}])
    assert await db.find_user_by_id("u-x") is None
