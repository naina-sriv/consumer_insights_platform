from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database & Cache
    database_url: str = "postgresql+asyncpg://insights:insights@localhost:5432/insights"
    redis_url: str = "redis://redis:6379/0"

    # Security & Auth
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # LLM Gateway
    primary_provider: str = "openai"
    fallback_provider: str = "anthropic"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    llm_timeout_seconds: int = 30
    cache_ttl_seconds: int = 86400
    tenant_rpm_limit: int = 60

    # Embeddings
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536

    # Upload Limits
    max_upload_mb: int = 20
    max_rows_per_dataset: int = 20000

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
