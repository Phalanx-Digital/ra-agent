from __future__ import annotations

from abc import ABC, abstractmethod

import httpx


class AgentAdapter(ABC):
    @abstractmethod
    async def run(self, transcript: str, session_id: str, turn_id: str) -> dict:
        """Return tool results and memory context, never a user-facing final answer."""


class NoopAgent(AgentAdapter):
    async def run(self, transcript: str, session_id: str, turn_id: str) -> dict:
        return {"tool_results": [], "memory": [], "agent": "noop"}


class OpenAICompatibleAgent(AgentAdapter):
    """Adapter for Hermes/OpenClaw gateways exposing /v1/chat/completions."""

    def __init__(self, base_url: str, model: str, api_key: str, timeout_s: float = 120) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_s = timeout_s

    async def run(self, transcript: str, session_id: str, turn_id: str) -> dict:
        prompt = (
            "You are the tool-execution layer. Execute or propose only tools needed for the "
            "request. Return concise JSON context for a separate conversational model.\n"
            f"User transcript: {transcript}"
        )
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            response = await client.post(
                f"{self.base_url}/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        return {"agent": "openai-compatible", "raw_context": content}


def build_agent(config: dict) -> AgentAdapter:
    import os

    if config.get("type", "noop") == "noop":
        return NoopAgent()
    return OpenAICompatibleAgent(
        base_url=config["base_url"],
        model=config["model"],
        api_key=os.getenv(config.get("api_key_env", "AURA_AGENT_API_KEY"), "not-required"),
        timeout_s=config.get("timeout_s", 120),
    )

