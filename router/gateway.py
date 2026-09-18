from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import os
import ssl

from websockets.asyncio.client import connect
from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from aura_link.config import EndpointConfig, load_yaml
from aura_link.protocol import Envelope, EventType
from aura_link.security import bearer_from_headers, constant_time_token_valid, server_ssl_context
from router.agent_adapter import AgentAdapter, build_agent

LOG = logging.getLogger("aura.router")


class Gateway:
    def __init__(self, config_path: str) -> None:
        raw = load_yaml(config_path)
        self.host = raw.get("host", "0.0.0.0")
        self.port = int(raw.get("port", 8765))
        self.client_token = os.environ[raw.get("client_token_env", "AURA_ROUTER_TOKEN")]
        self.inference = EndpointConfig.model_validate(raw["inference"])
        self.agent: AgentAdapter = build_agent(raw.get("agent", {}))
        tls = raw.get("tls", {})
        self.ssl_context = (
            server_ssl_context(tls["cert_file"], tls["key_file"]) if tls.get("enabled") else None
        )
        self.inference_ca = tls.get("inference_ca_file")

    async def authenticate(self, connection: ServerConnection, _request: object):
        provided = bearer_from_headers(connection.request.headers)
        if constant_time_token_valid(provided, self.client_token):
            return None
        return connection.respond(401, "Unauthorized\n")

    async def handle_client(self, client: ServerConnection) -> None:
        LOG.info("Client connected remote=%s", client.remote_address)
        headers = {"Authorization": f"Bearer {self.inference.token()}"}
        tls: ssl.SSLContext | None = None
        if self.inference.url.startswith("wss://"):
            tls = ssl.create_default_context(cafile=self.inference_ca)
        try:
            async with connect(
                self.inference.url,
                ssl=tls,
                additional_headers=headers,
                max_size=self.inference.max_message_mb * 1024 * 1024,
            ) as inference:
                async with asyncio.TaskGroup() as tasks:
                    tasks.create_task(self._client_to_inference(client, inference))
                    tasks.create_task(self._inference_to_client(inference, client))
        except ConnectionClosed:
            LOG.info("Client disconnected remote=%s", client.remote_address)

    async def _client_to_inference(self, client: object, inference: object) -> None:
        async for raw in client:
            event = Envelope.loads(raw)
            if event.type in {EventType.INPUT_BUNDLE, EventType.CANCEL, EventType.HELLO}:
                await inference.send(event.dumps())

    async def _inference_to_client(self, inference: object, client: object) -> None:
        async for raw in inference:
            event = Envelope.loads(raw)
            if event.type == EventType.TRANSCRIPT_FINAL:
                transcript = str(event.payload.get("text", ""))
                try:
                    context = await self.agent.run(
                        transcript, event.session_id, event.turn_id or "unknown"
                    )
                except Exception as exc:
                    LOG.exception("Agent adapter failed")
                    context = {"agent_error": type(exc).__name__, "tool_results": []}
                await inference.send(
                    Envelope(
                        type=EventType.AGENT_CONTEXT,
                        session_id=event.session_id,
                        turn_id=event.turn_id,
                        payload={"transcript": transcript, "context": context},
                    ).dumps()
                )
            await client.send(event.dumps())

    async def run(self) -> None:
        async with serve(
            self.handle_client,
            self.host,
            self.port,
            ssl=self.ssl_context,
            process_request=self.authenticate,
            max_size=self.inference.max_message_mb * 1024 * 1024,
            ping_interval=20,
        ):
            LOG.info("Gateway listening on %s:%s", self.host, self.port)
            await asyncio.Future()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/router.yaml")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(Gateway(args.config).run())


if __name__ == "__main__":
    main()

