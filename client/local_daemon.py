from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import ssl

from websockets.asyncio.client import connect
from websockets.asyncio.server import ServerConnection, serve

from aura_link.config import EndpointConfig, load_yaml
from aura_link.protocol import Envelope, EventType, b64encode, new_id
from aura_link.security import client_ssl_context
from client.audio import SileroTurnDetector
from client.capture import capture_screen, capture_webcam

LOG = logging.getLogger("aura.client")


class LocalDaemon:
    def __init__(self, config_path: str) -> None:
        raw = load_yaml(config_path)
        self.endpoint = EndpointConfig.model_validate(raw["router"])
        self.capture = raw.get("capture", {})
        self.vad = SileroTurnDetector(**raw.get("vad", {}))
        self.session_id = new_id("session")
        self.outbox: asyncio.Queue[Envelope] = asyncio.Queue(maxsize=32)
        self.current_turn: str | None = None
        self.ca_file = raw.get("tls", {}).get("ca_file")
        overlay = raw.get("overlay_bridge", {})
        self.overlay_host = overlay.get("host", "127.0.0.1")
        self.overlay_port = int(overlay.get("port", 18765))
        self.overlay_clients: set[ServerConnection] = set()

    async def run_forever(self) -> None:
        backoff = 1.0
        while True:
            try:
                async with serve(self._overlay_client, self.overlay_host, self.overlay_port):
                    LOG.info("Overlay bridge listening on ws://%s:%s", self.overlay_host, self.overlay_port)
                    await self._run_session()
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception:
                LOG.exception("Router connection failed; retrying in %.1fs", backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    async def _run_session(self) -> None:
        tls: ssl.SSLContext | None = None
        if self.endpoint.url.startswith("wss://"):
            tls = client_ssl_context(self.ca_file)
        headers = {"Authorization": f"Bearer {self.endpoint.token()}"}
        async with connect(
            self.endpoint.url,
            ssl=tls,
            additional_headers=headers,
            max_size=self.endpoint.max_message_mb * 1024 * 1024,
            open_timeout=self.endpoint.connect_timeout_s,
            ping_interval=20,
        ) as socket:
            await socket.send(Envelope(type=EventType.HELLO, session_id=self.session_id).dumps())
            async with asyncio.TaskGroup() as tasks:
                tasks.create_task(self._capture_loop())
                tasks.create_task(self._send_loop(socket))
                tasks.create_task(self._receive_loop(socket))

    async def _capture_loop(self) -> None:
        async for wav in self.vad.utterances():
            if wav == b"__speech_started__":
                if self.current_turn:
                    cancel = Envelope(
                        type=EventType.CANCEL,
                        session_id=self.session_id,
                        turn_id=self.current_turn,
                        payload={"reason": "barge_in"},
                    )
                    await self.outbox.put(cancel)
                    await self._broadcast_overlay(cancel.dumps())
                continue
            self.current_turn = new_id("turn")
            screen_task = asyncio.to_thread(
                capture_screen,
                self.capture.get("monitor", 0),
                self.capture.get("screen_max_width", 1600),
            )
            webcam_task = asyncio.to_thread(
                capture_webcam,
                self.capture.get("webcam_device", 0),
                self.capture.get("webcam_max_width", 640),
            )
            screen, webcam = await asyncio.gather(screen_task, webcam_task)
            await self.outbox.put(
                Envelope(
                    type=EventType.INPUT_BUNDLE,
                    session_id=self.session_id,
                    turn_id=self.current_turn,
                    payload={
                        "audio_wav_b64": b64encode(wav),
                        "screen_jpeg_b64": b64encode(screen),
                        "webcam_jpeg_b64": b64encode(webcam) if webcam else None,
                        "mime": {"audio": "audio/wav", "screen": "image/jpeg", "webcam": "image/jpeg"},
                    },
                )
            )

    async def _send_loop(self, socket: object) -> None:
        while True:
            event = await self.outbox.get()
            await socket.send(event.dumps())

    async def _receive_loop(self, socket: object) -> None:
        async for raw in socket:
            event = Envelope.loads(raw)
            LOG.info("event=%s turn=%s seq=%s", event.type, event.turn_id, event.sequence)
            await self._broadcast_overlay(event.dumps())
            if event.type == EventType.RESPONSE_DONE and event.turn_id == self.current_turn:
                self.current_turn = None

    async def _overlay_client(self, socket: ServerConnection) -> None:
        self.overlay_clients.add(socket)
        try:
            await socket.wait_closed()
        finally:
            self.overlay_clients.discard(socket)

    async def _broadcast_overlay(self, raw: str) -> None:
        clients = tuple(self.overlay_clients)
        if not clients:
            return
        results = await asyncio.gather(
            *(client.send(raw) for client in clients), return_exceptions=True
        )
        for client, result in zip(clients, results, strict=False):
            if isinstance(result, Exception):
                self.overlay_clients.discard(client)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/client.yaml")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(LocalDaemon(args.config).run_forever())


if __name__ == "__main__":
    main()
