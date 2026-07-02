from functools import lru_cache
from typing import Annotated

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_WEAK_JWT_SECRETS = {"your-secret-key", "change-me", "secret"}
_MIN_JWT_SECRET_LENGTH = 32


class Settings(BaseSettings):
    app_env: str = Field("development", validation_alias="APP_ENV")
    api_v1_prefix: str = Field("/api/v1", validation_alias="API_V1_PREFIX")
    frontend_url: str = Field("http://localhost:5173", validation_alias="FRONTEND_URL")
    frontend_url_alt: str = Field(
        "http://127.0.0.1:5173", validation_alias="FRONTEND_URL_ALT"
    )

    api_port: int = Field(8000, validation_alias="API_HOST_PORT")

    app_name: str = Field("Advocacia API", validation_alias="APP_NAME")
    app_version: str = Field("0.1.0", validation_alias="APP_VERSION")

    postgres_user: str = Field("postgres", validation_alias="POSTGRES_USER")
    postgres_password: str = Field("postgres", validation_alias="POSTGRES_PASSWORD")
    postgres_host: str = Field("localhost", validation_alias="POSTGRES_HOST")
    postgres_port: int = Field(5432, validation_alias="POSTGRES_PORT")
    postgres_db: str = Field("advocacia_db", validation_alias="POSTGRES_DB")

    jwt_secret_key: str = Field(validation_alias="JWT_SECRET_KEY")
    jwt_expire_minutes: int = Field(60, validation_alias="JWT_EXPIRE_MINUTES")
    password_reset_expire_minutes: int = Field(
        30, validation_alias="PASSWORD_RESET_EXPIRE_MINUTES"
    )

    resend_api_key: str = Field(validation_alias="RESEND_API_KEY")
    resend_from_email: str = Field(
        "onboarding@resend.dev", validation_alias="RESEND_FROM_EMAIL"
    )

    datajud_api_key: str = Field("", validation_alias="DATAJUD_API_KEY")
    datajud_base_url: str = Field(
        "https://api-publica.datajud.cnj.jus.br",
        validation_alias="DATAJUD_BASE_URL",
    )
    datajud_timeout_seconds: float = Field(
        10.0,
        gt=0,
        le=60,
        validation_alias="DATAJUD_TIMEOUT_SECONDS",
    )
    datajud_max_retries: int = Field(
        2,
        ge=0,
        le=5,
        validation_alias="DATAJUD_MAX_RETRIES",
    )
    datajud_retry_backoff_seconds: float = Field(
        0.5,
        ge=0,
        le=10,
        validation_alias="DATAJUD_RETRY_BACKOFF_SECONDS",
    )
    datajud_sync_interval_hours: int = Field(
        6,
        ge=1,
        le=168,
        validation_alias="DATAJUD_SYNC_INTERVAL_HOURS",
    )
    datajud_sync_limit: int = Field(
        50, ge=1, le=100, validation_alias="DATAJUD_SYNC_LIMIT"
    )
    datajud_sync_user_id: int | None = Field(
        None,
        validation_alias="DATAJUD_SYNC_USER_ID",
    )
    integration_failure_email_throttle_minutes: int = Field(
        30,
        ge=0,
        le=1440,
        validation_alias="INTEGRATION_FAILURE_EMAIL_THROTTLE_MINUTES",
    )

    lead_dedup_window_hours: int = Field(1, validation_alias="LEAD_DEDUP_WINDOW_HOURS")

    upload_dir: str = Field("uploads/media", validation_alias="UPLOAD_DIR")
    max_file_size_mb: int = Field(5, validation_alias="MAX_FILE_SIZE_MB")
    allowed_mime_types: list[str] = Field(
        default=["image/jpeg", "image/png"],
        validation_alias="ALLOWED_MIME_TYPES",
    )

    kanban_max_per_column: int = Field(100, validation_alias="KANBAN_MAX_PER_COLUMN")

    scheduler_enabled: bool = Field(True, validation_alias="SCHEDULER_ENABLED")
    deadline_alert_cron: str = Field("06:00", validation_alias="DEADLINE_ALERT_CRON")
    deadline_alert_intervals: Annotated[list[int], NoDecode] = Field(
        default=[30, 15, 7, 3, 2, 1],
        validation_alias="DEADLINE_ALERT_INTERVALS",
    )

    google_client_id: str = Field("", validation_alias="GOOGLE_CLIENT_ID")
    google_client_secret: str = Field("", validation_alias="GOOGLE_CLIENT_SECRET")
    google_redirect_uri: str = Field(
        "http://localhost:8000/api/v1/integrations/google/callback",
        validation_alias="GOOGLE_REDIRECT_URI",
    )
    google_token_encryption_key: str = Field(
        "", validation_alias="GOOGLE_TOKEN_ENCRYPTION_KEY"
    )
    google_pull_interval_minutes: int = Field(
        5,
        ge=1,
        le=1440,
        validation_alias="GOOGLE_PULL_INTERVAL_MINUTES",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("jwt_secret_key")
    @classmethod
    def strong_jwt_secret(cls, jwt_secret_key: str, info: ValidationInfo) -> str:
        if info.data.get("app_env") == "production" and (
            len(jwt_secret_key) < _MIN_JWT_SECRET_LENGTH
            or jwt_secret_key in _WEAK_JWT_SECRETS
        ):
            raise ValueError(
                "JWT_SECRET_KEY must be at least "
                f"{_MIN_JWT_SECRET_LENGTH} chars and not a known default in production"
            )
        return jwt_secret_key

    @field_validator("deadline_alert_intervals", mode="before")
    @classmethod
    def parse_intervals(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(part.strip()) for part in value.split(",") if part.strip()]
        return value

    @property
    def deadline_alert_cron_parts(self) -> tuple[int, int]:
        parts = self.deadline_alert_cron.split(":")
        if len(parts) != 2:
            raise ValueError("DEADLINE_ALERT_CRON must be in HH:MM format")
        hour, minute = int(parts[0]), int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("DEADLINE_ALERT_CRON hour/minute out of range")
        return hour, minute

    @property
    def google_configured(self) -> bool:
        return bool(
            self.google_client_id
            and self.google_client_secret
            and self.google_redirect_uri
            and self.google_token_encryption_key
        )

    @property
    def database_url(self) -> str:
        return (
            "postgresql+psycopg://"
            f"{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
