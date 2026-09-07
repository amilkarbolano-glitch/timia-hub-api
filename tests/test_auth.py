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
    u = login(client, "u-sergio")
    assert u["role"] == "developer"
    me = client.get("/api/auth/me").json()
    assert me["user"]["id"] == "u-sergio" and "plan.view" in me["permissions"] and "team.manage" not in me["permissions"]
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_demo_unknown_user(client):
    assert client.post("/api/auth/demo", json={"userId": "nadie"}).status_code == 404


def test_google_not_configured(client):
    r = client.post("/api/auth/google", json={"credential": "x"})
    assert r.status_code == 400


def test_demo_accounts_public(client):
    accs = client.get("/api/auth/demo-accounts").json()
    assert any(a["id"] == "u-rodolfo" for a in accs)
    assert all("email" in a and "role" in a for a in accs)


def test_permissions_catalog(client):
    login(client, "u-rodolfo")
    p = client.get("/api/permissions").json()
    assert "matrix" in p and p["matrix"]["pm"] and "tasks.view" in p["matrix"]["developer"]
