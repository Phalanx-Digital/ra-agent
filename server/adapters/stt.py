from __future__ import annotations

import asyncio
import os
import tempfile
from abc import ABC, abstractmethod

import httpx


class SpeechToText(ABC):
    @abstractmethod
    async def transcribe(self, wav: bytes) -> str: ...


class FasterWhisperSTT(SpeechToText):
    def __init__(self, model: str, device: str = "cuda", compute_type: str = "float16") -> None:
        from faster_whisper import WhisperModel

        self.model = WhisperModel(model, device=device, compute_type=compute_type)

    async def transcribe(self, wav: bytes) -> str:
        def blocking() -> str:
            with tempfile.NamedTemporaryFile(suffix=".wav") as handle:
                handle.write(wav)
                handle.flush()
                segments, _ = self.model.transcribe(handle.name, vad_filter=False, beam_size=1)
                return " ".join(segment.text.strip() for segment in segments).strip()

        return await asyncio.to_thread(blocking)


class OpenAICompatibleSTT(SpeechToText):
    def __init__(self, base_url: str, model: str, api_key_env: str, timeout_s: float = 60) -> None:
        self.url = f"{base_url.rstrip('/')}/v1/audio/transcriptions"
        self.model = model
        self.api_key = os.getenv(api_key_env, "not-required")
        self.timeout_s = timeout_s

    async def transcribe(self, wav: bytes) -> str:
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            response = await client.post(
                self.url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                data={"model": self.model},
                files={"file": ("speech.wav", wav, "audio/wav")},
            )
            response.raise_for_status()
            return response.json()["text"].strip()


def build_stt(config: dict) -> SpeechToText:
    if config.get("type") == "faster-whisper":
        return FasterWhisperSTT(
            config["model"], config.get("device", "cuda"), config.get("compute_type", "float16")
        )
    return OpenAICompatibleSTT(
        config["base_url"], config["model"], config.get("api_key_env", "AURA_OPENAI_API_KEY")
    )

