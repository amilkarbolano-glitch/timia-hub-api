"""
Roles y permisos de Timia Hub — fuente de verdad del servidor.

· PERMISSIONS: catálogo de permisos (id → módulo, etiqueta).
· DEFAULT_ROLE_PERMISSIONS: matriz por rol. El PM puede ajustarla desde el front
  (Herramientas › Roles y permisos); se guarda en la key `timia_role_permissions`
  y el servidor la usa en cada petición (con estos defaults como base).
· KEY_RULES: qué permiso exige escribir cada colección `timia_*` y con qué alcance:
    - 'global'  : basta el permiso
    - 'project' : además, cada ítem creado/modificado/eliminado debe pertenecer a un
                  proyecto del usuario (salvo que tenga projects.view_all)
    - 'own'     : cada ítem creado/modificado/eliminado debe ser del propio usuario
                  (userId == yo), salvo que tenga el permiso "any" alternativo
"""
from __future__ import annotations

from typing import Any

ROLES = ("account_manager", "pm", "tech_lead", "developer")

ROLE_LABELS = {
    "account_manager": "Gerente de cuenta",
    "pm": "Project Manager",
    "tech_lead": "Líder / Referente técnico",
    "developer": "Desarrollador",
}
# Roles antiguos → nuevos (migración de usuarios guardados)
LEGACY_ROLES = {"project_lead": "tech_lead", "tech_ref": "tech_lead"}


def normalize_role(role: str | None) -> str:
    r = LEGACY_ROLES.get(role or "", role or "developer")
    return r if r in ROLES else "developer"

# id → (módulo, etiqueta)
PERMISSIONS: dict[str, tuple[str, str]] = {
    # Proyectos y equipo
    "projects.view_all":   ("Proyectos", "Ver todos los proyectos (no solo los asignados)"),
    "projects.create":     ("Proyectos", "Crear proyectos (wizard) y plantillas"),
    "projects.manage":     ("Proyectos", "Administrar proyectos (Panel Admin)"),
    "team.manage":         ("Equipo",    "Gestionar usuarios y su asignación a proyectos"),
    "roles.manage":        ("Equipo",    "Editar la matriz de roles y permisos"),
    "config.manage":       ("Equipo",    "Configurar ANS, festivos y parámetros"),
    # Plan de trabajo
    "plan.view":           ("Plan de trabajo", "Ver el plan de trabajo"),
    "plan.edit_progress":  ("Plan de trabajo", "Marcar etapas, % de avance, asignados y Jira de actividades"),
    "plan.manage_issues":  ("Plan de trabajo", "Registrar y resolver alertas y bloqueantes"),
    "plan.export":         ("Plan de trabajo", "Exportar/imprimir el plan"),
    # Estimaciones
    "estimaciones.view":   ("Estimaciones", "Ver estimaciones"),
    "estimaciones.edit":   ("Estimaciones", "Editar estimaciones y cronogramas"),
    "estimaciones.generate": ("Estimaciones", "Generar el plan de trabajo desde la estimación"),
    # Tablero
    "tasks.view":          ("Tablero", "Ver el tablero de tareas"),
    "tasks.manage":        ("Tablero", "Crear, editar y eliminar tareas"),
    "tasks.update_status": ("Tablero", "Mover tareas de estado"),
    "tasks.assign":        ("Tablero", "Asignar tareas"),
    "tasks.comment":       ("Tablero", "Comentar tareas"),
    # Tareas (cambios funcionales)
    "bitacora.view":       ("Tareas · cambios funcionales", "Ver cambios funcionales"),
    "bitacora.write":      ("Tareas · cambios funcionales", "Registrar cambios funcionales"),
    # Circuitos BBVA
    "circuitos.view":      ("Circuitos BBVA", "Ver circuitos"),
    "circuitos.edit":      ("Circuitos BBVA", "Mover y editar circuitos"),
    # Recursos
    "inventario.view":     ("Recursos", "Ver inventario"),
    "inventario.edit":     ("Recursos", "Agregar y editar objetos del inventario"),
    "inventario.configure":("Recursos", "Configurar columnas/etapas del inventario y borrar"),
    "links.edit":          ("Recursos", "Agregar y borrar links"),
    "imputaciones.edit":   ("Recursos", "Editar imputaciones Jira"),
    # Activity Report
    "tr.view":             ("Activity Report", "Ver cumplimiento del TR"),
    "tr.load_own":         ("Activity Report", "Cargar mi propio TR"),
    "tr.load_any":         ("Activity Report", "Cargar el TR de cualquier persona"),
    "tr.manage_features":  ("Activity Report", "Definir features y horas por fase"),
    # Dirección
    "analytics.view":      ("Dirección", "Dashboard ejecutivo"),
    "bank_status.view":    ("Dirección", "Estado con el banco"),
    "standup.generate":    ("Dirección", "Generar standup"),
    "audit.view":          ("Dirección", "Ver auditoría"),
}

