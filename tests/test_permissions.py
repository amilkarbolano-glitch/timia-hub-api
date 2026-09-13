"""Permisos sobre el dataset del piloto: MIGBD con Rodolfo (gerente), Juan (PM), Amilkar/Juliana (líderes), Santiago (dev)."""
from conftest import login


def get(c, key):
    r = c.get(f"/api/state/{key}")
    return r.json() if r.status_code == 200 else None


def put(c, key, value):
    return c.put(f"/api/state/{key}", json={"value": value})


TASK = {"id": "kt-1", "title": "Tarea piloto", "description": "", "priority": "Media", "startDate": "2026-09-13", "endDate": "2026-09-20",
        "status": "backlog", "assigneeIds": ["u-santiago"], "projectId": "MIGBD", "links": [], "comments": []}


# ─── globales ────────────────────────────────────────────────────────────────

def test_developer_cannot_edit_admin_users(client):
    login(client, "u-santiago")
    users = get(client, "timia_admin_users"); users[0]["name"] = "hack"
    r = put(client, "timia_admin_users", users)
    assert r.status_code == 403 and "team.manage" in r.json()["detail"]


def test_pm_and_account_manager_can_edit_admin_users(client):
    for uid in ("u-juan", "u-rodolfo"):
        client.post("/api/auth/logout"); login(client, uid)
        users = get(client, "timia_admin_users"); users[0]["areaLabel"] = f"cambio {uid}"
        assert put(client, "timia_admin_users", users).status_code == 200


def test_noop_write_is_allowed(client):
    login(client, "u-santiago")
    assert put(client, "timia_admin_users", get(client, "timia_admin_users")).status_code == 200


# ─── alcance por proyecto ─────────────────────────────────────────────────────

def test_developer_issue_in_own_project(client):
    login(client, "u-santiago")
    issues = get(client, "timia_plan_issues") or []
    issues.append({"id": "is-t1", "planKey": "MIGBD", "type": "bloqueante", "title": "t", "startDate": "2026-09-13", "createdBy": "x", "createdAt": "x"})
    assert put(client, "timia_plan_issues", issues).status_code == 200


def test_developer_issue_in_other_project_denied(client):
    login(client, "u-santiago")
    issues = get(client, "timia_plan_issues") or []
    issues.append({"id": "is-t2", "planKey": "OTRO", "type": "alerta", "title": "t", "startDate": "2026-09-13", "createdBy": "x", "createdAt": "x"})
    r = put(client, "timia_plan_issues", issues)
    assert r.status_code == 403 and "OTRO" in r.json()["detail"]


def test_progress_scoped(client):
    pcts = {}
    login(client, "u-santiago")
    assert put(client, "timia_plan_pcts", {"MIGBD-documentacion-y-0": 50}).status_code == 403   # dev sin plan.edit_progress
    client.post("/api/auth/logout"); login(client, "u-amilkar")                                    # líder técnico en MIGBD
    assert put(client, "timia_plan_pcts", {"MIGBD-documentacion-y-0": 50}).status_code == 200
    assert put(client, "timia_plan_pcts", {"MIGBD-documentacion-y-0": 50, "OTRO-doc-0": 10}).status_code == 403
    client.post("/api/auth/logout"); login(client, "u-juan")                                       # PM: solo sus proyectos
    assert put(client, "timia_plan_pcts", {"MIGBD-documentacion-y-0": 60, "OTRO-doc-0": 10}).status_code == 403
    client.post("/api/auth/logout"); login(client, "u-rodolfo")                                    # gerente: todos
    assert put(client, "timia_plan_pcts", {"MIGBD-documentacion-y-0": 60, "OTRO-doc-0": 10}).status_code == 200


# ─── kanban: cambios parciales ───────────────────────────────────────────────

def test_developer_can_move_task_but_not_create_or_edit(client):
    login(client, "u-juan"); assert put(client, "timia_kanban_tasks", [TASK]).status_code == 200
    client.post("/api/auth/logout"); login(client, "u-santiago")
    assert put(client, "timia_kanban_tasks", [{**TASK, "status": "in-progress"}]).status_code == 200
    r = put(client, "timia_kanban_tasks", [{**TASK, "status": "in-progress", "title": "otro"}])
    assert r.status_code == 403 and "status" in r.json()["detail"]
    assert put(client, "timia_kanban_tasks", [{**TASK, "status": "in-progress"}, {**TASK, "id": "kt-2"}]).status_code == 403


def test_tech_lead_can_create_task(client):
    login(client, "u-amilkar")
    assert put(client, "timia_kanban_tasks", [TASK]).status_code == 200


# ─── TR: propio vs cualquiera ────────────────────────────────────────────────

