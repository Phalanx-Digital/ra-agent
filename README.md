# Aura-Link

Aura-Link is an open-source framework for connecting a Windows desktop avatar,
an Ubuntu agent/tool router, and a remote GPU inference node. It is designed for
always-listening multimodal assistants while keeping model and agent vendors
replaceable through explicit adapters and OpenAI-compatible APIs.

> Status: **v0.1.0 foundation**. The protocol and services are runnable
> boilerplate. A production VRM renderer, native MuseTalk bridge, signed Windows
> installer, and sub-600 ms tuning are roadmap work—not falsely claimed as complete.

## What exists in v0.1.0

- Silero VAD microphone turns with 0.8-second configurable endpointing.
- Screen and webcam capture only after a completed speech turn.
- Authenticated bidirectional WSS transport with reconnect and keepalive.
- Barge-in cancellation when the user speaks during an active response.
- Router boundary for Hermes, OpenClaw or another OpenAI-compatible agent.
- Faster-Whisper or OpenAI-compatible STT adapter.
- OpenAI-compatible multimodal VLM adapter (Qwen via vLLM/SGLang/Ollama).
- Fish Speech HTTP or OpenAI-compatible TTS adapter.
- Sentence-level streamed TTS and portable VRM mouth-weight fallback.
- Frameless, translucent, always-on-top PyQt6 avatar shell.
- Per-turn latency marks and natural thinking-cue events.

## Repository map

```text
aura_link/                 Shared protocol, config, security, metrics
client/
  local_daemon.py          VAD + screen/webcam capture + WSS client
  overlay_app.py           Transparent Windows avatar shell
router/
  gateway.py               Ubuntu WSS router/orchestrator
  agent_adapter.py         Hermes/OpenClaw adapter boundary
server/
  inference_pipeline.py    STT → agent context → VLM → TTS → motion
  adapters/                Swappable STT, VLM, TTS and lip-sync backends
  config.yaml              Vast.ai/model/voice configuration
configs/                   Client and router examples
docker/                    Router and CUDA inference images
docs/                      Architecture and protocol contracts
tests/                     Protocol and security tests
```

See [Architecture](docs/ARCHITECTURE.md), [Protocol](docs/PROTOCOL.md), and
[Changelog](CHANGELOG.md).

## 1. Prerequisites

- Python 3.11 or 3.12.
- Windows 10/11 client with microphone and optional webcam.
- Ubuntu 22.04+ router host reachable from the client.
- NVIDIA GPU node/Vast.ai pod for local Whisper, Qwen and Fish Speech.
- TLS certificates whose hostnames match both WSS endpoints.

For local-only development, OpenSSL scripts in `scripts/` create a short-lived
self-signed certificate. Use Let's Encrypt, Caddy, Traefik or your platform's
managed certificate for public deployments.

## 2. Install

```bash
git clone https://github.com/Phalanx-Digital/ra-agent.git
cd ra-agent
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
pip install -e ".[client,dev]"
Copy-Item .env.example .env
```

Ubuntu router:

```bash
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
```

GPU inference node:

```bash
source .venv/bin/activate
pip install -e '.[server,dev]'
cp .env.example .env
```

Generate separate random secrets for client→router and router→GPU. Never reuse
the example values or commit `.env`.

## 3. Configure backends

Edit `server/config.yaml`:

- `stt.type: faster-whisper` loads a local model; use `openai-compatible` for
  another STT server.
- `vision.base_url` points to the `/v1` parent of Qwen-VL served by vLLM,
  SGLang, Ollama or another compatible service.
- `tts.type: fish-speech-http` calls a Fish Speech server. Change its URL and
  reference voice ID to match the Fish Speech deployment.
- `lipsync.type: energy-vrm` produces basic mouth weights. The documented
  `musetalk-http` entry is a future adapter, not active code in v0.1.0.

Edit `configs/router.yaml` to point at the GPU WSS URL. Set `agent.type` to
`openai-compatible` when Hermes/OpenClaw exposes a compatible gateway, or leave
it as `noop` while developing the voice/vision path.

Edit `configs/client.yaml` with the public Ubuntu router URL and capture device
IDs. The default monitor value `0` means the combined virtual desktop in `mss`.

## 4. Run

Inference/Vast.ai node:

```bash
export AURA_INFERENCE_TOKEN='your-inference-secret'
export AURA_OPENAI_API_KEY='not-required-for-local'
python -m server.inference_pipeline --config server/config.yaml
```

Ubuntu router:

```bash
export AURA_ROUTER_TOKEN='your-client-secret'
export AURA_INFERENCE_TOKEN='your-inference-secret'
python -m router.gateway --config configs/router.yaml
```

Windows client (two terminals):

```powershell
$env:AURA_ROUTER_TOKEN = "your-client-secret"
python -m client.local_daemon --config configs/client.yaml
python -m client.overlay_app
```

The v0.1.0 overlay is a renderer shell/diagnostic avatar. Wiring its local IPC
audio player to daemon events and loading VRM/WebGL assets are explicit next
milestones.

## 5. TLS and public ports

Expose only `8765/tcp` on the Ubuntu router and `9000/tcp` on the GPU pod. Use
WSS end-to-end. Restrict the GPU port to the router IP when Vast.ai/network
controls permit it. Recommended production hardening:

1. Put Caddy or Traefik in front of each service for certificate renewal.
2. Store tokens in systemd credentials or a secret manager.
3. Rotate both tokens independently and rate-limit connection attempts.
4. Add explicit screen/webcam permission toggles before distributing binaries.
5. Avoid retaining raw camera, screen or voice data unless the user opts in.

## 6. Docker

Run only the router by default:

```bash
docker compose up --build router
```

Run the inference profile on a configured NVIDIA host:

```bash
docker compose --profile gpu up --build inference
```

Model servers such as vLLM and Fish Speech remain separate processes/containers;
their endpoints are declared in `server/config.yaml`.

## 7. Tests and contribution workflow

```bash
pip install -e '.[dev]'
pytest
ruff check .
```

Open an issue before changing the protocol. New backends should implement one
adapter interface without importing vendor code into the shared protocol. Add a
changelog entry and tests for every behavior change. Security reports should not
be posted publicly until a private disclosure channel is published.

## Honest limitations

- MuseTalk commonly generates facial video, not universal VRM blendshape arrays;
  the framework therefore provides a neutral motion contract and an energy-based
  fallback instead of pretending both formats are identical.
- Base64 JSON is easy to inspect but adds bandwidth and allocation overhead.
  Binary frames/WebRTC are planned for production latency.
- “Always listening” must remain visible, user-controlled and privacy-aware.
- Whole-body gesture synthesis and screen-target gaze require a renderer-specific
  IK/motion policy and are not completed in this foundation release.
- `<600 ms` depends on model size, quantization, warm state, geographic RTT and
  TTS chunking. The included metrics make regressions measurable.

## License

Apache License 2.0. See [LICENSE](LICENSE).

