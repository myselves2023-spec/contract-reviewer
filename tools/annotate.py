# -*- coding: utf-8 -*-
"""标注工具：把规则层命中的风险点逐条给你确认，写入 eval/labels.json。

这是「用更多合同提升精度」的操作入口。流程：
    收集合同 -> 本工具标注 -> eval.py 算指标 -> 看 FP/FN -> 改规则或 prompt -> 复跑

注意：这不是"训练"。规则层的正则和审查点是明文配置，改它是改代码逻辑；
评测集的作用是把「改完到底变好还是变坏」变成可测量的数字。

用法：
    python tools/annotate.py
    python tools/annotate.py --dir eval/cases --labels eval/labels.json
    python tools/annotate.py --review          # 重新标注已标注过的合同
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import review  # noqa: E402
from app.checklist import load_checklist  # noqa: E402
from app.parsing import ParseError, extract  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

SUPPORTED = (".txt", ".md", ".docx")


def load_labels(path: Path) -> dict:
    if not path.exists():
        return {"note": "人工标注：expected 为该合同确实存在的风险点编号；空数组表示不应命中任何审查点。", "cases": []}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    payload.setdefault("cases", [])
    return payload


def save_labels(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_contract(path: Path) -> str:
    if path.suffix.lower() == ".docx":
        return extract(path.name, path.read_bytes())["text"]
    return path.read_text(encoding="utf-8-sig")


def ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        return "q"


def annotate_one(path: Path, all_ids: set[str], checkpoint_names: dict) -> list[str] | None:
    """返回该合同标注的风险点列表；返回 None 表示放弃这份。"""
    try:
        text = read_contract(path)
    except (ParseError, OSError) as exc:
        print(f"  ! 读取失败：{exc}")
        return None

    result = review.review_bytes(path.name, text=text, use_llm=False)
    findings = result["findings"]

    print(f"\n{'=' * 66}")
    print(f"  {path.name}   {result['contract']['chars']} 字 / {len(findings)} 项命中")
    print(f"{'=' * 66}")

    if not findings:
        print("  规则层未命中任何审查点。")
        print("  如果这份合同确实干净，直接回车即可（记为负样本）。")

    expected: list[str] = []
    for index, finding in enumerate(findings, 1):
        evidence = finding["evidence"][0]["text"] if finding["evidence"] else "（条款缺失）"
        if len(evidence) > 70:
            evidence = evidence[:70] + "…"
        print(f"\n  [{index}/{len(findings)}] {finding['severity_label']}风险 {finding['id']} {finding['name']}")
        print(f"      依据：{evidence}")

        while True:
            answer = ask("      这份合同真的存在该风险吗？[y 是 / n 否 / q 退出] ").lower()
            if answer in ("y", "yes", "是", ""):
                expected.append(finding["id"])
                print("      -> 记为真实风险")
                break
            if answer in ("n", "no", "否"):
                print("      -> 记为误报（规则层多报了）")
                break
            if answer in ("q", "quit"):
                return None
            print("      请输入 y / n / q")

    triggered = {f["id"] for f in findings}
    missed = sorted(all_ids - triggered)
    if missed:
        print(f"\n  规则层没有命中的审查点（{len(missed)} 项）：")
        for cid in missed:
            print(f"      {cid}  {checkpoint_names.get(cid, '')}")
        raw = ask("\n  其中有「规则层漏掉、但这份合同确实存在」的吗？\n"
                  "  输入编号，逗号分隔（如 CP03,CP15）；没有就回车跳过： ")
        for token in raw.replace("，", ",").split(","):
            cid = token.strip().upper()
            if not cid:
                continue
            if cid not in all_ids:
                print(f"      ! 忽略未知编号：{cid}")
                continue
            if cid not in expected:
                expected.append(cid)
                print(f"      -> 记为漏报（已补入 {cid}）")

    return sorted(expected)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default=str(ROOT / "eval" / "cases"), help="合同目录")
    parser.add_argument("--labels", default=str(ROOT / "eval" / "labels.json"), help="标注文件")
    parser.add_argument("--review", action="store_true", help="重新标注已有记录")
    args = parser.parse_args()

    case_dir = Path(args.dir)
    label_path = Path(args.labels)
    if not case_dir.exists():
        print(f"目录不存在：{case_dir}")
        return 1

    checkpoints = load_checklist()
    all_ids = {cp.id for cp in checkpoints}
    checkpoint_names = {cp.id: cp.name for cp in checkpoints}

    payload = load_labels(label_path)
    done = {case["file"] for case in payload["cases"]}

    files = sorted(p for p in case_dir.iterdir() if p.suffix.lower() in SUPPORTED)
    pending = [p for p in files if args.review or p.name not in done]

    print(f"合同目录：{case_dir}")
    print(f"标注文件：{label_path}")
    print(f"共 {len(files)} 份，待标注 {len(pending)} 份")

    if not pending:
        print("\n都标注完了。运行 python tools/eval.py --verbose 看指标。")
        return 0

    saved = 0
    for path in pending:
        expected = annotate_one(path, all_ids, checkpoint_names)
        if expected is None:
            print("\n已退出，未保存当前这份。")
            break

        payload["cases"] = [c for c in payload["cases"] if c["file"] != path.name]
        payload["cases"].append({"file": path.name, "expected": expected})
        payload["cases"].sort(key=lambda c: c["file"])
        save_labels(label_path, payload)
        saved += 1
        print(f"\n  已保存：{path.name} -> {len(expected)} 个风险点")

    print(f"\n{'=' * 66}")
    print(f"本次标注 {saved} 份，标注集共 {len(payload['cases'])} 份")
    print("下一步： python tools/eval.py --verbose")
    return 0


if __name__ == "__main__":
    sys.exit(main())
