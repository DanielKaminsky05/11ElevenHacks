"""Typed, validated configuration loaded from environment / .env.

Misconfiguration fails fast at startup rather than at first request.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="TRANSITRL_",
        extra="ignore",
    )

    # Server
    api_host: str = "0.0.0.0"
    api_port: int = 9000

    # CORS — the frontend runs on the laptop, a different origin than this host.
    allowed_origins: list[str] = ["http://localhost:3000"]

    # Nemotron NIM (OpenAI-compatible). localhost when co-located on the Spark.
    nim_base_url: str = "http://localhost:8000/v1"
    nim_model: str = "nvidia/llama-3.1-nemotron-70b-instruct"
    # When True, model-calling tools use FakeNIMClient (no model) so the app runs
    # end-to-end on a laptop. Set False on the Spark to use the real Nemotron.
    nim_offline: bool = False

    # City grid
    data_dir: str = "../data"
    grid_resolution: int = 30


@lru_cache
def get_settings() -> Settings:
    """Cached so Settings is constructed once and is injectable via Depends."""
    return Settings()
