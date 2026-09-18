from __future__ import annotations

import os
from abc import ABC, abstractmethod

import httpx


class TextToSpeech(ABC):
    content_type = "audio/wav"

    @abstractmethod
    async def synthesize(self, text: str, emotion: str = "neutral") -> bytes: ...


class FishSpeechHTTP(TextToSpeech):
    """Fish Speech HTTP adapter; endpoint shape can be overridden in config."""

    def __init__(self, config: dict) -> None:
        self.url = config["url"]
        self.reference_id = config.get("reference_id")
        self.format = config.get("format", "wav")
        self.content_type = f"audio/{self.format}"
        self.timeout_s = config.get("timeout_s", 120)
        self.token = os.getenv(config.get("api_key_env", "AURA_OPENAI_API_KEY"), "not-required")

    async def synthesize(self, text: str, emotion: str = "neutral") -> bytes:
        payload = {
            "text": text,
            "format": self.format,
            "reference_id": self.reference_id,
            "emotion": emotion,
            "streaming": False,
        }
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            response = await client.post(
                self.url, headers={"Authorization": f"Bearer {self.token}"}, json=payload
            )
            response.raise_for_status()
            return response.content


class OpenAICompatibleTTS(TextToSpeech):
    def __init__(self, config: dict) -> None:
        self.url = f"{config['base_url'].rstrip('/')}/v1/audio/speech"
        self.model = config["model"]
        self.voice = config.get("voice", "alloy")
        self.format = config.get("format", "wav")
        self.content_type = f"audio/{self.format}"
        self.token = os.getenv(config.get("api_key_env", "AURA_OPENAI_API_KEY"), "not-required")

    async def synthesize(self, text: str, emotion: str = "neutral") -> bytes:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                self.url,
                headers={"Authorization": f"Bearer {self.token}"},
                json={"model": self.model, "voice": self.voice, "input": text, "format": self.format},
            )
            response.raise_for_status()
            return response.content


def build_tts(config: dict) -> TextToSpeech:
    if config.get("type") == "fish-speech-http":
        return FishSpeechHTTP(config)
    return OpenAICompatibleTTS(config)

