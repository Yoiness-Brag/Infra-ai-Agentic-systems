"""Application settings (pydantic-settings).

Fail-closed: required secrets have NO usable defaults. If any required value is
empty (``""``) or a known-insecure placeholder, the service refuses to start.
This is the REF-03/04 lesson from the platform reference-port review.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_FORBIDDEN_SECRET_VALUES = {"", "postgres", "password", "changeme", "secret", "default"}


class Settings(BaseSettings):
    """Runtime configuration sourced from environment / K8s secrets."""

    model_config = SettingsConfigDict(
        env_file=None,
        case_sensitive=True,
        extra="ignore",
    )

    app_name: str = Field(default="agent-backend", alias="APP_NAME")
    workload_app: str = Field(default="mvp-app", alias="X_WORKLOAD_APP")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    jwt_secret: str = Field(alias="JWT_SECRET")
    jwt_iss: str = Field(default="mvp-app", alias="JWT_ISS")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")

    postgres_host: str = Field(default="postgres.ai-platform", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_user: str = Field(alias="POSTGRES_USER")
    postgres_password: str = Field(alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(default="agentmvp", alias="POSTGRES_DB")
    postgres_pool_min_size: int = Field(default=1, alias="POSTGRES_POOL_MIN_SIZE")
    postgres_pool_max_size: int = Field(default=10, alias="POSTGRES_POOL_MAX_SIZE")
    postgres_command_timeout_seconds: float = Field(
        default=10.0, alias="POSTGRES_COMMAND_TIMEOUT_SECONDS"
    )
    postgres_acquire_timeout_seconds: float = Field(
        default=5.0, alias="POSTGRES_ACQUIRE_TIMEOUT_SECONDS"
    )

    falkordb_host: str = Field(default="falkordb.ai-platform", alias="FALKORDB_HOST")
    falkordb_port: int = Field(default=6379, alias="FALKORDB_PORT")
    falkordb_password: str = Field(default="", alias="FALKORDB_PASSWORD")

    google_api_key: str = Field(alias="GOOGLE_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")
    gemini_embedding_model: str = Field(
        default="gemini-embedding-001", alias="GEMINI_EMBEDDING_MODEL"
    )
    graphiti_op_timeout_seconds: float = Field(
        default=60.0, alias="GRAPHITI_OP_TIMEOUT"
    )

    kagent_agent_a2a_url: str = Field(alias="KAGENT_AGENT_A2A_URL")
    a2a_timeout_seconds: float = Field(default=60.0, alias="A2A_TIMEOUT_SECONDS")
    a2a_max_retries: int = Field(default=2, alias="A2A_MAX_RETRIES")
    a2a_breaker_threshold: int = Field(default=5, alias="A2A_BREAKER_THRESHOLD")
    a2a_breaker_cooldown_seconds: float = Field(
        default=30.0, alias="A2A_BREAKER_COOLDOWN_SECONDS"
    )

    @field_validator("jwt_secret", "postgres_password", "google_api_key")
    @classmethod
    def _reject_insecure_secret(cls, value: str, info: ValidationInfo) -> str:
        """Fail closed on empty / placeholder secrets."""
        if value is None or value.strip().lower() in _FORBIDDEN_SECRET_VALUES:
            raise ValueError(
                f"required secret '{info.field_name}' is empty or an insecure "
                f"placeholder; refusing to start (fail-closed)"
            )
        return value

    @property
    def postgres_dsn(self) -> str:
        """Return the libpq DSN for the configured Postgres instance."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor. Raises on missing/insecure secrets at first call."""
    return Settings()
