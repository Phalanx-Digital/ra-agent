from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import os
import re
from dataclasses import dataclass

from websockets.asyncio.server import ServerConnection, serve

from aura_link.config import load_yaml
from aura_link.metrics import TurnMetrics
from aura_link.protocol import Envelope, EventType, b64decode, b64encode
from aura_link.security import bearer_from_headers, constant_time_token_valid, server_ssl_context
from server.adapters.lipsync import EnergyLipSync
from server.adapters.stt import SpeechToText, build_stt
from server.adapters.tts import TextToSpeech, build_tts
from server.adapters.vision import VisionLanguageModel, build_vision

LOG = logging.getLogger("aura.inference")
SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


@dataclass
class PendingTurn:
    bundle: dict
    metrics: TurnMetrics


class InferencePipeline:
    def __init__(self, config_path: str) -> None:
        raw = load_yaml(config_path)
        self.host = raw.get("host", "0.0.0.0")
        self.port = int(raw.get("port", 9000))
        self.token = os.environ[raw.get("token_env", "AURA_INFERENCE_TOKEN")]
        self.stt: SpeechToText = build_stt(raw["stt"])
        self.vision: VisionLanguageModel = build_vision(raw["vision"])
        self.tts: TextToSpeech = build_tts(raw["tts"])
        self.lipsync = EnergyLipSync()
        self.pending: dict[str, PendingTurn] = {}
        self.tasks: dict[str, asyncio.Task] = {}
        self.thinking_delay_s = float(raw.get("behavior", {}).get("thinking_cue_after_s", 1.2))
        tls = raw.get("tls", {})
        self.ssl_context = (
            server_ssl_context(tls["cert_file"], tls["key_file"]) if tls.get("enabled") else None
        )

    async def authenticate(self, connection: ServerConnection, _request: object):
        provided = bearer_from_headers(connection.request.headers)
        if constant_time_token_valid(provided, self.token):
            return None
        return connection.respond(401, "Unauthorized\n")

    async def handle(self, socket: ServerConnection) -> None:
        async for raw in socket:
            event = Envelope.loads(raw)
            if event.type == EventType.HELLO:
                await socket.send(
                    Envelope(type=EventType.READY, session_id=event.session_id).dumps()
                )
            elif event.type == EventType.INPUT_BUNDLE:
                task = asyncio.create_task(self._transcribe(socket, event))
                self.tasks[event.turn_id or ""] = task
            elif event.type == EventType.AGENT_CONTEXT:
                task = asyncio.create_task(self._respond(socket, event))
                self.tasks[event.turn_id or ""] = task
            elif event.type == EventType.CANCEL:
                task = self.tasks.pop(event.turn_id or "", None)
                if task:
                    task.cancel()
                self.pending.pop(event.turn_id or "", None)

    async def _transcribe(self, socket: object, event: Envelope) -> None:
        if not event.turn_id:
            return
        metrics = TurnMetrics()
        self.pending[event.turn_id] = PendingTurn(event.payload, metrics)
        try:
            text = await self.stt.transcribe(b64decode(event.payload["audio_wav_b64"]))
            metrics.mark("stt_final")
            await socket.send(
                Envelope(
                    type=EventType.TRANSCRIPT_FINAL,
                    session_id=event.session_id,
                    turn_id=event.turn_id,
                    payload={"text": text, "latency_ms": metrics.snapshot()},
                ).dumps()
            )
        except Exception as exc:
            await self._send_error(socket, event, "stt_failed", exc)

    async def _respond(self, socket: object, event: Envelope) -> None:
        if not event.turn_id or event.turn_id not in self.pending:
            return
        turn = self.pending[event.turn_id]
        cue_task = asyncio.create_task(self._thinking_cue(socket, event))
        sequence = 0
        buffer = ""
        full_text = ""
        try:
            stream = self.vision.stream(
                event.payload.get("transcript", ""),
                turn.bundle["screen_jpeg_b64"],
                turn.bundle.get("webcam_jpeg_b64"),
                event.payload.get("context", {}),
            )
            async for delta in stream:
                if not full_text:
                    turn.metrics.mark("first_text_token")
                    cue_task.cancel()
                full_text += delta
                buffer += delta
                await socket.send(
                    Envelope(
                        type=EventType.TEXT_DELTA,
                        session_id=event.session_id,
                        turn_id=event.turn_id,
                        sequence=sequence,
                        payload={"text": delta},
                    ).dumps()
                )
                sequence += 1
                sentences = SENTENCE_END.split(buffer)
                buffer = sentences.pop() if sentences else buffer
                for sentence in sentences:
                    if sentence.strip():
                        sequence = await self._speak(socket, event, sentence.strip(), sequence)
            if buffer.strip():
                sequence = await self._speak(socket, event, buffer.strip(), sequence)
            turn.metrics.mark("completed")
            await socket.send(
                Envelope(
                    type=EventType.RESPONSE_DONE,
                    session_id=event.session_id,
                    turn_id=event.turn_id,
                    sequence=sequence,
                    payload={"text": full_text, "latency_ms": turn.metrics.snapshot()},
                ).dumps()
            )
        except asyncio.CancelledError:
            cue_task.cancel()
            raise
        except Exception as exc:
            cue_task.cancel()
            await self._send_error(socket, event, "response_failed", exc)
        finally:
            self.pending.pop(event.turn_id, None)
            self.tasks.pop(event.turn_id, None)

    async def _speak(self, socket: object, event: Envelope, text: str, sequence: int) -> int:
        audio = await self.tts.synthesize(text)
        motion = self.lipsync.analyze(audio)
        await socket.send(
            Envelope(
                type=EventType.AUDIO_CHUNK,
                session_id=event.session_id,
                turn_id=event.turn_id,
                sequence=sequence,
                payload={"audio_b64": b64encode(audio), "mime": self.tts.content_type, "text": text},
            ).dumps()
        )
        await socket.send(
            Envelope(
                type=EventType.AVATAR_MOTION,
                session_id=event.session_id,
                turn_id=event.turn_id,
                sequence=sequence,
                payload={"expression": "speaking", "blendshapes": motion},
            ).dumps()
        )
        return sequence + 1

    async def _thinking_cue(self, socket: object, event: Envelope) -> None:
        await asyncio.sleep(self.thinking_delay_s)
        await socket.send(
            Envelope(
                type=EventType.THINKING_CUE,
                session_id=event.session_id,
                turn_id=event.turn_id,
                payload={"cue": "wait_natural", "text": "Hmm, tunggu sebentar ya…"},
            ).dumps()
        )

    async def _send_error(self, socket: object, event: Envelope, code: str, exc: Exception) -> None:
        LOG.exception("%s turn=%s", code, event.turn_id)
        await socket.send(
            Envelope(
                type=EventType.ERROR,
                session_id=event.session_id,
                turn_id=event.turn_id,
                payload={"code": code, "message": str(exc), "retryable": True},
            ).dumps()
        )

    async def run(self) -> None:
        async with serve(
            self.handle,
            self.host,
            self.port,
            ssl=self.ssl_context,
            process_request=self.authenticate,
            max_size=32 * 1024 * 1024,
            ping_interval=20,
        ):
            LOG.info("Inference pipeline listening on %s:%s", self.host, self.port)
            await asyncio.Future()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="server/config.yaml")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(InferencePipeline(args.config).run())


if __name__ == "__main__":
    main()

