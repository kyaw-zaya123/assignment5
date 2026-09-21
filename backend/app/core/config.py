"""Application settings — all external endpoints via environment."""

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Myanmar Logistics Intelligence"
    debug: bool = True
    api_prefix: str = "/api"
    secret_key: str = "dev-only-change-me"
    cors_origins: str = "http://localhost:1234,http://127.0.0.1:1234"

    database_url: str = (
        "postgresql+psycopg2://logistics:logistics_dev@127.0.0.1:5435/myanmar_logistics_intel"
    )

    # Qdrant (existing OSINT collection)
    qdrant_url: str = "http://192.168.11.52:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "content"
    qdrant_top_k: int = 8
    # Only use OSINT published within this many calendar days (newest window)
    osint_max_age_days: int = 7

    # Embeddings — must match collection dim (1024). Prefer HTTP; local optional.
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"
    embedding_dim: int = 1024
    embedding_mode: str = "auto"  # auto | http | local | keyword

    # Gemma-e2b (OpenAI-compatible)
    gemma_url: str = "http://127.0.0.1:8004"
    gemma_api_key: str = "0123456789"
    llm_model_gemma: str = "Gemma-SEA-LION-v4.5-E2B-IT"
    gemma_timeout: float = 90.0
    gemma_max_tokens: int = 1024

    # Weather
    weather_provider: str = "stub"  # stub | openweather
    openweather_api_key: str = ""
    openweather_base_url: str = "https://api.openweathermap.org/data/2.5"
    openweather_tile_url: str = "https://tile.openweathermap.org/map"

    # Road routing (OSRM-compatible)
    osrm_url: str = "https://router.project-osrm.org"

    log_level: str = "INFO"
    upload_dir: str = "uploads"
    upload_max_mb: float = 8.0

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
