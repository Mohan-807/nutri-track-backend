from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Loaded from backend/.env (see .env.example). Never import os.environ directly elsewhere —
    always go through get_settings() so tests can override cleanly."""

    database_url: str
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days
    cors_origins: str = "http://localhost:5173"
    environment: str = "development"

    # --- LLM providers ---------------------------------------------------------------------
    # Failover order, highest priority first. A provider with no API key is skipped
    # automatically, so removing a key is enough to disable it — no code change needed.
    llm_provider_order: str = "gemini,nvidia"

    # Gemini via Google AI Studio's free tier.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    gemini_timeout_seconds: float = 30.0

    # NVIDIA NIM — an OpenAI-compatible endpoint, driven by the `openai` SDK.
    nvidia_api_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_model: str = "nvidia/nemotron-3-ultra-550b-a55b"
    nvidia_timeout_seconds: float = 120.0  # a reasoning model; slower first token than Gemini
    nvidia_max_tokens: int = 8192  # generous: this model's private reasoning counts toward it

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def llm_provider_order_list(self) -> list[str]:
        return [name.strip() for name in self.llm_provider_order.split(",") if name.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
