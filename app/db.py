"""Conexión a MongoDB (Motor) y helpers de las colecciones de estado."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

from .config import settings

KEY_PREFIX = "timia_"
KV = "kv"                       # metadatos por key (+ valor si no es array)
USERS_KEY = "timia_admin_users"

_client: AsyncIOMotorClient | None = None


def connect() -> None:
    global _client
    _client = AsyncIOMotorClient(settings.MONGO_URL, serverSelectionTimeoutMS=5000)


def close() -> None:
    if _client:
        _client.close()


def db():
    assert _client is not None, "db no conectada"
    return _client[settings.MONGO_DB]


async def ping() -> None:
    await _client.admin.command("ping")  # type: ignore[union-attr]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_valid_key(key: str) -> bool:
    return key.startswith(KEY_PREFIX) and len(key) <= 120 and key.replace("_", "").replace("-", "").replace(":", "").isalnum()


# ─── Lectura / escritura de una key ──────────────────────────────────────────

async def read_key(key: str) -> Any | None:
    d = db()
    meta = await d[KV].find_one({"_id": key})
    if meta is None:
        return None
    if meta.get("kind") == "array":
        docs = await d[key].find({}, {"_ord": 1, "item": 1}).sort("_ord", 1).to_list(length=None)
        return [x["item"] for x in docs]
    return meta.get("value")


async def write_key(key: str, value: Any, by: str = "") -> None:
    d = db()
    if isinstance(value, list):
        await d[key].delete_many({})
        if value:
            docs, seen = [], set()
            for i, item in enumerate(value):
                _id = item.get("id") if isinstance(item, dict) and isinstance(item.get("id"), (str, int)) else i
                _id = str(_id)
                if _id in seen:
                    _id = f"{_id}#{i}"
                seen.add(_id)
                docs.append({"_id": _id, "_ord": i, "item": item})
            await d[key].insert_many(docs)
        await d[KV].replace_one({"_id": key}, {"_id": key, "kind": "array", "count": len(value), "updatedAt": now_iso(), "updatedBy": by}, upsert=True)
    else:
        await d[key].drop()
        await d[KV].replace_one({"_id": key}, {"_id": key, "kind": "value", "value": value, "updatedAt": now_iso(), "updatedBy": by}, upsert=True)


async def delete_key(key: str) -> None:
    await db()[key].drop()
    await db()[KV].delete_one({"_id": key})


async def list_keys() -> list[str]:
    return [m["_id"] async for m in db()[KV].find({}, {"_id": 1})]


async def list_meta() -> list[dict]:
    return [m async for m in db()[KV].find({}, {"_id": 1, "kind": 1, "count": 1, "updatedAt": 1, "updatedBy": 1})]


async def find_user_by_email(email: str) -> dict | None:
    """Usuario del panel (timia_admin_users) por correo, solo activos."""
    email = email.strip().lower()
    async for doc in db()[USERS_KEY].find({}, {"item": 1}):
        u = doc["item"]
        if str(u.get("email", "")).strip().lower() == email and u.get("active", True):
            return u
    return None


async def find_user_by_id(user_id: str) -> dict | None:
    doc = await db()[USERS_KEY].find_one({"_id": user_id}, {"item": 1})
    return doc["item"] if doc and doc["item"].get("active", True) else None


# ─── Seed ────────────────────────────────────────────────────────────────────

def seed_path() -> Path:
    here = Path(__file__).resolve().parent.parent
    if settings.SEED_FILE:
        return Path(settings.SEED_FILE)
    for p in (here / "seed.json", here.parent / "timia-hub" / "public" / "db.json"):
        if p.exists():
            return p
    return here / "seed.json"


async def seed_from_file(force: bool) -> dict:
    path = seed_path()
    if not path.exists():
        return {"seeded": [], "skipped": [], "note": f"sin seed file en {path}"}
    data = json.loads(path.read_text(encoding="utf-8"))
    existing = set(await list_keys())
    seeded, skipped = [], []
    for k, v in data.items():
        if not k.startswith(KEY_PREFIX):
            continue
        if k in existing and not force:
            skipped.append(k)
            continue
        await write_key(k, v, by="seed")
        seeded.append(k)
    return {"seeded": seeded, "skipped": skipped}
