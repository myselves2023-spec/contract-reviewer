# -*- coding: utf-8 -*-
"""prompt 调试器：对单个审查点跑一次真实模型调用，把 prompt 和原始返回都打出来。

打磨 prompt 时的迭代循环就靠它——改 data/prompts/review_v1.user.txt，重跑，看输出。

用法：
  python tools/prompt_probe.py --file samples/contract.txt --id CP02
  python tools/prompt_probe.py --id CP01          # 用内置样例合同
  python tools/prompt_probe.py --id CP02 --raw    # 同时打印完整 prompt
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import llm, review  # noqa: E402
from app.env import load_env_file  # noqa: E402

load_env_file()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="合同文本路径，默认用 samples/sample_contract.txt")
    parser.add_argument("--id", required=True, help="审查点编号，例如 CP02")
    parser.add_argument("--raw", action="store_true", help="打印完整 prompt")
    args = parser.parse_args()

    if not llm.available():
        print("未配置 LLM（检查 .env 里的 LLM_BASE_URL / LLM_API_KEY），或 key 是占位符。")
        return 2

    source = Path(args.file) if args.file else ROOT / "samples" / "sample_contract.txt"
    text = source.read_text(encoding="utf-8-sig")

    book, _ = review.resources()
    result = review.review_bytes(source.name, text=text, use_llm=False)
    finding = next((f for f in result["findings"] if f["id"] == args.id), None)
    if not finding:
        available = "、".join(f["id"] for f in result["findings"])
        print(f"该合同未命中 {args.id}。已命中：{available}")
        return 1

    cfg = llm.config()
    system, template = llm.load_prompt(cfg["prompt"])
    user = llm.build_user_prompt(
        template,
        finding=finding,
        context=llm.context_for(result["contract"]["segments"], finding),
        statutes=[s for s in finding["statutes"]],
    )

    if args.raw:
        print("=" * 70)
        print("[SYSTEM]")
        print(system)
        print("=" * 70)
        print("[USER]")
        print(user)
        print("=" * 70)

    print(f"调用 {cfg['model']} …（prompt {len(user)} 字）")
    try:
        response = llm._chat(system, user, cfg)  # noqa: SLF001 - 调试脚本，直接复用
    except Exception as exc:  # noqa: BLE001
        print(f"调用失败：{type(exc).__name__}: {exc}")
        return 1

    content = response["choices"][0]["message"]["content"]
    print("\n[原始返回]")
    print(content)

    usage = response.get("usage") or {}
    if usage:
        print(f"\n[用量] {usage}")

    print("\n[解析结果]")
    try:
        parsed = llm._normalize_result(llm._extract_json(content))  # noqa: SLF001
        print(json.dumps(parsed, ensure_ascii=False, indent=2))
    except Exception as exc:  # noqa: BLE001
        print(f"解析失败：{exc}\n说明模型没有按约定输出 JSON，需要收紧 prompt 或换模型。")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
