"""Configuration management via pydantic-settings."""

import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # LLM
    deepseek_api_key: str = ""
    tavily_api_key: str = ""

    # OBS
    ak: str = ""
    sk: str = ""
    endpoint: str = ""
    bucket_name: str = ""

    # App
    host: str = "0.0.0.0"
    port: int = 5000
    cors_origins: list[str] = ["http://localhost:5173"]

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }
