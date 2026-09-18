from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class EndpointConfig(BaseModel):
    url: str
    token_env: str
    connect_timeout_s: float = 10
    max_message_mb: int = 24

    def token(self) -> str:
        value = os.getenv(self.token_env, "")
        if not value:
            raise RuntimeError(f"Environment variable {self.token_env} is required")
        return value


class OpenAIBackend(BaseModel):
    base_url: str
    api_key_env: str = "AURA_OPENAI_API_KEY"
    model: str
    timeout_s: float = 90
    extra_body: dict[str, Any] = Field(default_factory=dict)

    def api_key(self) -> str:
        return os.getenv(self.api_key_env, "not-required")


def load_yaml(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle) or {}
    if not isinstance(value, dict):
        raise ValueError(f"Configuration root must be a mapping: {config_path}")
    return value