def test_developer_loads_only_own_tr(client):
    login(client, "u-santiago")
    e = {"id": "tr-x1", "userId": "u-santiago", "userName": "S", "date": "2026-09-13", "featureId": "DECIBCUMPL-727", "phase": "Pruebas", "hours": 8, "source": "manual", "createdAt": "x"}
    assert put(client, "timia_tr_entries", [e]).status_code == 200
    r = put(client, "timia_tr_entries", [e, {**e, "id": "tr-x2", "userId": "u-amilkar"}])
    assert r.status_code == 403 and "propios" in r.json()["detail"]


def test_tech_lead_loads_any_tr(client):
    login(client, "u-amilkar")
    e = {"id": "tr-x3", "userId": "u-santiago", "userName": "S", "date": "2026-09-13", "featureId": "DECIBCUMPL-727", "phase": "Pruebas", "hours": 8, "source": "manual", "createdAt": "x"}
    assert put(client, "timia_tr_entries", [e]).status_code == 200


# ─── matriz editable y aplicada al instante ──────────────────────────────────

def test_account_manager_edits_matrix_and_server_applies_it(client):
    login(client, "u-juan"); put(client, "timia_kanban_tasks", [TASK]); client.post("/api/auth/logout")
    login(client, "u-rodolfo")
    matrix = client.get("/api/permissions").json()["matrix"]
    matrix["developer"] = [p for p in matrix["developer"] if p != "tasks.update_status"]
    assert put(client, "timia_role_permissions", matrix).status_code == 200
    client.post("/api/auth/logout"); login(client, "u-santiago")
    assert put(client, "timia_kanban_tasks", [{**TASK, "status": "done"}]).status_code == 403
    hack = {**matrix, "developer": matrix["developer"] + ["team.manage"]}
    assert put(client, "timia_role_permissions", hack).status_code == 403


def test_account_manager_always_has_everything(client):
    login(client, "u-rodolfo")
    assert put(client, "timia_role_permissions", {"account_manager": []}).status_code == 200
    me = client.get("/api/auth/me").json()
    assert me["user"]["role"] == "account_manager" and "team.manage" in me["permissions"]


def test_legacy_roles_normalized(client):
    login(client, "u-rodolfo")
    users = get(client, "timia_admin_users"); users[-1]["role"] = "tech_ref"
    assert put(client, "timia_admin_users", users).status_code == 200
    client.post("/api/auth/logout"); login(client, users[-1]["id"])
    assert client.get("/api/auth/me").json()["user"]["role"] == "tech_lead"


def test_pilot_project_seeded(client):
    login(client, "u-amilkar")
    me = client.get("/api/auth/me").json()
    assert me["user"]["role"] == "tech_lead" and "MIGBD" in me["user"]["projectIds"]
    projs = get(client, "timia_admin_projects")
    assert len(projs) == 1 and projs[0]["id"] == "MIGBD" and projs[0]["sda"] == "SDATOOL-54364"
    cfg = get(client, "timia_plan_configs")["MIGBD"]
    assert cfg["startDate"] == "2026-02-18" and len(cfg["entregables"]) == 9


# ─── rol por proyecto ─────────────────────────────────────────────────────────

def test_role_override_per_project(client):
    """Amilkar es líder técnico base; si el gerente lo marca developer en MIGBD, en MIGBD pierde plan.edit_progress."""
    login(client, "u-rodolfo")
    assert put(client, "timia_project_roles", {"u-amilkar:MIGBD": "developer"}).status_code == 200
    client.post("/api/auth/logout"); login(client, "u-amilkar")
    r = put(client, "timia_plan_pcts", {"MIGBD-documentacion-y-0": 40})
    assert r.status_code == 403 and "MIGBD" in r.json()["detail"]
    issues = get(client, "timia_plan_issues") or []
    issues.append({"id": "is-ov", "planKey": "MIGBD", "type": "bloqueante", "title": "t", "startDate": "2026-09-13", "createdBy": "x", "createdAt": "x"})
    assert put(client, "timia_plan_issues", issues).status_code == 200          # dev sí reporta bloqueantes
    client.post("/api/auth/logout"); login(client, "u-rodolfo")
    assert put(client, "timia_project_roles", {}).status_code == 200
    client.post("/api/auth/logout"); login(client, "u-amilkar")
    assert put(client, "timia_plan_pcts", {"MIGBD-documentacion-y-0": 40}).status_code == 200


def test_developer_has_no_plan_view(client):
    login(client, "u-santiago")
    me = client.get("/api/auth/me").json()
    assert "plan.view" not in me["permissions"] and "plan.manage_issues" in me["permissions"]
