"""Runtime configuration. Every value can be set with an IVR_-prefixed environment variable."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "synthetic"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="IVR_", extra="ignore")

    env: Literal["local", "test", "dev", "staging", "prod"] = "local"
    log_level: str = "INFO"
    data_dir: Path = DEFAULT_DATA_DIR

    # API protection for the /v1 JSON API (simulator, test harnesses, other services).
    api_key: SecretStr = SecretStr("change-me-local-only")

    # NLU provider. "rules" is deterministic and free; LLM providers fall back to rules on failure.
    nlu_provider: Literal["rules", "openai_compatible", "bedrock"] = "rules"
    llm_base_url: str = "http://localhost:11434/v1"  # Ollama's OpenAI-compatible endpoint
    llm_model: str = "llama3.1:8b"
    llm_api_key: SecretStr = SecretStr("")
    llm_timeout_s: float = Field(default=4.0, gt=0, le=30)
    llm_min_confidence: float = Field(default=0.5, ge=0, le=1)
    bedrock_model_id: str = ""  # set to a model ID enabled in your AWS account
    aws_region: str = "us-east-1"

    # Conversation policy.
    max_auth_attempts: int = Field(default=3, ge=1, le=5)
    max_no_match: int = Field(default=3, ge=1, le=5)
    session_ttl_s: int = Field(default=1800, ge=60)

    # Twilio voice channel.
    twilio_auth_token: SecretStr = SecretStr("")
    twilio_validate_signature: bool = False
    public_base_url: str = ""  # e.g. https://abc123.ngrok.app — used to rebuild signed URLs
    tts_voice: str = "Polly.Joanna"

    # Observability.
    otel_console_exporter: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
