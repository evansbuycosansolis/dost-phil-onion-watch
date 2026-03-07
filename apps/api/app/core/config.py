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
    oidc_enabled: bool = False
    oidc_discovery_url: str | None = None
    oidc_issuer_url: str | None = None
    oidc_jwks_url: str | None = None
    oidc_audience: str | None = None
    oidc_signing_algorithms: str = "RS256,HS256"
    oidc_role_claim: str = "roles"
    oidc_role_mapping: str = ""
    oidc_email_claim: str = "email"
    oidc_name_claim: str = "name"
    oidc_subject_claim: str = "sub"
    oidc_mfa_claim: str = "amr"
    oidc_mfa_boolean_claim: str = "mfa"
    oidc_mfa_methods: str = "mfa,otp,webauthn,sms,hwk"
    oidc_mfa_acr_claim: str = "acr"
    oidc_mfa_acr_values: str = "mfa,urn:mfa"
    oidc_privileged_roles: str = "super_admin,provincial_admin"
    oidc_sync_roles_on_login: bool = True
    oidc_auto_provision_users: bool = False
    oidc_cache_ttl_seconds: int = 300
    enforce_oidc_for_privileged_roles: bool = False
    enforce_mfa_for_privileged_tokens: bool = False
    faiss_index_path: str = "storage/faiss/knowledge.index"
    faiss_metadata_path: str = "storage/faiss/knowledge_meta.json"
    reports_path: str = "storage/reports"
    local_embedding_dim: int = 128
    scheduler_timezone: str = "Asia/Manila"
    monthly_pipeline_cron: str = "0 2 1 * *"
    alert_refresh_cron: str = "0 6 * * *"
    report_generation_cron: str = "30 2 1 * *"
    report_distribution_cron: str = "0 */6 * * *"
    observability_monitor_cron: str = "*/5 * * * *"
    reindex_documents_cron: str = "45 2 1 * *"
    document_ingestion_cron: str = "*/2 * * * *"
    agency_feed_ingestion_cron: str = "15 */6 * * *"
    geospatial_ingest_cron: str = "0 */12 * * *"
    geospatial_refresh_cron: str = "30 3 * * *"

    stac_api_url: str = "https://earth-search.aws.element84.com/v1"
    stac_timeout_seconds: float = 20.0
    geospatial_default_lookback_days: int = 30
    geospatial_enable_postgis: bool = True
    geospatial_default_srid: int = 4326
    geospatial_stac_sentinel2_enabled: bool = True
    geospatial_stac_sentinel1_enabled: bool = True
    geospatial_stac_landsat_enabled: bool = True
    job_max_retries: int = 3
    job_retry_backoff_seconds: int = 15
    report_distribution_batch_size: int = 50
    report_distribution_default_max_attempts: int = 3
    report_distribution_retry_backoff_seconds: int = 300
    observability_window_minutes: int = 60
    observability_event_retention_minutes: int = 1440
    observability_alert_cooldown_seconds: int = 900
    degraded_endpoint_min_requests: int = 20
    degraded_endpoint_error_rate_threshold: float = 0.2
    degraded_endpoint_p95_latency_ms_threshold: float = 1500.0
    job_failure_min_runs: int = 3
    job_failure_rate_threshold: float = 0.3
    document_ingestion_job_max_attempts: int = 5
    document_chunk_max_retries: int = 3
    document_ingestion_batch_size: int = 4
    agency_feed_fixtures_path: str = "data/fixtures/feeds"
    report_distribution_webhook_url: str | None = None
    notification_webhook_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
