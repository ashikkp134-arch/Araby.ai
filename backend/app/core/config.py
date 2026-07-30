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
        openai_coding_max_tokens: Maximum output-token budget for coding requests.
        xai_api_key: xAI API key used by the Grok provider.
        xai_model_light: Fast Grok model for planning and lightweight tasks.
        xai_model_coding: Grok model used for website/code generation.
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
    openai_model: str = Field(default="gpt-5.6-terra", alias="OPENAI_MODEL")
    openai_model_light: str = Field(default="gpt-5.6-terra", alias="OPENAI_MODEL_LIGHT")
    openai_model_coding: str = Field(default="gpt-5.6-sol", alias="OPENAI_MODEL_CODING")
    openai_coding_max_tokens: int = Field(
        default=128_000,
        ge=1,
        le=128_000,
        alias="OPENAI_CODING_MAX_TOKENS",
    )
    xai_api_key: str = Field(default="", alias="XAI_API_KEY")
    xai_model_light: str = Field(default="grok-4.3", alias="XAI_MODEL_LIGHT")
    xai_model_coding: str = Field(default="grok-4.5", alias="XAI_MODEL_CODING")
    xai_base_url: str = Field(default="https://api.x.ai/v1", alias="XAI_BASE_URL")
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
    
    otel_enabled: bool = Field(default=True, alias="OTEL_ENABLED")
    otel_endpoint: str = Field(
        default="https://app.phoenix.arize.com/s/AI-Coding-Workspace/v1/traces",
        alias="OTEL_EXPORTER_OTLP_ENDPOINT",
    )
    otel_headers: str = Field(default="", alias="OTEL_EXPORTER_OTLP_HEADERS")
    otel_service_name: str = Field(default="araby-codeai-backend", alias="OTEL_SERVICE_NAME")
    phoenix_collector_endpoint: str = Field(default="", alias="PHOENIX_COLLECTOR_ENDPOINT")
    phoenix_api_key: str = Field(default="", alias="PHOENIX_API_KEY")
    phoenix_project: str = Field(default="", alias="PHOENIX_PROJECT")
    guardrails_enabled: bool = Field(default=True, alias="GUARDRAILS_ENABLED")
    guardrails_block_on_input: bool = Field(default=True, alias="GUARDRAILS_BLOCK_ON_INPUT")
    guardrails_block_on_output: bool = Field(default=True, alias="GUARDRAILS_BLOCK_ON_OUTPUT")
    # After website/React file applies, auto-repair missing imports up to N times.
    preview_repair_max_retries: int = Field(default=3, alias="PREVIEW_REPAIR_MAX_RETRIES")
    # Asset Resolution Service (images before LLM generation).
    asset_resolution_enabled: bool = Field(default=True, alias="ASSET_RESOLUTION_ENABLED")
    asset_resolution_validate: bool = Field(default=True, alias="ASSET_RESOLUTION_VALIDATE")
    asset_resolution_per_role: int = Field(default=4, alias="ASSET_RESOLUTION_PER_ROLE")
    # Wall-clock budget for provider search plus OpenAI semantic verification.
    asset_resolution_budget_seconds: float = Field(
        default=30.0,
        alias="ASSET_RESOLUTION_BUDGET_SECONDS",
    )
    asset_semantic_verification_enabled: bool = Field(
        default=True,
        alias="ASSET_SEMANTIC_VERIFICATION_ENABLED",
    )
    openai_image_verification_model: str = Field(
        default="gpt-4o-mini",
        alias="OPENAI_IMAGE_VERIFICATION_MODEL",
    )
    image_verification_api_key: str = Field(default="", alias="IMAGE_VERIFICATION_API_KEY")
    image_verification_model: str = Field(
        default="gpt-4o-mini",
        alias="IMAGE_VERIFICATION_MODEL",
    )
    image_verification_base_url: str = Field(
        default="https://api.openai.com/v1",
        alias="IMAGE_VERIFICATION_BASE_URL",
    )
    unsplash_access_key: str = Field(default="", alias="UNSPLASH_ACCESS_KEY")
    pexels_api_key: str = Field(default="", alias="PEXELS_API_KEY")

    # Agentic Website Builder (LangGraph multi-stage generation).
    website_agentic_enabled: bool = Field(default=True, alias="WEBSITE_AGENTIC_ENABLED")
    website_agentic_max_repair: int = Field(default=2, alias="WEBSITE_AGENTIC_MAX_REPAIR")
    website_agentic_github_search: bool = Field(
        default=True,
        alias="WEBSITE_AGENTIC_GITHUB_SEARCH",
    )
    github_token: str = Field(default="", alias="GITHUB_TOKEN")

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


def clear_settings_cache() -> None:
    """Drop the cached Settings so the next ``get_settings`` reloads ``.env``.

    Used on process (re)start with ``uvicorn --reload`` so key rotations and
    other env changes take effect without a full cold start.
    """
    get_settings.cache_clear()
