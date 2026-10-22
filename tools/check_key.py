# -*- coding: utf-8 -*-
"""检查 API Key 配置：只发一次最小请求，把失败原因翻译成人话。

比对着报错猜要快得多——401 / 402 / 404 各自对应完全不同的处理动作。

用法：
  python tools/check_key.py
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import llm  # noqa: E402
from app.env import load_env_file  # noqa: E402

load_env_file()

# Windows 控制台默认 GBK，遇到 ✓/✗ 会抛 UnicodeEncodeError。
# 固定成 utf-8 并允许替换字符，保证诊断脚本本身不会崩。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

HINTS = {
    400: "请求被拒绝。最常见原因是 LLM_MODEL 写错（模型名大小写、拼写）。",
    401: "API Key 无效或已被删除。去平台重新创建一个，注意复制完整、别带空格。",
    402: "账户余额不足。DeepSeek 是预付费的，需要先充值才能调用。",
    403: "无权限访问该模型，或账号状态异常（未实名、被限制）。",
    404: f"接口地址不存在。检查 LLM_BASE_URL 是否写全，例如 https://api.deepseek.com/v1",
    429: "触发限流或并发过高。稍等再试，或调低 LLM_CONCURRENCY。",
}


def mask(key: str) -> str:
    if len(key) <= 12:
        return f"（{len(key)} 字符，未显示）"
    return f"{key[:6]}…{key[-4:]}（共 {len(key)} 字符）"


def main() -> int:
    cfg = llm.config()

    print("当前配置")
    print(f"  LLM_BASE_URL = {cfg['base_url'] or '(未设置)'}")
    print(f"  LLM_MODEL    = {cfg['model'] or '(未设置)'}")
    print(f"  LLM_API_KEY  = {mask(cfg['api_key']) if cfg['api_key'] else '(未设置)'}")
    print(f"  LLM_PROMPT   = {cfg['prompt']}")
    print()

    if not cfg["base_url"] or not cfg["api_key"]:
        print("✗ 配置不完整。请在项目根目录建 .env，内容参考 .env.example。")
        print("  注意文件名必须是 .env，不是 .env.txt")
        return 2

    key_lower = cfg["api_key"].strip().lower()
    if key_lower in llm.PLACEHOLDER_KEYS:
        print("✗ API Key 还是占位符，没换成真实 key。")
        print("  打开 .env，把 LLM_API_KEY= 后面那段替换成平台复制的 sk-... 开头的字符串。")
        return 2

    print("发送一次最小请求（max_tokens=8）…")
    body = {
        "model": cfg["model"],
        "messages": [{"role": "user", "content": "只回复两个字：ok"}],
        "max_tokens": 8,
        "stream": False,
    }

    started = time.time()
    try:
        payload = llm._post(cfg, body)  # noqa: SLF001 - 诊断脚本，直接复用
    except urllib.error.HTTPError as exc:
        elapsed = int((time.time() - started) * 1000)
        detail = ""
        try:
            raw = exc.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw)
            detail = (parsed.get("error") or {}).get("message") or raw[:200]
        except Exception:  # noqa: BLE001
            pass
        print(f"\n✗ HTTP {exc.code}（耗时 {elapsed} ms）")
        if detail:
            print(f"  服务端原话：{detail}")
        print(f"  → {HINTS.get(exc.code, '未收录的错误码，把上面这句原话发给我。')}")
        return 1
    except urllib.error.URLError as exc:
        print(f"\n✗ 连不上 {cfg['base_url']}")
        print(f"  原因：{exc.reason}")
        print("  → 检查网络/代理；LLM_BASE_URL 域名是否拼错；公司网络是否拦截。")
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"\n✗ 调用异常：{type(exc).__name__}: {exc}")
        return 1

    elapsed = int((time.time() - started) * 1000)
    content = payload["choices"][0]["message"]["content"]
    usage = payload.get("usage") or {}

    print(f"\n✓ 调用成功（{elapsed} ms）")
    print(f"  模型回复：{content!r}")
    print(f"  token 用量：{usage or '端点未返回'}")
    print("\n下一步：刷新 http://127.0.0.1:8765 ，右上角应显示「大模型已启用」。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
