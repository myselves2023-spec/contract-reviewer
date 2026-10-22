# -*- coding: utf-8 -*-
"""冒烟测试：不依赖 HTTP，直接跑通 解析 -> 扫描 -> 评分 -> 导出。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import report, review  # noqa: E402

sample = (ROOT / "samples" / "sample_contract.txt").read_text(encoding="utf-8")
result = review.review_bytes("sample_contract.txt", text=sample, use_llm=False)

print("=" * 64)
print(f'评分 {result["score"]} / 100   等级 {result["risk_level"]}')
print(f'统计 {result["stats"]}')
print(f'段落 {result["contract"]["paragraphs"]}  字符 {result["contract"]["chars"]}')
print("=" * 64)
for finding in result["findings"]:
    cites = "、".join(s["cite"] for s in finding["statutes"])
    print(f'[{finding["severity_label"]}] {finding["id"]} {finding["name"]}  <- {cites}')
    for ev in finding["evidence"]:
        print(f'        证据: {ev["text"][:70]}')

print("=" * 64)
print(result["overall_comment"])

# 校验偏移能否正确切回原文
for finding in result["findings"]:
    for ev in finding["evidence"]:
        sliced = result["contract"]["text"][ev["start"] : ev["end"]]
        assert sliced == ev["text"], f"偏移错位: {finding['id']}"

blob = report.build(result)
out = ROOT / "samples" / "审查意见书_样例.docx"
out.write_bytes(blob)
print(f"\n导出成功: {out}  ({len(blob)} bytes)")
