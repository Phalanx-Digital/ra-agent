# WebSocket protocol 1.0

Every message is a JSON `Envelope` containing `type`, `session_id`, optional
`turn_id`, `sequence`, `timestamp_ms`, `protocol_version`, and `payload`.

| Event | Direction | Purpose |
|---|---|---|
| `input.bundle` | Client → GPU | WAV, screenshot and optional webcam frame |
| `transcript.final` | GPU → Router/client | Final STT result |
| `agent.context` | Router → GPU | Tool results and memory context |
| `response.text.delta` | GPU → Client | Incremental assistant text |
| `response.audio.chunk` | GPU → Client | Ordered audio chunk |
| `avatar.motion` | GPU → Client | Expression and blendshape timeline |
| `response.thinking_cue` | GPU → Client | Natural latency filler cue |
| `response.cancel` | Client → pipeline | Barge-in cancellation |
| `response.completed` | GPU → Client | Turn completion and latency marks |

JSON/base64 is intentionally used for the bootstrap release. For production,
keep the control envelope and move audio/video payloads to binary frames or
WebRTC to reduce encoding overhead and memory copies.

