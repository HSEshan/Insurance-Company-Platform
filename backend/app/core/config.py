"""Application configuration loaded from environment variables.

Uses pydantic-settings so every value is validated and typed at startup.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- Application ---
    APP_ENV: Literal["development", "staging", "production", "test"] = "development"
    APP_NAME: str = "Insurance Management Platform"
    API_V1_PREFIX: str = "/api/v1"
    LOG_LEVEL: str = "INFO"
    FRONTEND_URL: str = "http://localhost:5173"
    DEMO_MODE_ENABLED: bool = True
    CHAT_WIDGET_ENABLED: bool = True
    GITHUB_REPO_URL: str = ""

    # --- Database ---
    DATABASE_URL: PostgresDsn = Field(
        default="postgresql+asyncpg://insurance:insurance@localhost:5432/insurance_db"  # type: ignore[arg-type]
    )

    # --- Redis ---
    REDIS_URL: RedisDsn = Field(default="redis://localhost:6379/0")  # type: ignore[arg-type]

    # --- Celery ---
    CELERY_BROKER_URL: str | None = None
    CELERY_RESULT_BACKEND: str | None = None
    PREMIUM_LAPSE_DAYS: int = 30
    ORPHAN_OBJECT_GRACE_MINUTES: int = 60

    # --- Email (MailHog in local compose) ---
    MAIL_SERVER: str = "localhost"
    MAIL_PORT: int = 1025
    MAIL_FROM: str = "noreply@insureco.com"
    MAIL_FROM_NAME: str = "InsureCo"
    EMAIL_NOTIFICATIONS_ENABLED: bool = True

    # --- Security ---
    SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION_use_a_256_bit_random_hex_value"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ENCRYPTION_KEY: str = "dev-only-insecure-32byte-key-padding-000000="

    # --- Auth hardening ---
    MAX_LOGIN_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 15

    # --- Object storage (MinIO) ---
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_PUBLIC_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_USE_SSL: bool = False
    MINIO_REGION: str = "us-east-1"
    PRESIGNED_URL_EXPIRY_MINUTES: int = 15
    MAX_UPLOAD_SIZE_MB: int = 25

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cors_origins(self) -> list[str]:
        return [self.FRONTEND_URL]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def max_upload_size_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @computed_field  # type: ignore[prop-decorator]
    @property
    def celery_broker_url(self) -> str:
        return self.CELERY_BROKER_URL or _redis_db(str(self.REDIS_URL), 1)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def celery_result_backend(self) -> str:
        return self.CELERY_RESULT_BACKEND or _redis_db(str(self.REDIS_URL), 2)


def _redis_db(url: str, db: int) -> str:
    """Point a redis:// URL at a different logical database."""
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(url)
    return urlunparse(parsed._replace(path=f"/{db}"))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
