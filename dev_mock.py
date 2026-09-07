"""API con Mongo en memoria (mongomock) — para desarrollo/pruebas sin Docker ni Mongo.
   pip install -r requirements-dev.txt && python dev_mock.py  → http://localhost:8000/docs"""
import sys
import app.db as dbmod
import app.main as m
from mongomock_motor import AsyncMongoMockClient
dbmod.AsyncIOMotorClient = lambda *a, **k: AsyncMongoMockClient()
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(m.app, host="0.0.0.0", port=int(sys.argv[1]) if len(sys.argv) > 1 else 8000, log_level="warning")
