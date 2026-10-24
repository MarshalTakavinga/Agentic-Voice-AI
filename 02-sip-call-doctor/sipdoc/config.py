from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SIPDOC_", extra="ignore")

    env: Literal["local", "test", "dev", "staging", "prod"] = "local"
    log_level: str = "INFO"
    api_key: SecretStr = SecretStr("change-me-local-only")
    max_upload_mb: int = Field(default=20, ge=1, le=200)
    max_stored_analyses: int = Field(default=100, ge=1, le=10_000)

    # template (deterministic, default) | openai_compatible (Ollama, vLLM, OpenAI)
    narrator: Literal["template", "openai_compatible"] = "template"
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "llama3.1:8b"
    llm_api_key: SecretStr = SecretStr("")
    llm_timeout_s: float = Field(default=8.0, gt=0, le=60)


@lru_cache
def get_settings() -> Settings:
    return Settings()
