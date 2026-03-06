from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "DOST Phil Onion Watch API"
    environment: str = "development"
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 60 * 12
    algorithm: str = "HS256"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "phil_onion_watch"
    postgres_user: str = "onion"
    postgres_password: str = "onion"
    database_url: str = "postgresql+psycopg://onion:onion@localhost:5432/phil_onion_watch"

    redis_url: str = "redis://localhost:6379/0"
    faiss_index_path: str = "storage/faiss/knowledge.index"
    faiss_metadata_path: str = "storage/faiss/knowledge_meta.json"
    reports_path: str = "storage/reports"
    local_embedding_dim: int = 128
    scheduler_timezone: str = "Asia/Manila"
    monthly_pipeline_cron: str = "0 2 1 * *"
    alert_refresh_cron: str = "0 6 * * *"
    report_generation_cron: str = "30 2 1 * *"
    reindex_documents_cron: str = "45 2 1 * *"
    job_max_retries: int = 3
    job_retry_backoff_seconds: int = 15
    notification_webhook_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
