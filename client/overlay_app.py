from __future__ import annotations

import argparse
import math
import sys

from PyQt6.QtCore import QPointF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPainterPath
from PyQt6.QtWidgets import QApplication, QWidget


class AvatarOverlay(QWidget):
    """Transparent shell; replace paintEvent with a VRM/WebGL renderer adapter."""

    def __init__(self) -> None:
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
        self.mouth = 0.0
        timer = QTimer(self)
        timer.timeout.connect(self._animate)
        timer.start(16)

    def _animate(self) -> None:
        self.phase += 0.06
        self.update()

    def apply_motion(self, expression: str, mouth_open: float) -> None:
        self.expression = expression
        self.mouth = max(0.0, min(1.0, mouth_open))

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bob = math.sin(self.phase) * 4
        center = QPointF(self.width() / 2, self.height() / 2 + bob)
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
    parser = argparse.ArgumentParser(add_help=False)
    parser.parse_known_args()
    app = QApplication(sys.argv)
    window = AvatarOverlay()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()

