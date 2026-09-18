from __future__ import annotations

import base64
import json
import time
import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


PROTOCOL_VERSION = "1.0"


class EventType(StrEnum):
    HELLO = "session.hello"
    READY = "session.ready"
    INPUT_BUNDLE = "input.bundle"
    TRANSCRIPT_FINAL = "transcript.final"
    AGENT_CONTEXT = "agent.context"
    TEXT_DELTA = "response.text.delta"
    AUDIO_CHUNK = "response.audio.chunk"
    AVATAR_MOTION = "avatar.motion"
    THINKING_CUE = "response.thinking_cue"
    RESPONSE_DONE = "response.completed"
    CANCEL = "response.cancel"
    ERROR = "error"
    PING = "ping"
    PONG = "pong"


class Envelope(BaseModel):
    type: EventType
    session_id: str
    turn_id: str | None = None
    sequence: int = 0
    timestamp_ms: int = Field(default_factory=lambda: int(time.time() * 1000))
    payload: dict[str, Any] = Field(default_factory=dict)
    protocol_version: str = PROTOCOL_VERSION

    def dumps(self) -> str:
        return self.model_dump_json()

    @classmethod
    def loads(cls, raw: str | bytes) -> "Envelope":
        return cls.model_validate_json(raw)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def b64encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def b64decode(data: str) -> bytes:
    return base64.b64decode(data.encode("ascii"), validate=True)


def json_size(event: Envelope) -> int:
    return len(json.dumps(event.model_dump(mode="json"), separators=(",", ":")))

