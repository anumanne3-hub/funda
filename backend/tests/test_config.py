import pytest

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


def test_gemini_defaults_model_without_overriding_explicit_model(monkeypatch):
    monkeypatch.delenv("LLM_MODEL", raising=False)
    options = {
        "llm_provider": "gemini",
        "llm_api_key": "test-key",
        "llm_free_tier": True,
        "_env_file": None,
    }
    assert Settings(**options).llm_model == "gemini-3.1-flash-lite"
    assert Settings(**options, llm_model="explicit-model").llm_model == "explicit-model"


def test_provider_validation_identifies_model_and_hides_secrets():
    with pytest.raises(ValueError, match="LLM_MODEL") as error:
        Settings(
            llm_provider="gemini",
            llm_api_key="private-test-key",
            llm_model="mock-stream-v1",
            _env_file=None,
        )
    assert "private-test-key" not in str(error.value)
    assert "input_value" not in str(error.value)


def test_provider_validation_rejects_blank_key():
    with pytest.raises(ValueError, match="LLM_API_KEY"):
        Settings(llm_provider="gemini", llm_api_key="   ", _env_file=None)
