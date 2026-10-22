# -*- coding: utf-8 -*-
"""本地 mock 的 OpenAI 兼容端点，用于在没有外网时验证 LLM 链路。

它不是一个"假装能用"的桩：它真的会解析程序发来的 prompt，按 prompt 里出现的
审查点编号给出不同结论（含 dismiss），因此可以验证「否决」「字段归一化」
「并发合并」「重试」这些分支是否写对。

用法：
  python tools/mock_llm.py --port 8899
  python tools/mock_llm.py --port 8899 --fail-first 2   # 前 2 次请求返回 500，测重试
"""
from __future__ import annotations

import argparse
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATE = {"calls": 0, "fail_first": 0, "last_prompt": "", "last_body": None}
LOCK = threading.Lock()

# 这些审查点在 mock 里判 dismiss，用于覆盖「模型否决规则层」分支
DISMISS_IDS = {"CP16"}
DISMISS_KEYWORDS = ("保密",)


def extract(user_prompt: str) -> dict:
    def grab(pattern: str) -> str:
        found = re.search(pattern, user_prompt)
        return found.group(1).strip() if found else ""

    return {
        "id": grab(r"编号：(.+)"),
        "name": grab(r"名称：(.+)"),
        "severity": grab(r"初判等级：(.+)"),
        "has_statutes": "《民法典》" in user_prompt,
        "has_context": "【该审查点所在的条款上下文】" in user_prompt,
    }


def build_answer(info: dict) -> dict:
    cid = info.get("id", "")
    name = info.get("name", "该事项")
    should_dismiss = cid in DISMISS_IDS or any(k in name for k in DISMISS_KEYWORDS)

    if should_dismiss:
        return {
            "verdict": "dismiss",
            "confidence": 0.78,
            "analysis": f"经核对上下文，本合同已就「{name}」作出明确约定，规则层命中的表述并非风险条款，不构成实质风险。",
            "revised_clause": "",
        }

    return {
        "verdict": "confirm",
        "confidence": 0.86,
        "analysis": f"本合同关于「{name}」的表述将相应不利后果分配给甲方，且未设置对等救济或补偿机制。",
        "revised_clause": (
            f"双方就{name}事项确认如下：一方违反本条约定致使对方遭受损失的，"
            f"应赔偿对方由此产生的直接损失及可预见的间接损失；"
            f"本条约定不影响对方依据法律规定主张其他权利。"
        ),
    }


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # 安静一点
        return

    def _send(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path.startswith("/v1/_last"):
            with LOCK:
                return self._send(200, {
                    "prompt": STATE["last_prompt"],
                    "parsed": extract(STATE["last_prompt"]),
                    "calls": STATE["calls"],
                })
        return self._send(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        if not self.path.startswith("/v1/chat/completions"):
            return self._send(404, {"error": "not found"})

        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            return self._send(400, {"error": "bad json"})

        with LOCK:
            STATE["calls"] += 1
            call_index = STATE["calls"]
            if call_index <= STATE["fail_first"]:
                return self._send(500, {"error": "mock transient failure"})
            if STATE.get("reject_json_mode") and "response_format" in payload:
                return self._send(400, {"error": "response_format is not supported"})
            messages = payload.get("messages") or []
            user_prompt = next(
                (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), ""
            )
            STATE["last_prompt"] = user_prompt
            STATE["last_body"] = payload

        info = extract(user_prompt)
        answer = build_answer(info)

        return self._send(
            200,
            {
                "id": f"mock-{call_index}",
                "object": "chat.completion",
                "model": payload.get("model", "mock-model"),
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(answer, ensure_ascii=False),
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            },
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8899)
    parser.add_argument("--fail-first", type=int, default=0,
                        help="前 N 个请求返回 500，用于测试重试逻辑")
    parser.add_argument("--reject-json-mode", action="store_true",
                        help="收到 response_format 时返回 400，用于测试降级重试")
    args = parser.parse_args()

    STATE["fail_first"] = args.fail_first
    STATE["reject_json_mode"] = args.reject_json_mode
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.daemon_threads = True
    print(f"mock LLM 已启动： http://127.0.0.1:{args.port}/v1  (fail_first={args.fail_first})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
