"""Generate app/gui/app.ico (multi-size, PNG-compressed entries).  python tools/make_icon.py"""
import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter

SIZES = [16, 24, 32, 48, 64, 128, 256]
OUTPUT = Path(__file__).resolve().parents[1] / "app" / "gui" / "app.ico"


def render(size: int) -> bytes:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    margin = max(1, size // 16)
    rect = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#0f6cbd"))
    painter.drawRoundedRect(rect, size * 0.2, size * 0.2)

    font = QFont("Segoe UI")
    font.setBold(True)
    font.setPixelSize(int(size * 0.5))
    painter.setFont(font)
    painter.setPen(QColor("white"))
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "iF")
    painter.end()

    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)


def main():
    QGuiApplication(sys.argv)
    images = [render(size) for size in SIZES]

    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, payload = b"", b""
    for size, png in zip(SIZES, images):
        dim = 0 if size >= 256 else size  # 0 means 256 in the ICO directory
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset + len(payload))
        payload += png

    OUTPUT.write_bytes(header + entries + payload)
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
