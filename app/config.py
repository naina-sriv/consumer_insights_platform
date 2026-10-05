from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://insights:insights@localhost:5432/insights"
    redis_url: str = "redis://redis:6379/0"
    jwt_secret: str = "change-me"
    jwt_expire_minutes: int = 60
    
    primary_provider: str = "openai"
    fallback_provider: str = "anthropic"
    llm_timeout_seconds: int = 30
    cache_ttl_seconds: int = 86400
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    max_upload_mb: int = 20
    max_rows_per_dataset: int = 20000


settings = Settings()
