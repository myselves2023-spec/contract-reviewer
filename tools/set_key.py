# -*- coding: utf-8 -*-
"""把 API Key 写进 .env，不需要手动编辑文件。

用法：
  双击 set_key.bat（推荐），按提示粘贴 key
  python tools/set_key.py                 # 交互式
  python tools/set_key.py --key sk-xxx    # 直接指定（脚本用）
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

DEFAULT_BODY = [
    "# 由 set_key 生成。改完保存后刷新页面即可，不需要重启服务。",
    "# 如果暂时不用大模型，把 LLM_API_KEY 留空即可（会被识别为未配置）。",
    "",
    "LLM_BASE_URL=https://api.deepseek.com/v1",
    "LLM_API_KEY=",
    "LLM_MODEL=deepseek-chat",
]


def mask(key: str) -> str:
    if len(key) <= 12:
        return f"（{len(key)} 字符）"
    return f"{key[:6]}…{key[-4:]}（{len(key)} 字符）"


def upsert(lines: list[str], name: str, value: str) -> tuple[list[str], bool]:
    out: list[str] = []
    done = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{name}=") or stripped.startswith(f"{name} ="):
            out.append(f"{name}={value}")
            done = True
        else:
            out.append(line)
    if not done:
        out.append(f"{name}={value}")
    return out, done


def ask_key() -> str:
    print("请粘贴你的 API Key，然后按回车。")
    print("（粘贴后屏幕上不显示字符是正常的；在这个窗口里右键即可粘贴）")
    try:
        value = getpass.getpass("API Key: ").strip()
    except Exception:  # noqa: BLE001 - 某些终端不支持隐藏输入
        value = ""
    if not value:
        # 有些控制台 getpass 读不到粘贴内容，退回可见输入，总比卡住好
        print("（没有读到输入，改为可见模式，请再粘贴一次）")
        try:
            value = input("API Key: ").strip()
        except EOFError:
            value = ""
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--key", help="直接指定 key，不走交互")
    parser.add_argument("--base-url", help="同时覆盖 LLM_BASE_URL")
    parser.add_argument("--model", help="同时覆盖 LLM_MODEL")
    args = parser.parse_args()

    key = (args.key or "").strip()
    if not key:
        print("=" * 60)
        key = ask_key()
        print()

    # 去掉常见的复制污染：引号、前后空格、换行
    key = key.strip().strip('"').strip("'").replace(" ", "").replace("\n", "")

    if not key:
        print("✗ 没有输入任何内容，已取消。")
        return 1

    if key == "sk-your-key-here":
        print("✗ 这是占位符，不是真实 key。请到 platform.deepseek.com 创建 API key。")
        return 1

    if len(key) < 20:
        print(f"⚠ 这个 key 只有 {len(key)} 个字符，通常 DeepSeek 的 key 在 30 字符以上，请确认没有漏复制。")
        print("  仍然会写入，如果检测失败请重新复制一遍。")

    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8-sig").splitlines()
    else:
        lines = list(DEFAULT_BODY)

    lines, found = upsert(lines, "LLM_API_KEY", key)
    if args.base_url:
        lines, _ = upsert(lines, "LLM_BASE_URL", args.base_url.strip())
    if args.model:
        lines, _ = upsert(lines, "LLM_MODEL", args.model.strip())

    if not ENV_PATH.exists():
        lines, _ = upsert(lines, "LLM_BASE_URL", "https://api.deepseek.com/v1")
        lines, _ = upsert(lines, "LLM_MODEL", "deepseek-chat")

    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"✓ 已写入 {ENV_PATH.name}：LLM_API_KEY = {mask(key)}")
    if not found:
        print("  （原文件里没有 LLM_API_KEY 这一行，已自动追加）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
