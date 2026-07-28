"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings.

    Attributes:
        mongo_uri: MongoDB connection URI.
        database_name: Target MongoDB database name.
        redis_url: Redis connection URL.
        jwt_secret: Secret used to sign access tokens.
        jwt_refresh_secret: Secret used to sign refresh tokens.
        openai_api_key: OpenAI API key for LLM calls.
        openai_model: Default OpenAI model identifier (fallback for both tiers).
        openai_model_light: Fast/cheap model for explanations and docs.
        openai_model_coding: Stronger model for generation and multi-file edits.
        openai_base_url: Optional OpenAI-compatible API base URL (empty = OpenAI).
        llm_provider: Active LLM provider name.
        access_token_expire: Access token lifetime in minutes.
        refresh_token_expire: Refresh token lifetime in minutes.
        cors_origins: Allowed CORS origins.
        cookie_secure: Whether auth cookies require HTTPS.
        rate_limit_login: Max login attempts per window.
        app_env: Application environment name.
        app_name: Human-readable application name.
        log_level: Logging level.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    mongo_uri: str = Field(default="mongodb://localhost:27017", alias="MONGO_URI")
    database_name: str = Field(default="ai_coding_workspace", alias="DATABASE_NAME")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    jwt_secret: str = Field(..., alias="JWT_SECRET")
    jwt_refresh_secret: str = Field(..., alias="JWT_REFRESH_SECRET")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    openai_model_light: str = Field(default="", alias="OPENAI_MODEL_LIGHT")
    openai_model_coding: str = Field(default="", alias="OPENAI_MODEL_CODING")
    # Optional OpenAI-compatible base URL (e.g. https://api.x.ai/v1 for Grok).
    # Leave empty to use the default OpenAI endpoint.
    openai_base_url: str = Field(default="", alias="OPENAI_BASE_URL")
    llm_provider: str = Field(default="openai", alias="LLM_PROVIDER")
    access_token_expire: int = Field(default=15, alias="ACCESS_TOKEN_EXPIRE")
    refresh_token_expire: int = Field(default=10080, alias="REFRESH_TOKEN_EXPIRE")
    cors_origins: str = Field(
        default="http://localhost:5173",
        alias="CORS_ORIGINS",
    )
    cookie_secure: bool = Field(default=False, alias="COOKIE_SECURE")
    rate_limit_login: int = Field(default=5, alias="RATE_LIMIT_LOGIN")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_name: str = Field(default="AI Coding Workspace", alias="APP_NAME")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @field_validator("jwt_secret", "jwt_refresh_secret")
    @classmethod
    def validate_secrets(cls, value: str) -> str:
        """Ensure JWT secrets meet minimum length.

        Args:
            value: Secret string from environment.

        Returns:
            Validated secret string.

        Raises:
            ValueError: If secret is shorter than 32 characters.
        """
        if len(value) < 32:
            raise ValueError("JWT secrets must be at least 32 characters")
        return value

    def get_cors_origins(self) -> List[str]:
        """Parse CORS origins into a list.

        Returns:
            List of allowed origin URLs.
        """
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings.

    Returns:
        Settings instance loaded from environment.
    """
    return Settings()
