from __future__ import annotations

import argparse
import asyncio
import base64
import math
import os
import sys
import tempfile

from PyQt6.QtCore import QPointF, Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import QApplication, QWidget
from websockets.asyncio.client import connect

from aura_link.protocol import Envelope, EventType


class EventWorker(QThread):
    event_received = pyqtSignal(str)

    def __init__(self, url: str) -> None:
        super().__init__()
        self.url = url

    def run(self) -> None:
        asyncio.run(self._listen())

    async def _listen(self) -> None:
        while not self.isInterruptionRequested():
            try:
                async with connect(self.url, ping_interval=20) as socket:
                    while not self.isInterruptionRequested():
                        try:
                            raw = await asyncio.wait_for(socket.recv(), timeout=0.5)
                        except TimeoutError:
                            continue
                        self.event_received.emit(raw)
            except Exception:
                await asyncio.sleep(1)


class AudioQueue:
    def __init__(self, parent: QWidget) -> None:
        self.output = QAudioOutput(parent)
        self.player = QMediaPlayer(parent)
        self.player.setAudioOutput(self.output)
        self.player.mediaStatusChanged.connect(self._status_changed)
        self.queue: list[tuple[bytes, str]] = []
        self.current_path: str | None = None

    def enqueue(self, audio: bytes, mime: str) -> None:
        self.queue.append((audio, mime))
        if self.player.playbackState() == QMediaPlayer.PlaybackState.StoppedState:
            self._play_next()

    def stop(self) -> None:
        self.queue.clear()
        self.player.stop()
        self._remove_current()

    def _status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if status in {
            QMediaPlayer.MediaStatus.EndOfMedia,
            QMediaPlayer.MediaStatus.InvalidMedia,
        }:
            self._remove_current()
            self._play_next()

    def _play_next(self) -> None:
        if not self.queue:
            return
        audio, mime = self.queue.pop(0)
        suffix = ".wav" if "wav" in mime else ".mp3"
        handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        handle.write(audio)
        handle.close()
        self.current_path = handle.name
        self.player.setSource(QUrl.fromLocalFile(handle.name))
        self.player.play()

    def _remove_current(self) -> None:
        if self.current_path:
            try:
                os.unlink(self.current_path)
            except OSError:
                pass
            self.current_path = None


class AvatarOverlay(QWidget):
    """Transparent event-driven shell; replace painting with VRM/WebGL rendering."""

    def __init__(self, bridge_url: str) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.resize(360, 560)
        self.phase = 0.0
        self.expression = "idle"
        self.expression_score = 0.0
        self.gesture = "idle_breathing"
        self.gaze_target = "user"
        self.mouth = 0.0
        self.audio = AudioQueue(self)
        self.worker = EventWorker(bridge_url)
        self.worker.event_received.connect(self.apply_event)
        self.worker.start()
        timer = QTimer(self)
        timer.timeout.connect(self._animate)
        timer.start(16)

    def closeEvent(self, event: object) -> None:
        self.worker.requestInterruption()
        self.worker.wait(1500)
        self.audio.stop()
        event.accept()

    def apply_event(self, raw: str) -> None:
        event = Envelope.loads(raw)
        if event.type == EventType.CANCEL:
            self.audio.stop()
            self.mouth = 0.0
        elif event.type == EventType.AUDIO_CHUNK:
            self.audio.enqueue(
                base64.b64decode(event.payload["audio_b64"]),
                event.payload.get("mime", "audio/wav"),
            )
        elif event.type == EventType.AVATAR_MOTION:
            self.expression = event.payload.get("expression", "speaking")
            self.expression_score = float(event.payload.get("expression_score", 0.5))
            self.gesture = event.payload.get("gesture", "conversational")
            self.gaze_target = event.payload.get("gaze_target", "user")
            frames = event.payload.get("blendshapes", [])
            if frames:
                self.mouth = float(frames[0].get("aa", 0.0))
        elif event.type == EventType.RESPONSE_DONE:
            self.expression, self.gesture, self.mouth = "idle", "idle_breathing", 0.0

    def _animate(self) -> None:
        self.phase += 0.06
        if self.expression in {"speaking", "smile"}:
            self.mouth = max(0.08, (math.sin(self.phase * 4) + 1) * 0.28)
        self.update()

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bob = math.sin(self.phase) * (6 if self.gesture == "excited" else 4)
        look = 18 if self.gaze_target == "screen" else 0
        center = QPointF(self.width() / 2 + look, self.height() / 2 + bob)
        painter.setBrush(QColor(28, 31, 44, 235))
        painter.setPen(QColor(127, 231, 255, 220))
        painter.drawEllipse(center, 125, 170)
        painter.setBrush(QColor(127, 231, 255))
        painter.drawEllipse(QPointF(center.x() - 43, center.y() - 35), 11, 15)
        painter.drawEllipse(QPointF(center.x() + 43, center.y() - 35), 11, 15)
        mouth = QPainterPath()
        mouth.addEllipse(QPointF(center.x(), center.y() + 45), 30, 4 + self.mouth * 24)
        painter.fillPath(mouth, QColor(241, 105, 153))

    def mousePressEvent(self, event: object) -> None:
        self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: object) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bridge", default="ws://127.0.0.1:18765")
    args, qt_args = parser.parse_known_args()
    app = QApplication([sys.argv[0], *qt_args])
    window = AvatarOverlay(args.bridge)
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
