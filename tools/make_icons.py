# -*- coding: utf-8 -*-
"""生成 PWA 图标：深蓝底 + 白色「法」字，输出多种尺寸。

用系统字体渲染，不依赖任何图标库。
用法： python tools/make_icons.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

NAVY = (31, 58, 95)
WHITE = (255, 255, 255)

FONT_CANDIDATES = [
    Path(r"C:\Windows\Fonts\msyhbd.ttc"),
    Path(r"C:\Windows\Fonts\msyh.ttc"),
    Path(r"C:\Windows\Fonts\simhei.ttf"),
    Path(r"C:\Windows\Fonts\simsun.ttc"),
]

SIZES = {
    "icon-192.png": 192,
    "icon-512.png": 512,
    "apple-touch-icon.png": 180,
    "favicon.png": 64,
}


def pick_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    raise SystemExit("找不到中文字体")


def make(size: int) -> Image.Image:
    # 4 倍超采样后缩小，边缘更干净
    scale = 4
    canvas = Image.new("RGBA", (size * scale, size * scale), NAVY + (255,))
    draw = ImageDraw.Draw(canvas)

    font = pick_font(int(size * scale * 0.62))
    text = "法"
    box = draw.textbbox((0, 0), text, font=font)
    x = (size * scale - (box[2] - box[0])) / 2 - box[0]
    y = (size * scale - (box[3] - box[1])) / 2 - box[1] - size * scale * 0.02
    draw.text((x, y), text, font=font, fill=WHITE)

    return canvas.resize((size, size), Image.LANCZOS)


def main() -> int:
    for name, size in SIZES.items():
        image = make(size)
        path = WEB / name
        image.save(path, "PNG", optimize=True)
        print(f"  {name}  {size}x{size}  {path.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
