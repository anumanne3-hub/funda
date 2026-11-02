from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated environment configuration loaded once at process startup."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_name: str = "genai-chatbot-api"
    api_prefix: str = "/api/v1"
    frontend_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    log_level: str = "INFO"
    llm_provider: str = "mock"
    llm_model: str = "mock-stream-v1"
    llm_timeout_seconds: int = Field(default=45, ge=1, le=120)
    llm_max_output_tokens: int = Field(default=1000, ge=1, le=8000)

    @field_validator("frontend_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
