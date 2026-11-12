"""
El corte diario del plan: la foto de cada día.

Lo que más importa aquí es que no mienta —ni duplicando días ni perdiendo %— y
que reiniciar la API tres veces en una tarde no deje tres cortes compitiendo.
"""
from datetime import datetime, timedelta

import pytest

from app import cortes as svc
from app import db
from conftest import login


# ─── A qué hora toca ─────────────────────────────────────────────────────────

def test_el_corte_es_a_las_seis_de_la_tarde():
    manana = datetime(2026, 11, 11, 9, 0, tzinfo=svc.BOGOTA)
    assert svc.proximo_corte(manana) == datetime(2026, 11, 11, 18, 0, tzinfo=svc.BOGOTA)


def test_pasadas_las_seis_toca_mañana():
    tarde = datetime(2026, 11, 11, 19, 30, tzinfo=svc.BOGOTA)
    assert svc.proximo_corte(tarde).date() == datetime(2026, 11, 12).date()


def test_justo_a_las_seis_el_de_hoy_ya_pasó():
    # A las 18:00 clavadas el corte de hoy se toma en ese mismo instante; el
    # siguiente es el de mañana, no un bucle de esperas de cero segundos.
    assert svc.proximo_corte(datetime(2026, 11, 11, 18, 0, tzinfo=svc.BOGOTA)).day == 12


def test_la_espera_nunca_es_negativa():
    for hora in range(24):
        ahora = datetime(2026, 11, 11, hora, 17, tzinfo=svc.BOGOTA)
        assert (svc.proximo_corte(ahora) - ahora).total_seconds() > 0


# ─── Qué guarda ──────────────────────────────────────────────────────────────

def test_reparte_los_pcts_por_cronograma(client):
    assert svc.pcts_de_plan({"MIGBD-doc-0": 80, "FICO-doc-0": 10}, "MIGBD") == {"MIGBD-doc-0": 80}


def test_un_plankey_con_guiones_no_se_parte(client):
    # 'SDATOOL-54364::crono-2' lleva guiones: separar la clave a la brava daría
    # un cronograma inventado. Por eso los planKey salen de las configuraciones.
    pcts = {"SDATOOL-54364::crono-2-doc-0": 50, "MIGBD-doc-0": 80}
    configs = {"SDATOOL-54364::crono-2": {}, "MIGBD": {}}
    claves = svc.planes_de(pcts, configs)
    assert svc.pcts_de_plan(pcts, "SDATOOL-54364::crono-2") == {"SDATOOL-54364::crono-2-doc-0": 50}
    assert claves == ["MIGBD", "SDATOOL-54364::crono-2"]


@pytest.mark.anyio
async def test_el_corte_guarda_los_pcts_de_cada_plan(client):
    await db.write_key(svc.PCTS_KEY, {"MIGBD-doc-0": 80, "MIGBD-doc-1": 70})
    await db.write_key(svc.CONFIGS_KEY, {"MIGBD": {"totalWeeks": 14}})
    res = await svc.tomar_corte(fecha="2026-11-11")
    assert res["tomado"] and res["planes"] == 1
    guardado = await db.read_key(svc.CORTES_KEY)
    assert guardado[0]["planes"][0]["pcts"] == {"MIGBD-doc-0": 80, "MIGBD-doc-1": 70}


@pytest.mark.anyio
async def test_los_pcts_huerfanos_no_se_pierden(client):
    """Si un % no cae bajo ningún cronograma declarado, se guarda aparte."""
    await db.write_key(svc.PCTS_KEY, {"MIGBD-doc-0": 80, "FANTASMA-doc-0": 5})
    await db.write_key(svc.CONFIGS_KEY, {"MIGBD": {}})
    await svc.tomar_corte(fecha="2026-11-11")
    corte = (await db.read_key(svc.CORTES_KEY))[0]
    assert corte["sueltos"] == {"FANTASMA-doc-0": 5}


@pytest.mark.anyio
async def test_no_se_duplica_el_corte_del_mismo_dia(client):
    await db.write_key(svc.PCTS_KEY, {"MIGBD-doc-0": 80})
    await db.write_key(svc.CONFIGS_KEY, {"MIGBD": {}})
    assert (await svc.tomar_corte(fecha="2026-11-11"))["tomado"] is True
    segundo = await svc.tomar_corte(fecha="2026-11-11")
    assert segundo["tomado"] is False and "ya existe" in segundo["razon"]
    assert len(await db.read_key(svc.CORTES_KEY)) == 1


@pytest.mark.anyio
async def test_un_corte_viejo_no_se_pisa_con_los_pcts_de_hoy(client):
    """La foto de ayer tiene que seguir siendo la de ayer."""
    await db.write_key(svc.CONFIGS_KEY, {"MIGBD": {}})
    await db.write_key(svc.PCTS_KEY, {"MIGBD-doc-0": 30})
    await svc.tomar_corte(fecha="2026-11-10")
    await db.write_key(svc.PCTS_KEY, {"MIGBD-doc-0": 80})
    await svc.tomar_corte(fecha="2026-11-11")
    cortes = {c["fecha"]: c for c in await db.read_key(svc.CORTES_KEY)}
    assert cortes["2026-11-10"]["planes"][0]["pcts"]["MIGBD-doc-0"] == 30
    assert cortes["2026-11-11"]["planes"][0]["pcts"]["MIGBD-doc-0"] == 80


@pytest.mark.anyio
async def test_sin_pcts_el_corte_se_toma_igual(client):
    """Un día sin movimientos también es un punto de la línea de tiempo."""
    await db.write_key(svc.CONFIGS_KEY, {"MIGBD": {}})
    await db.write_key(svc.PCTS_KEY, {})
    res = await svc.tomar_corte(fecha="2026-11-11")
    assert res["tomado"] is True
    assert (await db.read_key(svc.CORTES_KEY))[0]["planes"][0]["pcts"] == {}


# ─── Los endpoints ───────────────────────────────────────────────────────────

def test_listar_exige_sesion(client):
    assert client.get("/api/cortes").status_code == 401


def test_listar_no_devuelve_los_pcts(client):
    """Solo el índice de días: los valores se leen por /api/state."""
    login(client, "u-rodolfo")
    r = client.get("/api/cortes")
    assert r.status_code == 200
    assert set(r.json().keys()) == {"hoy", "cortes"}
    for c in r.json()["cortes"]:
        assert set(c.keys()) == {"fecha", "tomadoEn", "motivo", "planes"}


def test_tomar_corte_a_mano(client):
    login(client, "u-rodolfo")
    r = client.post("/api/cortes/tomar")
    assert r.status_code == 200 and r.json()["tomado"] is True
    assert client.post("/api/cortes/tomar").json()["tomado"] is False   # idempotente


def test_el_corte_manual_deja_quién_lo_tomó(client):
    u = login(client, "u-rodolfo")
    client.post("/api/cortes/tomar")
    motivo = client.get("/api/cortes").json()["cortes"][0]["motivo"]
    assert motivo.startswith("manual") and u["name"].split()[0] in motivo


def test_un_desarrollador_no_toma_cortes(client):
    """Mirar la línea de tiempo sí; fijar el punto del día, no."""
    login(client, "u-santiago")
    assert client.get("/api/cortes").status_code == 200
    assert client.post("/api/cortes/tomar").status_code == 403


@pytest.fixture
def anyio_backend():
    return "asyncio"
