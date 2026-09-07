from conftest import login


def get(c, key):
    return c.get(f"/api/state/{key}").json()


def put(c, key, value):
    return c.put(f"/api/state/{key}", json={"value": value})


# ─── globales ────────────────────────────────────────────────────────────────

def test_developer_cannot_edit_admin_users(client):
    login(client, "u-sergio")
    users = get(client, "timia_admin_users")
    users[0]["name"] = "hack"
    r = put(client, "timia_admin_users", users)
    assert r.status_code == 403 and "team.manage" in r.json()["detail"]


def test_pm_can_edit_admin_users(client):
    login(client, "u-rodolfo")
    users = get(client, "timia_admin_users")
    users[0]["areaLabel"] = "cambio"
    assert put(client, "timia_admin_users", users).status_code == 200


def test_noop_write_is_allowed(client):
    login(client, "u-sergio")
    users = get(client, "timia_admin_users")
    assert put(client, "timia_admin_users", users).status_code == 200   # sin cambios → ok


# ─── alcance por proyecto ─────────────────────────────────────────────────────

def test_developer_issue_in_own_project(client):
    u = login(client, "u-sergio")
    assert "CRONOS" in u["projectIds"]
    issues = get(client, "timia_plan_issues")
    issues.append({"id": "is-t1", "planKey": "CRONOS::input", "type": "alerta", "title": "t", "startDate": "2026-09-07", "createdBy": "x", "createdAt": "x"})
    assert put(client, "timia_plan_issues", issues).status_code == 200


def test_developer_issue_in_other_project_denied(client):
    u = login(client, "u-sergio")
    other = next(p for p in ["BCBS239", "MURIC", "SDM1", "OPTIM"] if p not in u["projectIds"])
    issues = get(client, "timia_plan_issues")
    issues.append({"id": "is-t2", "planKey": other, "type": "alerta", "title": "t", "startDate": "2026-09-07", "createdBy": "x", "createdAt": "x"})
    r = put(client, "timia_plan_issues", issues)
    assert r.status_code == 403 and other in r.json()["detail"]


def test_object_keys_scoped_by_project(client):
    u = login(client, "u-sergio")
    other = next(p for p in ["BCBS239", "MURIC", "SDM1", "OPTIM"] if p not in u["projectIds"])
    pcts = get(client, "timia_plan_pcts") or {}
    ok = dict(pcts); ok["CRONOS-doc-0"] = 50
    assert put(client, "timia_plan_pcts", ok).status_code == 403   # developer no tiene plan.edit_progress
    login(client, "u-juan")                                           # tech_lead: sí, y ve todos los proyectos
    bad = dict(pcts); bad[f"{other}-doc-0"] = 50
    assert put(client, "timia_plan_pcts", bad).status_code == 200


def test_tech_ref_scoped_progress(client):
    # tech_ref tiene plan.edit_progress pero no projects.view_all → solo sus proyectos
    users = client.get("/api/auth/demo-accounts").json()
    ref = next((x for x in users if x["role"] == "tech_ref"), None)
    if not ref:
        return
    login(client, ref["id"])
    other = next(p for p in ["BCBS239", "MURIC", "SDM1", "OPTIM", "FICO", "CRONOS"] if p not in ref["projectIds"])
    pcts = get(client, "timia_plan_pcts") or {}
    mine = dict(pcts); mine[f"{ref['projectIds'][0]}-doc-0"] = 10
    assert put(client, "timia_plan_pcts", mine).status_code == 200
    bad = dict(pcts); bad[f"{other}-doc-0"] = 10
    assert put(client, "timia_plan_pcts", bad).status_code == 403


# ─── kanban: cambios parciales ───────────────────────────────────────────────

