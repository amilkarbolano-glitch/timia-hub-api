"""Datos de arranque: el merge agrega lo que falta y no toca nada existente.

Lo importante aquí es la garantía que pidió el equipo: el plan de MIGBD se editó a
mano y el bootstrap no puede sobrescribirlo. Estas pruebas verifican que
merge_key solo agrega.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import db

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ─── Doble de la base: guarda las keys en un dict ────────────────────────────
@pytest.fixture
def store(monkeypatch):
    datos: dict[str, object] = {}

    async def read_key(key):
        return datos.get(key)

    async def write_key(key, value, by=""):
        datos[key] = value

    monkeypatch.setattr(db, "read_key", read_key)
    monkeypatch.setattr(db, "write_key", write_key)
    return datos


async def test_lista_nueva_se_crea_completa(store):
    n = await db.merge_key("timia_inv_datax", [{"id": "a"}, {"id": "b"}])
    assert n == 2
    assert store["timia_inv_datax"] == [{"id": "a"}, {"id": "b"}]


async def test_lista_existente_solo_agrega_los_que_faltan(store):
    store["timia_inv_v2"] = [{"id": "a", "objeto": "editado a mano"}]
    n = await db.merge_key("timia_inv_v2", [{"id": "a", "objeto": "del excel"}, {"id": "b"}])
    assert n == 1
    # el ítem existente queda intacto, con el valor que tenía
    assert store["timia_inv_v2"][0] == {"id": "a", "objeto": "editado a mano"}
    assert store["timia_inv_v2"][1] == {"id": "b"}


async def test_correrlo_dos_veces_no_cambia_nada(store):
    items = [{"id": "a"}, {"id": "b"}]
    assert await db.merge_key("timia_inv_v2", items) == 2
    antes = json.dumps(store, sort_keys=True)
    assert await db.merge_key("timia_inv_v2", items) == 0
    assert json.dumps(store, sort_keys=True) == antes


async def test_objeto_solo_agrega_claves_nuevas(store):
    store["timia_plan_pcts"] = {"a": 50}
    n = await db.merge_key("timia_plan_pcts", {"a": 0, "b": 10})
    assert n == 1
    assert store["timia_plan_pcts"] == {"a": 50, "b": 10}


async def test_no_toca_una_key_de_tipo_distinto(store):
    store["timia_inv_v2"] = {"no": "es una lista"}
    assert await db.merge_key("timia_inv_v2", [{"id": "a"}]) == 0
    assert store["timia_inv_v2"] == {"no": "es una lista"}


async def test_bootstrap_ignora_keys_sin_prefijo_y_metadatos(store, tmp_path, monkeypatch):
    (tmp_path / "x.json").write_text(json.dumps({
        "_descripcion": "no es una key",
        "otra_cosa": [{"id": "z"}],
        "timia_inv_datax": [{"id": "a"}],
    }), encoding="utf-8")
    monkeypatch.setattr(db, "bootstrap_dir", lambda: tmp_path)
    res = await db.merge_bootstrap()
    assert res["added"] == {"timia_inv_datax": 1}
    assert set(store) == {"timia_inv_datax"}


async def test_sin_carpeta_no_falla(store, tmp_path, monkeypatch):
    monkeypatch.setattr(db, "bootstrap_dir", lambda: tmp_path / "no-existe")
    res = await db.merge_bootstrap()
    assert res["added"] == {}
    assert store == {}


# ─── El archivo real de MIGBD ────────────────────────────────────────────────
def test_el_archivo_de_migbd_es_coherente():
    path = Path(__file__).resolve().parent.parent / "bootstrap" / "migbd-inventario.json"
    data = json.loads(path.read_text(encoding="utf-8"))

    keys = [k for k in data if not k.startswith("_")]
    # Solo inventario: el plan de trabajo no se toca
    assert keys == ["timia_inv_stages", "timia_inv_v2", "timia_inv_datax",
                    "timia_inv_transmision", "timia_datax_config"]

    for k in keys:
        items = data[k]
        assert isinstance(items, list), k
        ids = [it["id"] for it in items]
        assert len(ids) == len(set(ids)), f"ids repetidos en {k}"
        assert all(ids), f"ids vacíos en {k}"

    # Todo apunta al proyecto piloto
    for k in ("timia_inv_v2", "timia_inv_datax", "timia_inv_transmision", "timia_datax_config"):
        assert {it["projectId"] for it in data[k]} == {"MIGBD"}, k

    # Las etapas nuevas son las que usan los responsables, y ninguna etapa trae avance
    nuevas = {s["id"] for s in data["timia_inv_stages"]}
    usados = {sid for o in data["timia_inv_v2"] for sid in o["responsables"]}
    assert nuevas <= usados
    assert all(o["stages"] == {} for o in data["timia_inv_v2"])

    # Los enlaces solo llevan URLs (en el Excel "Diccionario" era un responsable)
    for o in data["timia_inv_v2"]:
        for campo, url in o["enlaces"].items():
            assert url.startswith("http"), f"{o['objeto']}.{campo} no es una URL: {url!r}"
