from app.core.config import Settings


def test_environment_defaults_and_explicit_overrides(monkeypatch):
    for key in (
        "APP_ENV",
        "FRONTEND_ORIGINS",
        "SESSION_COOKIE_SECURE",
        "SESSION_COOKIE_SAMESITE",
        "LLM_PROVIDER",
    ):
        monkeypatch.delenv(key, raising=False)

    local = Settings(_env_file=None)
    assert local.frontend_origins == ["http://localhost:5173"]
    assert local.session_cookie_secure is False
    assert local.session_cookie_samesite == "lax"

    monkeypatch.setenv("APP_ENV", "production")
    production = Settings(database_url="postgresql+psycopg://unused/db", _env_file=None)
    assert production.frontend_origins == [
        "https://funda-geni.vercel.app",
        "https://funda-phi.vercel.app",
    ]
    assert production.session_cookie_secure is True
    assert production.session_cookie_samesite == "none"

    monkeypatch.setenv("FRONTEND_ORIGINS", "https://chat.example.com")
    monkeypatch.setenv("SESSION_COOKIE_SAMESITE", "lax")
    custom = Settings(database_url="postgresql+psycopg://unused/db", _env_file=None)
    assert custom.frontend_origins == ["https://chat.example.com"]
    assert custom.session_cookie_samesite == "lax"
