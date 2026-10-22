# -*- coding: utf-8 -*-
"""评测脚本：用带人工标注的合同集，计算规则层的精确率 / 召回率 / F1。

标注格式（eval/labels.json）：
{
  "cases": [
    {"file": "sample_contract.txt", "expected": ["CP01", "CP02"]},
    {"file": "clean_service_contract.txt", "expected": []}
  ]
}
expected 为空数组表示「该合同不应命中任何审查点」，用于衡量误报。

用法：
  python tools/eval.py
  python tools/eval.py --verbose
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import review  # noqa: E402

EVAL_DIR = ROOT / "eval"
CASES = EVAL_DIR / "cases"
LABELS = EVAL_DIR / "labels.json"


def load_cases():
    if not LABELS.exists():
        raise SystemExit(f"缺少标注文件：{LABELS}")
    payload = json.loads(LABELS.read_text(encoding="utf-8-sig"))
    cases = []
    for item in payload.get("cases", []):
        # 允许直接引用 samples/ 下的演示合同，避免重复拷贝
        candidates = [CASES / item["file"], ROOT / "samples" / item["file"]]
        path = next((p for p in candidates if p.exists()), None)
        if path is None:
            raise SystemExit(f"标注引用的文件不存在：{item['file']}")
        cases.append(
            {
                "name": item["file"],
                "text": path.read_text(encoding="utf-8-sig"),
                "expected": set(item.get("expected") or []),
            }
        )
    return cases


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", action="store_true", help="打印每个合同的明细")
    args = parser.parse_args()

    cases = load_cases()
    if not cases:
        raise SystemExit("标注集为空")

    tp = fp = fn = 0
    per_checkpoint = {}
    rows = []

    for case in cases:
        result = review.review_bytes(case["name"], text=case["text"], use_llm=False)
        predicted = {f["id"] for f in result["findings"]}
        expected = case["expected"]

        case_tp = predicted & expected
        case_fp = predicted - expected
        case_fn = expected - predicted

        tp += len(case_tp)
        fp += len(case_fp)
        fn += len(case_fn)

        for cid in predicted | expected:
            bucket = per_checkpoint.setdefault(cid, {"tp": 0, "fp": 0, "fn": 0})
            if cid in case_tp:
                bucket["tp"] += 1
            elif cid in case_fp:
                bucket["fp"] += 1
            elif cid in case_fn:
                bucket["fn"] += 1

        rows.append((case["name"], result["score"], case_tp, case_fp, case_fn))

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    width = max(len(r[0]) for r in rows) + 2
    print(f"\n评测集：{len(cases)} 份合同，{sum(len(c['expected']) for c in cases)} 个标注风险点\n")
    print(f'{"合同".ljust(width)}分数   命中   误报   漏报')
    print("-" * (width + 26))
    for name, score, case_tp, case_fp, case_fn in rows:
        if args.verbose:
            print(f"{name.ljust(width)}{score:>4}   {len(case_tp):>3}   "
                  f"{len(case_fp):>3}   {len(case_fn):>3}")
            if case_fp:
                print(f'{"":{width}}误报: {", ".join(sorted(case_fp))}')
            if case_fn:
                print(f'{"":{width}}漏报: {", ".join(sorted(case_fn))}')
        else:
            print(f"{name.ljust(width)}{score:>4}   {len(case_tp):>3}   "
                  f"{len(case_fp):>3}   {len(case_fn):>3}")

    print("-" * (width + 26))
    print(f"TP={tp}  FP={fp}  FN={fn}")
    print(f"精确率 Precision = {precision:.1%}")
    print(f"召回率 Recall    = {recall:.1%}")
    print(f"F1              = {f1:.1%}")

    weak = [(cid, b) for cid, b in per_checkpoint.items() if b["fp"] or b["fn"]]
    if weak:
        print("\n需要调优的审查点：")
        for cid, bucket in sorted(weak):
            print(f"  {cid}  TP={bucket['tp']} FP={bucket['fp']} FN={bucket['fn']}")

    return 0 if f1 >= 0.8 else 1


if __name__ == "__main__":
    sys.exit(main())