ALL = list(PERMISSIONS.keys())

DEFAULT_ROLE_PERMISSIONS: dict[str, list[str]] = {
    # Gerente de cuenta: todo, sobre todos los proyectos del cliente (números globales, dirección)
    "account_manager": ALL,
    # PM: todo sobre sus proyectos (no ve los de otros PM salvo projects.view_all)
    "pm": [p for p in ALL if p not in ("projects.view_all",)],
    # Líder / Referente técnico: apoya al PM — plan, estimaciones, alertas, inventario, TR del equipo
    "tech_lead": [
        "plan.view", "plan.edit_progress", "plan.manage_issues", "plan.export",
        "estimaciones.view", "estimaciones.edit",
        "tasks.view", "tasks.manage", "tasks.update_status", "tasks.assign", "tasks.comment",
        "bitacora.view", "bitacora.write", "circuitos.view", "circuitos.edit",
        "inventario.view", "inventario.edit", "inventario.configure", "links.edit", "imputaciones.edit",
        "tr.view", "tr.load_own", "tr.load_any", "tr.manage_features",
        "bank_status.view", "standup.generate",
    ],
    # Desarrollador: ve lo suyo, mueve sus tareas, reporta bloqueantes, carga su TR
    "developer": [
        "plan.view", "plan.manage_issues",
        "tasks.view", "tasks.update_status", "tasks.comment",
        "bitacora.view", "bitacora.write", "circuitos.view",
        "inventario.view", "inventario.edit",
        "tr.view", "tr.load_own",
    ],
}

# Colección → (permiso para escribir, alcance, opciones)
KEY_RULES: dict[str, dict[str, Any]] = {
    "timia_admin_users":      {"perm": "team.manage",       "scope": "global"},
    "timia_project_roles":    {"perm": "team.manage",       "scope": "global"},
    "timia_admin_projects":   {"perm": "projects.manage",   "scope": "global"},
    "timia_role_permissions": {"perm": "roles.manage",      "scope": "global"},
    "timia_ans_config":       {"perm": "config.manage",     "scope": "global"},
    "timia_bbva_ans_config":  {"perm": "config.manage",     "scope": "global"},
    "timia_holidays":         {"perm": "config.manage",     "scope": "global"},
    "timia_plan_configs":     {"perm": "estimaciones.edit", "scope": "project"},
    "timia_plan_startdates":  {"perm": "estimaciones.edit", "scope": "project"},
    "timia_plan_pcts":        {"perm": "plan.edit_progress","scope": "project"},
    "timia_etapa_states":     {"perm": "plan.edit_progress","scope": "project"},
    "timia_activity_done_dates": {"perm": "plan.edit_progress","scope": "project"},
    "timia_activity_assignees":  {"perm": "plan.edit_progress","scope": "project"},
    "timia_activity_jiras":   {"perm": "plan.edit_progress","scope": "project"},
    "timia_plan_historial":   {"perm": "plan.edit_progress","scope": "project"},
    "timia_plan_issues":      {"perm": "plan.manage_issues","scope": "project"},
    "timia_kanban_tasks":     {"perm": "tasks.manage",      "scope": "project",
                               # sin tasks.manage, se permite cambiar solo estos campos de tareas existentes
                               "partial": {"tasks.update_status": ["status"], "tasks.comment": ["comments"], "tasks.assign": ["assigneeIds"]}},
    "timia_bitacora":         {"perm": "bitacora.write",    "scope": "project"},
    "timia_circuitos":        {"perm": "circuitos.edit",    "scope": "project"},
    "timia_inv_v2":           {"perm": "inventario.edit",   "scope": "project"},
    "timia_inv_stages":       {"perm": "inventario.configure", "scope": "global"},
    "timia_links":            {"perm": "links.edit",        "scope": "project"},
    "timia_imputaciones":     {"perm": "imputaciones.edit", "scope": "project"},
    "timia_tr_features":      {"perm": "tr.manage_features","scope": "project"},
    "timia_tr_entries":       {"perm": "tr.load_any",       "scope": "own", "own_perm": "tr.load_own"},
}
# Keys con prefijo (notas del plan por cronograma)
PREFIX_RULES: list[tuple[str, dict[str, Any]]] = [
    ("timia_notes_", {"perm": "plan.edit_progress", "scope": "project"}),
]


def rule_for(key: str) -> dict[str, Any] | None:
    if key in KEY_RULES:
        return KEY_RULES[key]
    for prefix, rule in PREFIX_RULES:
        if key.startswith(prefix):
            return rule
    return None


