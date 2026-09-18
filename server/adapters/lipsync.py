from __future__ import annotations

import io
import wave

import numpy as np


class EnergyLipSync:
    """Portable fallback emitting VRM-style mouth weights from PCM energy.

    Replace with a MuseTalk/Linly adapter when the deployment exposes native
    blendshapes. MuseTalk normally renders face frames rather than VRM weights.
    """

    def analyze(self, audio: bytes, fps: int = 30) -> list[dict[str, float]]:
        try:
            with wave.open(io.BytesIO(audio), "rb") as source:
                rate = source.getframerate()
                channels = source.getnchannels()
                samples = np.frombuffer(source.readframes(source.getnframes()), dtype=np.int16)
        except (wave.Error, EOFError):
            return []
        if channels > 1:
            samples = samples.reshape(-1, channels).mean(axis=1)
        window = max(1, rate // fps)
        frames = []
        for offset in range(0, len(samples), window):
            chunk = samples[offset : offset + window].astype(np.float32) / 32768.0
            energy = min(1.0, float(np.sqrt(np.mean(chunk * chunk))) * 7) if len(chunk) else 0.0
            frames.append({"t_ms": len(frames) * 1000 / fps, "aa": energy, "ih": energy * 0.35})
        return frames

