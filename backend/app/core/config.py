from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Validated environment configuration loaded once at process startup."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    app_env: str = "development"
    app_name: str = "genai-chatbot-api"
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./genai_chatbot.db"
    database_pool_size: int = Field(default=3, ge=1, le=20)
    frontend_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )
    log_level: str = "INFO"
    session_cookie_name: str = "genai_session"
    session_ttl_days: int = Field(default=30, ge=1, le=365)
    session_cookie_secure: bool = False
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    migration_database_url: str | None = None
    llm_provider: Literal["mock", "openai", "gemini"] = "mock"
    llm_model: str = "mock-stream-v1"
    llm_api_key: str | None = None
    llm_base_url: str = "https://api.openai.com/v1"
    llm_timeout_seconds: int = Field(default=45, ge=1, le=120)
    llm_max_output_tokens: int = Field(default=1000, ge=1, le=8000)
    llm_input_usd_per_million: float = Field(default=0, ge=0)
    llm_output_usd_per_million: float = Field(default=0, ge=0)
    llm_daily_budget_usd: float = Field(default=1, gt=0)
    llm_free_tier: bool = False
    llm_daily_request_limit: int = Field(default=100, ge=1, le=10000)
    requests_per_minute: int = Field(default=20, ge=1)
    sessions_per_minute: int = Field(default=10, ge=1)

    @model_validator(mode="before")
    @classmethod
    def environment_defaults(cls, values: object) -> object:
        if isinstance(values, dict):
            values = dict(values)
            if values.get("llm_provider") == "gemini":
                values.setdefault("llm_model", "gemini-3.1-flash-lite")
        if isinstance(values, dict) and values.get("app_env") == "production":
            values.setdefault(
                "frontend_origins",
                ["https://funda-geni.vercel.app", "https://funda-phi.vercel.app"],
            )
            values.setdefault("session_cookie_secure", True)
            values.setdefault("session_cookie_samesite", "none")
        return values

    @model_validator(mode="after")
    def production_safety(self) -> "Settings":
        if self.session_cookie_samesite == "none" and not self.session_cookie_secure:
            raise ValueError("SameSite=None requires secure cookies")
        if self.llm_provider != "mock":
            if not self.llm_api_key or not self.llm_api_key.strip():
                raise ValueError("LLM_API_KEY is required for the selected LLM_PROVIDER")
            if not self.llm_model.strip() or self.llm_model == "mock-stream-v1":
                raise ValueError("LLM_MODEL must name a real provider model, not mock-stream-v1")
            if (
                not self.llm_free_tier
                and min(self.llm_input_usd_per_million, self.llm_output_usd_per_million) <= 0
            ):
                raise ValueError("Configure provider prices before enabling paid generation")
            if self.llm_free_tier and (
                self.llm_provider != "gemini"
                or self.llm_input_usd_per_million != 0
                or self.llm_output_usd_per_million != 0
            ):
                raise ValueError("Free-tier mode requires Gemini with zero configured prices")
        if self.app_env == "production":
            if not self.database_url.startswith("postgresql") or not self.session_cookie_secure:
                raise ValueError("Production requires PostgreSQL and secure cookies")
            if not self.frontend_origins or any(
                not origin.startswith("https://") or "*" in origin
                for origin in self.frontend_origins
            ):
                raise ValueError("Production requires exact HTTPS frontend origins")
        return self

    @field_validator("frontend_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
