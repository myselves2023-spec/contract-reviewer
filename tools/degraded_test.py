# -*- coding: utf-8 -*-
"""降级测试：LLM 端点不可达时，审查必须仍然成功返回规则结果。

前置：主服务指向一个不存在的端口（LLM_RETRIES=0 加速）。
  set LLM_BASE_URL=http://127.0.0.1:9/v1 & set LLM_API_KEY=x & set LLM_RETRIES=0
  python main.py --port 8770
  python tools/degraded_test.py 8770
"""
from __future__ import annotations

import json
import sys
import urllib.request

BASE = "http://127.0.0.1:" + (sys.argv[1] if len(sys.argv) > 1 else "8770")


def call(path: str, payload=None):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else None
    headers = {"Content-Type": "application/json"} if payload else {}
    request = urllib.request.Request(BASE + path, data=data, headers=headers,
                                     method="POST" if payload else "GET")
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


meta = call("/api/meta")
sample = call("/api/sample")
result = call("/api/review", {"filename": sample["filename"], "text": sample["text"], "use_llm": True})

engine = result.get("engine", {})
checks = [
    (meta.get("llm") is True, "配置存在，meta 显示 LLM 已启用"),
    (len(result["findings"]) > 0, f'仍返回 {len(result["findings"])} 个风险点'),
    (engine.get("llm") is False, "engine.llm 为 False（已降级）"),
    (bool(engine.get("llm_error")), f'记录了失败原因：{(engine.get("llm_error") or "")[:50]}'),
    (all("llm_analysis" not in f for f in result["findings"]), "没有残留半截的模型字段"),
    (result["score"] > 0, f'评分仍然计算（{result["score"]}）'),
]

failed = 0
for ok, message in checks:
    print(f"  [{'ok' if ok else 'FAIL'}] {message}")
    failed += 0 if ok else 1

print("\n降级路径通过。" if not failed else f"\n失败 {failed} 项")
sys.exit(1 if failed else 0)