def test_developer_can_move_task_but_not_create(client):
    u = login(client, "u-sergio")
    tasks = get(client, "timia_kanban_tasks")
    mine = next(t for t in tasks if t.get("projectId") in u["projectIds"])
    moved = [dict(t) for t in tasks]
    for t in moved:
        if t["id"] == mine["id"]:
            t["status"] = "review" if t["status"] != "review" else "done"
    assert put(client, "timia_kanban_tasks", moved).status_code == 200
    # editar título → 403
    edited = [dict(t) for t in tasks]
    for t in edited:
        if t["id"] == mine["id"]:
            t["title"] = "otro título"
    r = put(client, "timia_kanban_tasks", edited)
    assert r.status_code == 403 and "status" in r.json()["detail"]
    # crear → 403
    created = tasks + [{**mine, "id": "kt-new"}]
    assert put(client, "timia_kanban_tasks", created).status_code == 403


def test_tech_lead_can_create_task(client):
    login(client, "u-juan")
    tasks = get(client, "timia_kanban_tasks")
    tasks.append({"id": "kt-new-2", "title": "nueva", "description": "", "priority": "Media", "startDate": "2026-09-07", "endDate": "2026-09-08",
                  "status": "backlog", "assigneeIds": [], "projectId": "CRONOS", "links": [], "comments": []})
    assert put(client, "timia_kanban_tasks", tasks).status_code == 200


# ─── TR: propio vs cualquiera ────────────────────────────────────────────────

def test_developer_loads_only_own_tr(client):
    login(client, "u-sergio")
    entries = get(client, "timia_tr_entries")
    own = entries + [{"id": "tr-x1", "userId": "u-sergio", "userName": "S", "date": "2026-09-07", "featureId": "DECRONOS-2169", "phase": "Pruebas", "hours": 8, "source": "manual", "createdAt": "x"}]
    assert put(client, "timia_tr_entries", own).status_code == 200
    other = entries + [{"id": "tr-x2", "userId": "u-juan", "userName": "J", "date": "2026-09-07", "featureId": "DECRONOS-2169", "phase": "Pruebas", "hours": 8, "source": "manual", "createdAt": "x"}]
    r = put(client, "timia_tr_entries", other)
    assert r.status_code == 403 and "propios" in r.json()["detail"]


def test_project_lead_loads_any_tr(client):
    users = client.get("/api/auth/demo-accounts").json()
    pl = next((x for x in users if x["role"] == "project_lead"), None)
    if not pl:
        return
    login(client, pl["id"])
    entries = get(client, "timia_tr_entries")
    entries.append({"id": "tr-x3", "userId": "u-sergio", "userName": "S", "date": "2026-09-07", "featureId": "DECRONOS-2169", "phase": "Pruebas", "hours": 8, "source": "manual", "createdAt": "x"})
    assert put(client, "timia_tr_entries", entries).status_code == 200


# ─── matriz editable por el PM y aplicada al instante ────────────────────────

def test_pm_edits_matrix_and_server_applies_it(client):
    login(client, "u-rodolfo")
    matrix = client.get("/api/permissions").json()["matrix"]
    matrix["developer"] = [p for p in matrix["developer"] if p != "tasks.update_status"]
    assert put(client, "timia_role_permissions", matrix).status_code == 200
    client.post("/api/auth/logout")
    u = login(client, "u-sergio")
    tasks = get(client, "timia_kanban_tasks")
    mine = next(t for t in tasks if t.get("projectId") in u["projectIds"])
    moved = [dict(t) for t in tasks]
    for t in moved:
        if t["id"] == mine["id"]:
            t["status"] = "done" if t["status"] != "done" else "backlog"
    assert put(client, "timia_kanban_tasks", moved).status_code == 403
    # developer no puede darse permisos
    hack = {**matrix, "developer": matrix["developer"] + ["team.manage"]}
    assert put(client, "timia_role_permissions", hack).status_code == 403


def test_pm_always_has_everything(client):
    login(client, "u-rodolfo")
    assert put(client, "timia_role_permissions", {"pm": []}).status_code == 200
    me = client.get("/api/auth/me").json()
    assert "team.manage" in me["permissions"]
