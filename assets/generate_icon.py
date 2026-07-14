"""Generates the shankompare application icon: a PNG set plus a multi-
resolution .ico, written to assets/icons/. Pure PySide6 (already a project
dependency) — no Pillow or other image library needed, including for the
.ico packing (PNG-in-ICO, a plain binary container assembled by hand).

Re-run after changing the design in this file:
    python assets/generate_icon.py
"""

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath, QPen

OUT_DIR = Path(__file__).parent / "icons"
SIZES = (16, 24, 32, 48, 64, 128, 256)

LEFT_COLOR = QColor("#1565c0")  # matches the app's left-only status color
RIGHT_COLOR = QColor("#2e7d32")  # matches the app's right-only status color
ARROW_FILL = QColor("#ffffff")
ARROW_OUTLINE = QColor(0, 0, 0, 90)


def _double_arrow_path(cx: float, cy: float, size: float) -> QPainterPath:
    half_len = size * 0.30
    head_len = size * 0.11
    head_half_w = size * 0.085
    shaft_half_t = size * 0.045

    points = [
        (cx - half_len, cy),
        (cx - half_len + head_len, cy - head_half_w),
        (cx - half_len + head_len, cy - shaft_half_t),
        (cx + half_len - head_len, cy - shaft_half_t),
        (cx + half_len - head_len, cy - head_half_w),
        (cx + half_len, cy),
        (cx + half_len - head_len, cy + head_half_w),
        (cx + half_len - head_len, cy + shaft_half_t),
        (cx - half_len + head_len, cy + shaft_half_t),
        (cx - half_len + head_len, cy + head_half_w),
    ]
    path = QPainterPath()
    path.moveTo(*points[0])
    for x, y in points[1:]:
        path.lineTo(x, y)
    path.closeSubpath()
    return path


def render(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    margin = size * 0.03
    radius = size * 0.22
    clip = QPainterPath()
    clip.addRoundedRect(
        QRectF(margin, margin, size - 2 * margin, size - 2 * margin), radius, radius
    )
    painter.setClipPath(clip)
    painter.fillRect(QRectF(0, 0, size / 2, size), LEFT_COLOR)
    painter.fillRect(QRectF(size / 2, 0, size / 2, size), RIGHT_COLOR)
    painter.setClipping(False)

    painter.setPen(QPen(ARROW_OUTLINE, max(1.0, size * 0.012)))
    painter.setBrush(ARROW_FILL)
    painter.drawPath(_double_arrow_path(size / 2, size / 2, size))

    painter.end()
    return image


def _png_bytes(image: QImage) -> bytes:
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buf, "PNG")
    return bytes(buf.data())


def write_ico(path: Path, images: list[QImage]) -> None:
    entries = []
    payload = b""
    offset = 6 + 16 * len(images)
    for image in images:
        png = _png_bytes(image)
        # ICO stores 256 as 0 in the single-byte width/height fields
        dim = image.width() if image.width() < 256 else 0
        entries.append(struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset))
        payload += png
        offset += len(png)
    header = struct.pack("<HHH", 0, 1, len(images))
    path.write_bytes(header + b"".join(entries) + payload)


def main() -> None:
    QGuiApplication.instance() or QGuiApplication(sys.argv)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    images = [render(size) for size in SIZES]
    for size, image in zip(SIZES, images, strict=True):
        image.save(str(OUT_DIR / f"shankompare_{size}.png"))
    write_ico(OUT_DIR / "shankompare.ico", images)
    print(f"Wrote shankompare.ico and {len(SIZES)} PNGs to {OUT_DIR}")


if __name__ == "__main__":
    main()
