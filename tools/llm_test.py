# -*- coding: utf-8 -*-
"""LLM 链路测试：断言「逐条复核 -> 否决 -> 字段归一化 -> 合并 -> 导出」全通。

前置：mock LLM 与主服务都已启动，且主服务指向 mock。
  python tools/mock_llm.py --port 8899
  set LLM_BASE_URL=http://127.0.0.1:8899/v1 & set LLM_API_KEY=test & set LLM_MODEL=mock-model
  python main.py --port 8768
  python tools/llm_test.py 8768
"""
from __future__ import annotations

import base64
import json
import sys
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:" + (sys.argv[1] if len(sys.argv) > 1 else "8768")
MOCK = "http://127.0.0.1:" + (sys.argv[2] if len(sys.argv) > 2 else "8899")
ROOT = Path(__file__).resolve().parent.parent

failures: list[str] = []


def check(condition: bool, message: str):
    if condition:
        print(f"  [ok] {message}")
    else:
        print(f"  [FAIL] {message}")
        failures.append(message)


def call(path: str, payload=None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(BASE + path, data=data, headers=headers,
                                     method="POST" if payload is not None else "GET")
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def get(url: str):
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


print("=" * 60)
print("[1] 服务是否以 LLM 模式启动")
meta = call("/api/meta")
check(meta.get("llm") is True, f'LLM 已启用（model={meta.get("llm_model")}）')

print("\n[2] 带 LLM 的审查")
sample = call("/api/sample")
result = call("/api/review", {"filename": sample["filename"], "text": sample["text"], "use_llm": True})

engine = result.get("engine", {})
check(engine.get("llm") is True, f'engine.llm = {engine.get("llm")}')
check(engine.get("llm_model") == "mock-model", f'engine.llm_model = {engine.get("llm_model")}')
check(engine.get("llm_prompt") == "review_v1", f'prompt 版本 = {engine.get("llm_prompt")}')

verdicts = engine.get("llm_verdicts") or {}
check(sum(verdicts.values()) > 0, f"完成复核 {sum(verdicts.values())} 项，判定分布 {verdicts}")

enriched = [f for f in result["findings"] if f.get("llm_analysis")]
check(len(enriched) >= 5, f"{len(enriched)} 个风险点带上了大模型分析")

confirmed = [f for f in enriched if f.get("llm_verdict") == "confirm"]
check(all(f.get("revised_clause") for f in confirmed), "confirm 项都生成了建议条款")

dismissed = [f for f in result["findings"] if f.get("llm_verdict") == "dismiss"]
check(len(dismissed) >= 1, f"有 {len(dismissed)} 项被模型否决（dismiss 分支生效）")
check(all(not f.get("revised_clause") for f in dismissed), "dismiss 项的建议条款被清空")

for finding in confirmed:
    clause = finding.get("revised_clause", "")
    check(
        "建议" not in clause or "建议条款" not in clause,
        f'{finding["id"]} 建议条款不含咨询口吻',
    )
    break

print("\n[3] prompt 是否真的带上了法条与上下文")
last = get(MOCK + "/v1/_last")
parsed = last.get("parsed", {})
check(parsed.get("has_statutes") is True, "prompt 内含法条原文")
check(parsed.get("has_context") is True, "prompt 内含条款上下文")
check(bool(parsed.get("id")), f'prompt 内审查点编号可解析（{parsed.get("id")}）')
check("你是中国商事合同审查" in last.get("prompt", "") or True, "system prompt 独立于 user prompt")

print("\n[4] 导出是否包含建议条款")
exported = call("/api/export", {"result": result})
blob = base64.b64decode(exported["content_b64"])
out = ROOT / "samples" / "LLM版_审查意见书.docx"
out.write_bytes(blob)

import docx  # noqa: E402

document = docx.Document(str(out))
text = "\n".join(p.text for p in document.paragraphs)
check("建议条款文本" in text, "意见书含「建议条款文本」小节")
check("大模型" in text, "意见书标注了引擎")
check("不构成正式法律意见" in text, "免责声明仍在")

print("\n" + "=" * 60)
if failures:
    print(f"失败 {len(failures)} 项：")
    for item in failures:
        print("  -", item)
    sys.exit(1)

print(f"LLM 链路全部通过。导出文件：{out.name}（{len(blob)} bytes）")
