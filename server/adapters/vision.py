from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

import httpx


class VisionLanguageModel(ABC):
    @abstractmethod
    async def stream(
        self, transcript: str, screen_b64: str, webcam_b64: str | None, agent_context: dict
    ) -> AsyncIterator[str]: ...


class OpenAICompatibleVision(VisionLanguageModel):
    def __init__(self, config: dict) -> None:
        self.url = f"{config['base_url'].rstrip('/')}/v1/chat/completions"
        self.model = config["model"]
        self.api_key = os.getenv(config.get("api_key_env", "AURA_OPENAI_API_KEY"), "not-required")
        self.timeout_s = config.get("timeout_s", 120)
        self.system_prompt = config.get(
            "system_prompt",
            "You are a warm desktop companion. Be concise, natural, emotionally expressive, and honest.",
        )
        self.extra_body = config.get("extra_body", {})

    async def stream(
        self, transcript: str, screen_b64: str, webcam_b64: str | None, agent_context: dict
    ) -> AsyncIterator[str]:
        content: list[dict] = [
            {"type": "text", "text": f"User said: {transcript}\nTool context: {json.dumps(agent_context)}"},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{screen_b64}"}},
        ]
        if webcam_b64:
            content.append(
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{webcam_b64}"}}
            )
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": content},
            ],
            "stream": True,
            "temperature": 0.7,
            **self.extra_body,
        }
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            async with client.stream(
                "POST", self.url, headers={"Authorization": f"Bearer {self.api_key}"}, json=body
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: ") or line == "data: [DONE]":
                        continue
                    data = json.loads(line[6:])
                    delta = data.get("choices", [{}])[0].get("delta", {}).get("content")
                    if delta:
                        yield delta


def build_vision(config: dict) -> VisionLanguageModel:
    return OpenAICompatibleVision(config)

