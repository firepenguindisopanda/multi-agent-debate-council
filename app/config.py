import logging
import secrets
from functools import lru_cache
from typing import Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


@lru_cache
def get_settings():
    return Settings()


class Settings(BaseSettings):
    database_uri: str = "sqlite:///database.db"
    secret_key: Optional[str] = None
    env: str = "development"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expires: int = 60 * 24  # minutes
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    db_pool_size: int = 10
    db_additional_overflow: int = 10
    db_pool_timeout: int = 10
    db_pool_recycle: int = 1800
    # Run `alembic upgrade head` and seed agents on startup.
    auto_migrate: bool = True

    # NVIDIA NIM (OpenAI-compatible) settings
    nvidia_api_key: Optional[str] = None
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    llm_model: str = "meta/llama-3.3-70b-instruct"
    llm_temperature: float = 0.7
    llm_top_p: float = 0.9
    llm_max_tokens: int = 450
    llm_summary_max_tokens: int = 1200
    llm_timeout_seconds: float = 90.0
    # Upper bound on debates running at the same time in this process.
    max_concurrent_debates: int = 4
    # Debates a non-admin user may start per rolling 24 hours (0 = unlimited).
    daily_debate_limit: int = 10

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def is_production(self) -> bool:
        return self.env.lower() in ("prod", "production")

    @property
    def is_dev(self) -> bool:
        return self.env.lower() in ("dev", "development")

    @property
    def llm_configured(self) -> bool:
        return bool(self.nvidia_api_key)

    @model_validator(mode="after")
    def _ensure_secret_key(self):
        if not self.secret_key:
            if self.is_production:
                raise ValueError("SECRET_KEY must be set in production")
            logger.warning("SECRET_KEY not set; using a random key (sessions reset on restart)")
            self.secret_key = secrets.token_urlsafe(48)
        return self
