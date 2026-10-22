# -*- coding: utf-8 -*-
"""真实模型端到端自检：不需要起服务，直接跑一次带 LLM 的完整审查。

这是「配好 key 之后，到底能不能用」的最终答案。它会打印模型原始判定、
耗时，并导出一份 docx。

用法：
  python tools/live_check.py
  或双击 verify.bat
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import llm, report, review  # noqa: E402
from app.env import load_env_file  # noqa: E402

load_env_file()

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

SAMPLE = ROOT / "samples" / "sample_contract.txt"


def main() -> int:
    cfg = llm.config()
    print("=" * 68)
    print("真实模型端到端自检")
    print("=" * 68)
    print(f"  端  点：{cfg['base_url'] or '(未设置)'}")
    print(f"  模  型：{cfg['model'] or '(未设置)'}")
    print(f"  提示词：{cfg['prompt']}")
    key = cfg["api_key"]
    print(f"  Key  ：{'(未设置)' if not key else f'{key[:6]}…{key[-4:]}（{len(key)} 字符）'}")
    print()

    if not llm.available():
        if not cfg["base_url"] or not cfg["api_key"]:
            print("✗ 还没配置。请双击 edit_env.bat，把 .env 里的")
            print("  LLM_API_KEY=sk-your-key-here 换成你的真实 key 后再运行。")
        else:
            print("✗ Key 仍是占位符或处于禁用状态（LLM_DISABLE=1）。")
            print("  请双击 edit_env.bat 修改 .env。")
        return 2

    if not SAMPLE.exists():
        print(f"✗ 找不到样例合同：{SAMPLE}")
        return 1

    text = SAMPLE.read_text(encoding="utf-8-sig")
    print("调用真实模型复核样例合同（约 12 次请求，请稍候）…\n")

    result = review.review_bytes("技术服务合同（样例）.txt", text=text, use_llm=True)
    engine = result.get("engine") or {}

    print("-" * 68)
    print(f"规则层：命中 {result['stats']['total']} 项，评分 {result['score']}/100（{result['risk_level']}）")

    if not engine.get("llm"):
        print("大模型：✗ 未生效")
        if engine.get("llm_error"):
            print(f"  失败原因：{engine['llm_error'][:200]}")
        print("\n规则结果仍然可用，但大模型没跑通。把上面的原因发我，我判断是 key、模型名还是网络问题。")
        return 1

    verdicts = engine.get("llm_verdicts") or {}
    print(f"大模型：✓ 生效（{engine.get('llm_model')}，{engine.get('llm_latency_ms')} ms）")
    print(f"  复核 {sum(verdicts.values())} 项：确认 {verdicts.get('confirm', 0)}、"
          f"排除 {verdicts.get('dismiss', 0)}、存疑 {verdicts.get('uncertain', 0)}")

    enriched = [f for f in result["findings"] if f.get("llm_analysis")]
    print(f"  生成解释 {len(enriched)} 条，建议条款 {sum(1 for f in result['findings'] if f.get('revised_clause'))} 条")

    print("-" * 68)
    print("模型实际输出（前 3 条）")
    for finding in enriched[:3]:
        verdict = finding.get("llm_verdict")
        mark = {"confirm": "确认", "dismiss": "排除", "uncertain": "存疑"}.get(verdict, verdict)
        print(f"\n[{mark}] {finding['id']} {finding['name']}")
        print(f"  分析：{finding.get('llm_analysis')}")
        if finding.get("revised_clause"):
            print(f"  条款：{finding['revised_clause']}")

    blob = report.build(result)
    out = ROOT / "samples" / "真实模型_审查意见书.docx"
    out.write_bytes(blob)

    print("\n" + "-" * 68)
    print(f"✓ 全链路可用。意见书已导出：{out.name}（{len(blob)} bytes）")
    print("  现在可以双击 run.bat 打开界面，勾选「启用大模型复核」正常使用了。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
