from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    app_name: str = "Enterprise Agentic Research Platform"
    app_env: str = "development"
    app_debug: bool = True
    log_level: str = "INFO"

    api_host: str = "127.0.0.1"
    api_port: int = 8000

    anthropic_api_key: str = ""
    anthropic_model: str = ""
    tavily_api_key: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return one cached Settings instance for the application."""
    return Settings()


settings = get_settings()