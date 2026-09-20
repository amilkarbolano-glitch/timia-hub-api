"""Configuración por variables de entorno."""
import os
import secrets


def _env(name: str) -> str | None:
    """Valor de entorno; vacío (típico de un .env con `VAR=`) cuenta como no definido."""
    v = os.getenv(name)
    return None if v is None or not v.strip() else v.strip()


def _bool(name: str, default: bool) -> bool:
    v = _env(name)
    return default if v is None else v.lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    v = _env(name)
    try:
        return int(v) if v is not None else default
    except ValueError:
        return default


class Settings:
    MONGO_URL: str = _env("MONGO_URL") or "mongodb://mongo:27017"
    MONGO_DB: str = _env("MONGO_DB") or "timia"
    # Sesión
    SESSION_SECRET: str = os.getenv("SESSION_SECRET", "")
    SESSION_HOURS: int = _int("SESSION_HOURS", 8)
    COOKIE_NAME: str = _env("COOKIE_NAME") or "timia_session"
    COOKIE_SECURE: bool = _bool("COOKIE_SECURE", False)     # true detrás de HTTPS
    COOKIE_SAMESITE: str = _env("COOKIE_SAMESITE") or "lax"
    # Firebase Authentication (proveedor Google). Vacío ⇒ ver GOOGLE_CLIENT_ID / demo
    FIREBASE_PROJECT_ID: str = _env("FIREBASE_PROJECT_ID") or ""
    FIREBASE_API_KEY: str = _env("FIREBASE_API_KEY") or ""          # config pública del front
    FIREBASE_AUTH_DOMAIN: str = _env("FIREBASE_AUTH_DOMAIN") or ""
    FIREBASE_APP_ID: str = _env("FIREBASE_APP_ID") or ""
    # Google Sign-In directo (GIS/OIDC) — alternativa sin Firebase
    GOOGLE_CLIENT_ID: str = _env("GOOGLE_CLIENT_ID") or ""
    ALLOWED_EMAIL_DOMAINS: list[str] = [d.strip().lower() for d in os.getenv("ALLOWED_EMAIL_DOMAINS", "").split(",") if d.strip()]
    # Login demo (cuentas del panel sin contraseña). Por defecto solo si no hay Google configurado
    ALLOW_DEMO_LOGIN: bool = _bool("ALLOW_DEMO_LOGIN", _env("GOOGLE_CLIENT_ID") is None and _env("FIREBASE_PROJECT_ID") is None)
    # Primer administrador: si la base no tiene usuarios y entra este correo por Google,
    # se crea como gerente de cuenta. Después no vuelve a hacer nada (no reactiva ni cambia roles).
    BOOTSTRAP_ADMIN_EMAIL: str = (_env("BOOTSTRAP_ADMIN_EMAIL") or "").lower()
    BOOTSTRAP_ADMIN_NAME: str = _env("BOOTSTRAP_ADMIN_NAME") or ""
    # Acceso servicio-a-servicio (scripts, integraciones)
    API_KEY: str = os.getenv("TIMIA_API_KEY", "")
    CORS_ORIGINS: list[str] = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
    SEED_ON_START: bool = _bool("SEED_ON_START", True)
    SEED_FILE: str = os.getenv("SEED_FILE", "")
    # Rate limit de /api/auth/* (peticiones por minuto por IP)
    AUTH_RATE_LIMIT: int = _int("AUTH_RATE_LIMIT", 30)

    def __init__(self) -> None:
        if not self.SESSION_SECRET:
            # Secreto efímero: las sesiones se invalidan al reiniciar. En producción define SESSION_SECRET.
            self.SESSION_SECRET = secrets.token_urlsafe(48)
            self._ephemeral_secret = True
        else:
            self._ephemeral_secret = False


settings = Settings()
