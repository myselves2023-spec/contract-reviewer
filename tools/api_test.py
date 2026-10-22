# -*- coding: utf-8 -*-
"""接口冒烟测试：模拟前端调用，验证 HTTP 层与导出链路。

用法： python tools/api_test.py [port]
"""
from __future__ import annotations

import base64
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:" + (sys.argv[1] if len(sys.argv) > 1 else "8765")
ROOT = Path(__file__).resolve().parent.parent


def call(path: str, payload=None, method: str = "GET"):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


print("[1] GET /                ->", end=" ")
with urllib.request.urlopen(BASE + "/", timeout=10) as r:
    html = r.read().decode("utf-8")
    print(r.status, f"{len(html)} bytes", "结构正常" if 'id="dropzone"' in html else "结构异常")

print("[2] GET /assets/app.js   ->", end=" ")
with urllib.request.urlopen(BASE + "/assets/app.js", timeout=10) as r:
    print(r.status, r.headers.get("Content-Type"))

print("[3] GET /api/meta        ->", end=" ")
status, meta = call("/api/meta")
print(status, meta)

print("[4] GET /api/sample      ->", end=" ")
status, sample = call("/api/sample")
print(status, sample["filename"], f'{len(sample["text"])} 字')

print("[5] POST /api/review     ->", end=" ")
status, result = call(
    "/api/review",
    {"filename": sample["filename"], "text": sample["text"], "use_llm": False},
    "POST",
)
print(status, f'评分 {result["score"]}', result["risk_level"], result["stats"])

assert result["findings"], "未检出任何风险，规则层失效"
assert result["contract"]["text"].startswith("技术服务合同"), "原文回传异常"

for finding in result["findings"]:
    for ev in finding["evidence"]:
        assert result["contract"]["text"][ev["start"]:ev["end"]] == ev["text"], "偏移错位"

print("[6] POST /api/export     ->", end=" ")
status, exported = call("/api/export", {"result": result}, "POST")
blob = base64.b64decode(exported["content_b64"])
out = ROOT / "samples" / exported["filename"]
out.write_bytes(blob)
print(status, exported["filename"], f"{len(blob)} bytes")

print("[7] POST /api/review .docx ->", end=" ")
docx_path = ROOT / "samples" / "技术服务合同_样例.docx"
if docx_path.exists():
    encoded = base64.b64encode(docx_path.read_bytes()).decode("ascii")
    status, docx_result = call(
        "/api/review",
        {"filename": docx_path.name, "content_b64": encoded, "use_llm": False},
        "POST",
    )
    print(status, f'评分 {docx_result["score"]}', docx_result["stats"],
          f'{docx_result["contract"]["paragraphs"]} 段')
    assert docx_result["findings"], ".docx 解析后未检出风险"
else:
    print("跳过（样例 docx 不存在，先运行 tools/make_sample_docx.py）")

print("[8] POST /api/review .pdf ->", end=" ")
pdf_path = ROOT / "samples" / "技术服务合同_样例.pdf"
if pdf_path.exists():
    encoded = base64.b64encode(pdf_path.read_bytes()).decode("ascii")
    status, pdf_result = call(
        "/api/review",
        {"filename": pdf_path.name, "content_b64": encoded, "use_llm": False},
        "POST",
    )
    print(status, f'评分 {pdf_result["score"]}', pdf_result["stats"],
          f'{pdf_result["contract"]["paragraphs"]} 段')
    assert pdf_result["contract"]["paragraphs"] == result["contract"]["paragraphs"], \
        "PDF 与 txt 解析出的段落数不一致"
else:
    print("跳过（样例 PDF 不存在，先运行 tools/make_sample_pdf.py）")

print("[9] 损坏 PDF 的错误处理 ->", end=" ")
try:
    call(
        "/api/review",
        {"filename": "broken.pdf", "content_b64": base64.b64encode(b"%PDF-1.4 broken").decode()},
        "POST",
    )
    print("未按预期报错")
except urllib.error.HTTPError as exc:
    body = json.loads(exc.read().decode("utf-8"))
    print(exc.code, body.get("error", "")[:36])

print("\n全部接口通过。")
