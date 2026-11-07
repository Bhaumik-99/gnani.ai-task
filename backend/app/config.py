from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    environment: Literal["development", "test", "production"] = "development"
    gnani_api_key: str = ""
    prisma_model: str = "prisma-v2.5"
    prisma_ws_url: str = "wss://api.vachana.ai/stt/v3/stream"
    prisma_language_code: Literal["hi-IN", "en-IN"] = "hi-IN"
    prisma_format: Literal["verbatim", "transcribe"] = "transcribe"
    prisma_sample_rate: Literal[8000, 16000] = 16000

    timbre_model: str = "timbre-v2.5"
    timbre_ws_url: str = "wss://api.vachana.ai/api/v1/tts"
    timbre_voice: str = "Poorvi"
    timbre_language: str = "hi-en"
    timbre_sample_rate: Literal[8000, 16000, 22050, 24000, 44100, 48000] = 24000

    # Evon v3.3 is served from its open weights through an OpenAI-compatible vLLM endpoint.
    evon_base_url: str = ""
    evon_api_key: str = ""
    evon_model: str = "model"
    evon_timeout_seconds: float = Field(default=20.0, gt=0, le=120)

    cors_origins: str = "http://localhost:5173"
    session_signing_secret: str = "development-only-change-this-secret"
    session_ttl_seconds: int = Field(default=840, ge=60, le=840)
    max_audio_frame_bytes: Literal[1024] = 1024
    max_transcript_chars: int = Field(default=4000, ge=200, le=12000)
    max_tts_audio_bytes: int = Field(default=12_000_000, ge=1024, le=50_000_000)
    max_sessions_per_minute: int = Field(default=10, ge=1, le=100)
    redis_url: str = ""

    @model_validator(mode="after")
    def validate_production_settings(self):
        if self.environment == "production":
            if len(self.session_signing_secret) < 32 or self.session_signing_secret.startswith("replace-") or self.session_signing_secret == "development-only-change-this-secret":
                raise ValueError("Production requires a unique random SESSION_SIGNING_SECRET of at least 32 characters")
            if not self.redis_url:
                raise ValueError("REDIS_URL is required in production")
            if not self.cors_origin_list or "*" in self.cors_origin_list:
                raise ValueError("Production CORS_ORIGINS must contain explicit origins")
            if self.evon_base_url and not self.evon_base_url.startswith("https://"):
                raise ValueError("EVON_BASE_URL must use HTTPS in production")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip().rstrip("/") for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
