from __future__ import annotations

import cv2
import mss
import numpy as np
from PIL import Image


def _jpeg(image: Image.Image, quality: int = 72) -> bytes:
    from io import BytesIO

    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue()


def capture_screen(monitor: int = 0, max_width: int = 1600) -> bytes:
    with mss.mss() as grabber:
        shot = grabber.grab(grabber.monitors[monitor])
        image = Image.frombytes("RGB", shot.size, shot.rgb)
    if image.width > max_width:
        image.thumbnail((max_width, max_width), Image.Resampling.LANCZOS)
    return _jpeg(image)


def capture_webcam(device: int = 0, max_width: int = 640) -> bytes | None:
    camera = cv2.VideoCapture(device, cv2.CAP_DSHOW)
    try:
        ok, frame = camera.read()
    finally:
        camera.release()
    if not ok:
        return None
    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    image = Image.fromarray(np.asarray(frame))
    if image.width > max_width:
        image.thumbnail((max_width, max_width), Image.Resampling.LANCZOS)
    return _jpeg(image)

