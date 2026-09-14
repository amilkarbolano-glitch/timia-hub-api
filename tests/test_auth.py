from conftest import login


def test_health_and_config(client):
    h = client.get("/api/health").json()
    assert h["ok"] and h["keys"] > 15
    cfg = client.get("/api/auth/config").json()
    assert cfg["demo"] is True and cfg["google"] is False


def test_state_requires_session(client):
    assert client.get("/api/state").status_code == 401
    assert client.put("/api/state/timia_links", json={"value": []}).status_code == 401


def test_demo_login_me_logout(client):
    u = login(client, "u-santiago")
    assert u["role"] == "developer"
    me = client.get("/api/auth/me").json()
    assert me["user"]["id"] == "u-santiago" and "tasks.view" in me["permissions"] and "team.manage" not in me["permissions"]
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_demo_unknown_user(client):
    assert client.post("/api/auth/demo", json={"userId": "nadie"}).status_code == 404


def test_google_not_configured(client):
    r = client.post("/api/auth/google", json={"credential": "x"})
    assert r.status_code == 400


def test_demo_accounts_public(client):
    accs = client.get("/api/auth/demo-accounts").json()
    assert {a["id"] for a in accs} == {"u-amilkar", "u-rodolfo", "u-juan"}     # solo cuentas demo
    assert all("email" in a and "role" in a for a in accs)


def test_permissions_catalog(client):
    login(client, "u-rodolfo")
    p = client.get("/api/permissions").json()
    assert "matrix" in p and p["matrix"]["account_manager"] and "tasks.view" in p["matrix"]["developer"] and set(p["roles"]) == {"account_manager", "pm", "tech_lead", "developer"}


def test_firebase_not_configured(client):
    r = client.post("/api/auth/firebase", json={"idToken": "x"})
    assert r.status_code == 400
    assert client.get("/api/auth/config").json()["firebase"] is None


def test_firebase_configured_disables_demo_and_rejects_bad_token(monkeypatch):
    import importlib, app.config as cfg
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "timia-hub"); monkeypatch.setenv("FIREBASE_API_KEY", "AIza-x"); monkeypatch.setenv("FIREBASE_APP_ID", "1:1:web:x")
    importlib.reload(cfg)
    assert cfg.settings.ALLOW_DEMO_LOGIN is False
    import app.routers.auth as auth_mod
    monkeypatch.setattr(auth_mod, "settings", cfg.settings)
    import app.db as dbmod, app.main as m, app.security as sec
    from mongomock_motor import AsyncMongoMockClient
    from fastapi.testclient import TestClient
    monkeypatch.setattr(dbmod, "AsyncIOMotorClient", lambda *a, **k: AsyncMongoMockClient()); sec._hits.clear()
    with TestClient(m.app) as c:
        conf = c.get("/api/auth/config").json()
        assert conf["firebase"]["projectId"] == "timia-hub" and conf["firebase"]["authDomain"] == "timia-hub.firebaseapp.com"
        assert c.post("/api/auth/firebase", json={"idToken": "invalido"}).status_code == 401
    monkeypatch.delenv("FIREBASE_PROJECT_ID"); monkeypatch.delenv("FIREBASE_API_KEY"); monkeypatch.delenv("FIREBASE_APP_ID"); importlib.reload(cfg); monkeypatch.setattr(auth_mod, "settings", cfg.settings)