def effective_matrix(stored: dict | None) -> dict[str, list[str]]:
    """Matriz vigente: defaults + ajustes guardados (solo permisos conocidos y roles conocidos)."""
    out = {r: list(p) for r, p in DEFAULT_ROLE_PERMISSIONS.items()}
    if isinstance(stored, dict):
        for role, perms in stored.items():
            if role in ROLES and isinstance(perms, list):
                out[role] = [p for p in perms if p in PERMISSIONS]
    out["account_manager"] = ALL   # el gerente de cuenta siempre tiene todo (evita bloquearse a sí mismo)
    return out


def has(matrix: dict[str, list[str]], role: str, perm: str) -> bool:
    return perm in matrix.get(role, [])


# ─── Alcance: a qué proyecto pertenece un ítem / una key de objeto ────────────

def project_of_item(item: Any) -> str | None:
    if not isinstance(item, dict):
        return None
    if isinstance(item.get("projectId"), str):
        return item["projectId"]
    if isinstance(item.get("planKey"), str):
        return item["planKey"].split("::")[0]
    return None


def project_of_object_key(k: str) -> str | None:
    """Keys de objetos: 'FICO::input' · 'FICO-doc-2' · 'FICO__doc__2__et' · 'FICO' → 'FICO'."""
    for sep in ("::", "__", "-"):
        if sep in k:
            return k.split(sep)[0]
    return k or None


def changed_items(old: Any, new: Any) -> list[tuple[str, Any, Any]]:
    """Diferencias entre dos valores (arrays por id / objetos por key). Devuelve (id, antes, después)."""
    out: list[tuple[str, Any, Any]] = []
    if isinstance(old, list) or isinstance(new, list):
        def by_id(v):
            d = {}
            for i, it in enumerate(v or []):
                _id = it.get("id") if isinstance(it, dict) and it.get("id") is not None else f"#{i}"
                d[str(_id)] = it
            return d
        o, n = by_id(old if isinstance(old, list) else []), by_id(new if isinstance(new, list) else [])
        for k in set(o) | set(n):
            if o.get(k) != n.get(k):
                out.append((k, o.get(k), n.get(k)))
    elif isinstance(old, dict) or isinstance(new, dict):
        o, n = (old if isinstance(old, dict) else {}), (new if isinstance(new, dict) else {})
        for k in set(o) | set(n):
            if o.get(k) != n.get(k):
                out.append((str(k), o.get(k), n.get(k)))
    else:
        if old != new:
            out.append(("", old, new))
    return out


def check_write(key: str, old: Any, new: Any, *, role: str, user_id: str, project_ids: list[str], matrix: dict[str, list[str]]) -> str | None:
    """Devuelve None si la escritura está permitida; si no, el motivo."""
    rule = rule_for(key)
    if rule is None:
        return None                                   # colecciones sin regla: cualquier usuario autenticado
    perm, scope = rule["perm"], rule["scope"]
    full = has(matrix, role, perm)
    all_projects = has(matrix, role, "projects.view_all")
    diffs = changed_items(old, new)
    if not diffs:
        return None

    if scope == "global":
        return None if full else f"Requiere el permiso '{perm}'"

    if scope == "own":
        any_ok = full
        own_ok = has(matrix, role, rule.get("own_perm", perm))
        if not any_ok and not own_ok:
            return f"Requiere el permiso '{perm}' o '{rule.get('own_perm')}'"
        if not any_ok:
            for _id, before, after in diffs:
                for it in (before, after):
                    if isinstance(it, dict) and it.get("userId") not in (None, user_id):
                        return "Solo puedes modificar tus propios registros"
        return None

    # scope == 'project'
    partial = rule.get("partial", {})
    if not full:
        allowed_fields: set[str] = set()
        for p, fields in partial.items():
            if has(matrix, role, p):
                allowed_fields.update(fields)
        if not allowed_fields:
            return f"Requiere el permiso '{perm}'"
        # Solo cambios parciales sobre ítems existentes
        for _id, before, after in diffs:
            if before is None or after is None or not isinstance(before, dict) or not isinstance(after, dict):
                return f"Crear o eliminar requiere el permiso '{perm}'"
            changed = {f for f in set(before) | set(after) if before.get(f) != after.get(f)}
            if not changed <= allowed_fields:
                return f"Solo puedes cambiar {', '.join(sorted(allowed_fields))} (requiere '{perm}' para más)"
    if all_projects:
        return None
    # Alcance por proyecto
    for _id, before, after in diffs:
        projs = set()
        for it in (before, after):
            p = project_of_item(it)
            if p:
                projs.add(p)
        if not projs and isinstance(new, dict):
            p = project_of_object_key(_id)
            if p:
                projs.add(p)
        for p in projs:
            if p not in project_ids:
                return f"No tienes acceso al proyecto {p}"
    return None
