# -*- coding: utf-8 -*-
"""用样例合同生成一份中文 PDF，用于验证 PDF 解析链路。

没有 LibreOffice 也能造真实测试样本：直接用 PyMuPDF 排版写入，
带文字层，能反证「提取 -> 分段 -> 审查」是否等价于 txt 版本。

用法： python tools/make_sample_pdf.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "vendor"
sys.path.append(str(VENDOR))

import fitz  # noqa: E402

SAMPLES = ROOT / "samples"
SOURCE = SAMPLES / "sample_contract.txt"
TARGET = SAMPLES / "技术服务合同_样例.pdf"

# 用系统自带的中文字体，保证 PDF 里是真实中文字形而不是方框
FONT_CANDIDATES = [
    Path(r"C:\Windows\Fonts\msyh.ttc"),
    Path(r"C:\Windows\Fonts\simsun.ttc"),
    Path(r"C:\Windows\Fonts\simhei.ttf"),
]


def pick_font() -> Path:
    for path in FONT_CANDIDATES:
        if path.exists():
            return path
    raise SystemExit("找不到中文字体，无法生成测试 PDF")


def main() -> int:
    lines = [line.strip() for line in SOURCE.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    font_path = pick_font()

    document = fitz.open()
    page = None
    y = 0.0
    margin, line_height, font_size = 56.0, 18.0, 10.5

    for index, line in enumerate(lines):
        if page is None or y > 780:
            page = document.new_page(width=595, height=842)  # A4
            y = margin
        size = 15 if index == 0 else font_size
        page.insert_text(
            (margin, y),
            line,
            fontsize=size,
            fontname="cjk",
            fontfile=str(font_path),
            color=(0, 0, 0),
        )
        y += line_height + (6 if index == 0 else 0)

    # 只嵌入用到的字形，否则整份中文字体会被打包进去（十几 MB）
    try:
        document.subset_fonts()
    except Exception as exc:  # noqa: BLE001 - 老版本没有这个方法
        print(f"  (字体子集化失败，文件会偏大：{exc})")

    document.save(str(TARGET), garbage=4, deflate=True)
    document.close()
    print(f"已生成 {TARGET.name}（{TARGET.stat().st_size} bytes，字体 {font_path.name}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
