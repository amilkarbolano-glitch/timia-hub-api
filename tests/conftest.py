import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

import app.db as dbmod
import app.main as m
import app.security as sec


@pytest.fixture()
def client(monkeypatch):
    # Las pruebas corren sobre el respaldo del piloto (el seed de producción va vacío de datos)
    monkeypatch.setenv("SEED_FILE", str(pathlib.Path(__file__).resolve().parent.parent / "seed.piloto-migbd.json"))
    import importlib, app.config as cfg
    importlib.reload(cfg)
    monkeypatch.setattr(dbmod, "settings", cfg.settings)
    import app.routers.auth as auth_mod, app.routers.state as state_mod
    monkeypatch.setattr(auth_mod, "settings", cfg.settings)
    monkeypatch.setattr(dbmod, "AsyncIOMotorClient", lambda *a, **k: AsyncMongoMockClient())
    sec._hits.clear()                      # rate limit en memoria: reiniciar por prueba
    with TestClient(m.app) as c:
        yield c


def login(c: TestClient, user_id: str):
    r = c.post("/api/auth/demo", json={"userId": user_id})
    assert r.status_code == 200, r.text
    return r.json()["user"]
