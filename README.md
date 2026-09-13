# Timia Hub API

Backend de [Timia Hub](https://github.com/amilkarbolano-glitch/timia-hub): FastAPI + MongoDB.
Autenticación con Google (OIDC) o cuentas demo, sesión en cookie httpOnly, **roles y permisos aplicados en el servidor**
con alcance por proyecto, y persistencia del estado del front (una colección de Mongo por cada key `timia_*`).

## Arranque rápido
```bash
cp .env.example .env          # completa SESSION_SECRET (y GOOGLE_CLIENT_ID cuando lo tengan)
docker compose up -d --build  # api en :8000 + mongo
open http://localhost:8000/docs
```
Sin Docker: `pip install -r requirements-dev.txt && python dev_mock.py` (Mongo en memoria) o
`MONGO_URL=mongodb://localhost:27017 uvicorn app.main:app --reload`.

Pruebas: `python -m pytest -q` (22 pruebas: auth, permisos, alcance por proyecto, cambios parciales, TR propio, matriz editable).

## Estructura
```
app/
  main.py          app FastAPI, CORS, startup (conexión + seed)
  config.py        variables de entorno (ver .env.example)
  db.py            Motor/Mongo · lectura/escritura por key · seed
  security.py      sesión JWT (cookie httpOnly) · API key de servicio · rate limit
  permissions.py   catálogo de permisos · matriz por rol · reglas por colección · check_write()
  routers/auth.py  /api/auth/config · google · demo · demo-accounts · me · logout
  routers/state.py /api/state · /api/state/{key} · /api/keys · /api/seed · /api/permissions
seed.json          datos iniciales (copia de public/db.json del front)
tests/             pytest (mongomock)
```

## Endpoints
| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| GET | `/api/health` | — | estado, nº de colecciones, métodos de login |
| GET | `/api/auth/config` | — | `{google, googleClientId, demo, allowedDomains}` |
| POST | `/api/auth/google` | — | `{credential}` (ID token de Google) → cookie de sesión + `user` |
| POST | `/api/auth/demo` | — | `{userId}` → sesión (solo si `ALLOW_DEMO_LOGIN`) |
| GET | `/api/auth/demo-accounts` | — | cuentas del panel (solo demo) |
| GET | `/api/auth/me` | sesión | `user` + `permissions` efectivos |
| POST | `/api/auth/logout` | sesión | borra la cookie |
| GET | `/api/permissions` | sesión | catálogo, defaults y matriz vigente |
| GET | `/api/state` | sesión/API key | todas las colecciones |
| GET/PUT/DELETE | `/api/state/{key}` | sesión/API key | una colección (PUT valida permisos y alcance; DELETE solo pm) |
| GET | `/api/keys` | sesión/API key | metadatos (`kind`, `count`, `updatedAt`, `updatedBy`) |
| POST | `/api/seed?force=` | pm | carga `seed.json` |

## Roles y permisos
- 4 roles: `account_manager` (gerente de cuenta: todo, sobre todos los proyectos del cliente), `pm` (todo sobre sus proyectos),
  `tech_lead` (líder / referente técnico: apoya al PM), `developer`. Catálogo y defaults en `app/permissions.py`.
  Roles antiguos `project_lead`/`tech_ref` se normalizan a `tech_lead`.
- El PM edita la matriz desde el front (**Herramientas › Roles y permisos**); se guarda en `timia_role_permissions`
  y el servidor la aplica en la siguiente petición. El gerente de cuenta siempre conserva todos los permisos.
- Cada colección tiene una regla (`KEY_RULES`): permiso requerido + alcance
  (`global`, `project` = solo ítems de proyectos asignados salvo `projects.view_all`, `own` = solo registros propios).
- `timia_kanban_tasks` admite cambios parciales: sin `tasks.manage` un usuario solo puede cambiar `status`
  (`tasks.update_status`), `comments` (`tasks.comment`) o `assigneeIds` (`tasks.assign`) de tareas existentes.
- El servidor calcula el **diff** entre lo guardado y lo enviado; escrituras sin cambios siempre pasan.

## Google Sign-In
Ver `.env.example` (sección `[GOOGLE]`). El front muestra el botón oficial de Google cuando `GOOGLE_CLIENT_ID`
está definido; el correo debe existir en **Administración › Equipo** (de ahí salen rol y proyectos).

## Modelo en Mongo
```js
use timia
db.timia_tr_entries.find({ "item.userId": "u-sergio" })
db.kv.find({}, { kind:1, count:1, updatedAt:1, updatedBy:1 })   // metadatos por colección
```
Arrays → un documento por ítem (`_id` = `id`, `_ord`, `item`). Objetos → documento en `kv` con `value`.
