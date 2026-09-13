import importlib, os


def test_empty_env_vars_count_as_unset(monkeypatch):
    for k, v in {"ALLOW_DEMO_LOGIN": "", "GOOGLE_CLIENT_ID": "", "SESSION_HOURS": "", "MONGO_DB": "", "AUTH_RATE_LIMIT": ""}.items():
        monkeypatch.setenv(k, v)
    import app.config as cfg
    importlib.reload(cfg)
    assert cfg.settings.ALLOW_DEMO_LOGIN is True          # sin Google ⇒ demo activo aunque la var esté vacía
    assert cfg.settings.SESSION_HOURS == 8 and cfg.settings.MONGO_DB == "timia" and cfg.settings.AUTH_RATE_LIMIT == 30


def test_google_disables_demo_by_default(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "abc.apps.googleusercontent.com"); monkeypatch.setenv("ALLOW_DEMO_LOGIN", "")
    import app.config as cfg
    importlib.reload(cfg)
    assert cfg.settings.ALLOW_DEMO_LOGIN is False
    monkeypatch.setenv("ALLOW_DEMO_LOGIN", "true"); importlib.reload(cfg)
    assert cfg.settings.ALLOW_DEMO_LOGIN is True
    monkeypatch.delenv("GOOGLE_CLIENT_ID"); monkeypatch.setenv("ALLOW_DEMO_LOGIN", ""); importlib.reload(cfg)
