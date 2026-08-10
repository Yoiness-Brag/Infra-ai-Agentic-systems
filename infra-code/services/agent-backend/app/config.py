"""Application settings (pydantic-settings).

Fail-closed: required secrets have NO usable defaults. If any required value is
empty (``""``) or a known-insecure placeholder, the service refuses to start.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

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
    jwt_algorithm: Literal["HS256"] = Field(default="HS256", alias="JWT_ALGORITHM")

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
    gemini_model: str = Field(default="gemini-3.5-flash", alias="GEMINI_MODEL")
    gemini_embedding_model: str = Field(
        default="gemini-embedding-001", alias="GEMINI_EMBEDDING_MODEL"
    )
    graphiti_op_timeout_seconds: float = Field(
        default=60.0, alias="GRAPHITI_OP_TIMEOUT"
    )

    kagent_agent_a2a_url: str = Field(alias="KAGENT_AGENT_A2A_URL")
    a2a_timeout_seconds: float = Field(default=45.0, alias="A2A_TIMEOUT_SECONDS")
    a2a_max_retries: int = Field(default=1, alias="A2A_MAX_RETRIES")
    a2a_breaker_threshold: int = Field(default=5, alias="A2A_BREAKER_THRESHOLD")
    a2a_breaker_cooldown_seconds: float = Field(
        default=30.0, alias="A2A_BREAKER_COOLDOWN_SECONDS"
    )

    request_budget_seconds: float = Field(default=150.0, alias="REQUEST_BUDGET_SECONDS")

    minio_endpoint: str = Field(default="minio.ai-platform:9000", alias="MINIO_ENDPOINT")
    minio_access_key: str = Field(default="", alias="MINIO_ROOT_USER")
    minio_secret_key: str = Field(default="", alias="MINIO_ROOT_PASSWORD")
    minio_bucket: str = Field(default="documents", alias="MINIO_BUCKET")
    minio_secure: bool = Field(default=False, alias="MINIO_SECURE")

    max_upload_bytes: int = Field(default=25 * 1024 * 1024, alias="MAX_UPLOAD_BYTES")
    max_pdf_pages: int = Field(default=400, alias="MAX_PDF_PAGES")
    chunk_size: int = Field(default=1200, alias="CHUNK_SIZE")
    chunk_overlap: int = Field(default=150, alias="CHUNK_OVERLAP")
    ingest_concurrency: int = Field(default=2, alias="INGEST_CONCURRENCY")
    ingest_poll_seconds: float = Field(default=5.0, alias="INGEST_POLL_SECONDS")
    ingest_max_attempts: int = Field(default=3, alias="INGEST_MAX_ATTEMPTS")

    checkpoint_backend: Literal["falkordb", "memory"] = Field(
        default="falkordb", alias="CHECKPOINT_BACKEND"
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

    @field_validator("kagent_agent_a2a_url")
    @classmethod
    def _require_trailing_slash(cls, value: str) -> str:
        """kagent routes A2A on a path prefix; a missing trailing slash 404s."""
        if not value.startswith(("http://", "https://")):
            raise ValueError("KAGENT_AGENT_A2A_URL must be an http(s) URL")
        return value if value.endswith("/") else value + "/"

    @property
    def postgres_dsn(self) -> str:
        """Return the libpq DSN for the configured Postgres instance."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @staticmethod
    def _slug(value: str) -> str:
        """Graphiti only accepts [A-Za-z0-9_-] in a group_id.

        Subjects come from a JWT and routinely contain '@' or '.', so every
        component is slugified before it becomes part of a partition key.
        """
        return "".join(c if (c.isascii() and (c.isalnum() or c in "-_")) else "_" for c in value)

    def session_group_id(self, session_id: str) -> str:
        """Graph partition for a conversation."""
        return f"{self._slug(self.workload_app)}_session_{self._slug(session_id)}"

    def document_group_id(self, subject: str, document_id: str) -> str:
        """Graph partition for one uploaded document, scoped to its owner."""
        return (
            f"{self._slug(self.workload_app)}_{self._slug(subject)}"
            f"_doc_{self._slug(document_id)}"
        )

    def owner_document_prefix(self, subject: str) -> str:
        """Prefix shared by every document partition belonging to one subject."""
        return f"{self._slug(self.workload_app)}_{self._slug(subject)}_doc_"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor. Raises on missing/insecure secrets at first call."""
    return Settings()
