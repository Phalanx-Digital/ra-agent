from __future__ import annotations

import asyncio
import io
import wave
from collections.abc import AsyncIterator

import numpy as np
import sounddevice as sd


class SileroTurnDetector:
    """Turns 16 kHz microphone frames into utterance WAVs using Silero VAD."""

    def __init__(
        self,
        sample_rate: int = 16_000,
        frame_samples: int = 512,
        silence_seconds: float = 0.8,
        threshold: float = 0.5,
    ) -> None:
        from silero_vad import VADIterator, load_silero_vad

        self.sample_rate = sample_rate
        self.frame_samples = frame_samples
        self.silence_frames = max(1, int(silence_seconds * sample_rate / frame_samples))
        self.model = load_silero_vad()
        self.iterator = VADIterator(
            self.model, threshold=threshold, sampling_rate=sample_rate, min_silence_duration_ms=100
        )

    async def utterances(self) -> AsyncIterator[bytes]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=128)

        def callback(indata: np.ndarray, _frames: int, _time: object, status: object) -> None:
            if status:
                return
            raw = indata[:, 0].copy().tobytes()
            loop.call_soon_threadsafe(self._enqueue, queue, raw)

        recording: list[bytes] = []
        speaking = False
        silent = 0
        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
            blocksize=self.frame_samples,
            callback=callback,
        ):
            while True:
                raw = await queue.get()
                samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                event = self.iterator(samples, return_seconds=False)
                if event and "start" in event:
                    speaking = True
                    recording = [raw]
                    silent = 0
                    yield b"__speech_started__"
                    continue
                if not speaking:
                    continue
                recording.append(raw)
                if event and "end" in event:
                    silent += 1
                elif float(np.abs(samples).mean()) < 0.008:
                    silent += 1
                else:
                    silent = 0
                if silent >= self.silence_frames:
                    yield self._to_wav(b"".join(recording))
                    recording, speaking, silent = [], False, 0
                    self.iterator.reset_states()

    @staticmethod
    def _enqueue(queue: asyncio.Queue[bytes], raw: bytes) -> None:
        if not queue.full():
            queue.put_nowait(raw)

    def _to_wav(self, pcm: bytes) -> bytes:
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self.sample_rate)
            wav.writeframes(pcm)
        return output.getvalue()

