from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gnani_api_key: str = ""
    gnani_prisma_model: str = "Prisma-v3.0"
    gnani_evon_model: str = "Evon-v3.3"
    gnani_timbre_model: str = "Timbre-v3.0"
    gnani_warp_model: str = "Warp-v2.0"
    gnani_prisma_ws_url: str = ""
    gnani_evon_url: str = ""
    gnani_timbre_ws_url: str = ""
    gnani_warp_url: str = ""
    cors_origins: str = "http://localhost:5173"
    max_audio_frame_bytes: int = 65536
    session_ttl_seconds: int = 1800

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
