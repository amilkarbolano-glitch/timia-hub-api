"""Configuración por variables de entorno."""
import os
import secrets


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


class Settings:
    MONGO_URL: str = os.getenv("MONGO_URL", "mongodb://mongo:27017")
    MONGO_DB: str = os.getenv("MONGO_DB", "timia")
    # Sesión
    SESSION_SECRET: str = os.getenv("SESSION_SECRET", "")
    SESSION_HOURS: int = int(os.getenv("SESSION_HOURS", "8"))
    COOKIE_NAME: str = os.getenv("COOKIE_NAME", "timia_session")
    COOKIE_SECURE: bool = _bool("COOKIE_SECURE", False)     # true detrás de HTTPS
    COOKIE_SAMESITE: str = os.getenv("COOKIE_SAMESITE", "lax")
    # Google Sign-In (OIDC). Vacío ⇒ solo modo demo
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    ALLOWED_EMAIL_DOMAINS: list[str] = [d.strip().lower() for d in os.getenv("ALLOWED_EMAIL_DOMAINS", "").split(",") if d.strip()]
    # Login demo (cuentas del panel sin contraseña). Por defecto solo si no hay Google configurado
    ALLOW_DEMO_LOGIN: bool = _bool("ALLOW_DEMO_LOGIN", not bool(os.getenv("GOOGLE_CLIENT_ID", "").strip()))
    # Acceso servicio-a-servicio (scripts, integraciones)
    API_KEY: str = os.getenv("TIMIA_API_KEY", "")
    CORS_ORIGINS: list[str] = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
    SEED_ON_START: bool = _bool("SEED_ON_START", True)
    SEED_FILE: str = os.getenv("SEED_FILE", "")
    # Rate limit de /api/auth/* (peticiones por minuto por IP)
    AUTH_RATE_LIMIT: int = int(os.getenv("AUTH_RATE_LIMIT", "30"))

    def __init__(self) -> None:
        if not self.SESSION_SECRET:
            # Secreto efímero: las sesiones se invalidan al reiniciar. En producción define SESSION_SECRET.
            self.SESSION_SECRET = secrets.token_urlsafe(48)
            self._ephemeral_secret = True
        else:
            self._ephemeral_secret = False


settings = Settings()
