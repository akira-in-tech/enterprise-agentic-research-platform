from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    app_name: str = "Enterprise Agentic Research Platform"
    app_env: str = "development"
    app_debug: bool = True
    log_level: str = "INFO"
    run_live_tests: bool = False

    api_host: str = "127.0.0.1"
    api_port: int = 8000

    document_storage_root: str = "uploads"
    document_storage_provider: Literal["local", "s3"] = "local"
    document_s3_bucket: str = ""
    document_max_upload_bytes: int = Field(
        default=10_000_000,
        ge=1,
        le=100_000_000,
    )

    anthropic_model: str = ""
    anthropic_api_key: SecretStr = SecretStr("")
    tavily_api_key: SecretStr = SecretStr("")

    llm_provider: str = "anthropic"
    vector_store_provider: str = "memory"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    ollama_embedding_model: str = "qwen3-embedding:0.6b"
    ollama_embedding_dimensions: int = 1024
    embedding_provider: Literal["ollama", "bedrock"] = "ollama"
    aws_region: str = "us-west-2"
    bedrock_embedding_model: str = "amazon.titan-embed-text-v2:0"
    bedrock_embedding_dimensions: Literal[256, 512, 1024] = 1024

    milvus_uri: str = "http://localhost:19530"
    milvus_token: SecretStr = SecretStr("")
    milvus_collection: str = "private_document_chunks"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: SecretStr = SecretStr(
        "postgresql+asyncpg://research_user:change_me@localhost:5432/research_platform"
    )
    database_echo: bool = False

    redis_url: SecretStr = SecretStr(
        "redis://localhost:6379/0",
    )
    redis_max_connections: int = Field(
        default=20,
        ge=1,
        le=1000,
    )
    redis_socket_connect_timeout_seconds: float = Field(
        default=2.0,
        gt=0,
    )
    redis_socket_timeout_seconds: float = Field(
        default=2.0,
        gt=0,
    )
    redis_health_check_interval_seconds: int = Field(
        default=30,
        ge=0,
    )

    redis_research_result_ttl_seconds: int = Field(
        default=900,
        ge=1,
        le=86_400,
    )
    redis_research_idempotency_ttl_seconds: int = Field(
        default=86_400,
        ge=1,
        le=604_800,
    )
    redis_research_idempotency_lock_ttl_seconds: int = Field(
        default=300,
        ge=1,
        le=3600,
    )
    redis_research_rate_limit_requests: int = Field(
        default=20,
        ge=1,
        le=10_000,
    )
    redis_research_rate_limit_window_seconds: int = Field(
        default=60,
        ge=1,
        le=3600,
    )
    redis_research_progress_ttl_seconds: int = Field(
        default=3600,
        ge=1,
        le=604_800,
    )


@lru_cache
def get_settings() -> Settings:
    """Return one cached Settings instance for the application."""
    return Settings()


settings = get_settings()
