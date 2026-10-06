"""Application settings (environment-driven; no secrets in source)."""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="MERP_", extra="ignore")

    app_name: str = "GMP-MERP"
    environment: str = "development"
    database_url: str = "sqlite:///./merp_dev.db"
    secret_key: str = Field(min_length=16)
    audit_hmac_key: str = Field(min_length=16)

    cookie_secure: bool = True
    session_idle_minutes: int = 15
    session_absolute_hours: int = 8
    max_concurrent_sessions: int = 0

    password_min_length: int = 12
    password_history: int = 12
    password_max_age_days: int = 90
    argon2_time_cost: int = 3
    argon2_memory_kib: int = 65536
    argon2_parallelism: int = 4
    lockout_threshold: int = 5
    lockout_minutes: int = 15
    login_rate_limit_per_minute: int = 20
    db_pool_size: int = 25            # connections kept per worker process (server databases)
    db_max_overflow: int = 35         # extra short-lived connections per worker; size >= worker threads (default thread pool 40) avoids pool starvation under load
    db_pool_timeout: int = 30

    ldap_enabled: bool = False
    ldap_server_uri: str = ""
    ldap_bind_format: str = "{username}"
    ldap_timeout_seconds: int = 5

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    file_storage_path: str = "./storage/documents"
    max_upload_mb: int = 10
    log_dir: str = "./logs"
    site_timezone: str = "Asia/Kolkata"
    scheduler_enabled: bool = False   # run in exactly one app instance, or use scripts/run_jobs.py via cron
    scheduler_interval_seconds: int = 3600

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
