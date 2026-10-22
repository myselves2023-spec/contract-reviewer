# -*- coding: utf-8 -*-
"""HTTP 服务：标准库实现，不依赖 FastAPI/Flask。

之所以不用框架，是因为目标部署环境往往装不了包。代价是要自己处理路由和
multipart，收益是「clone 下来就能跑」。前端一律以 JSON + base64 传文件，
避开 multipart 解析。
"""
from __future__ import annotations

import base64
import binascii
import json
import os
import sys
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import llm, report, review
from .checklist import load_checklist
from .parsing import ParseError

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
SAMPLES = ROOT / "samples"

MAX_UPLOAD = 12 * 1024 * 1024  # 12 MB

# 内置样例：key -> (磁盘文件, 展示名)
SAMPLE_FILES = {
    "service": ("sample_contract.txt", "技术服务合同（样例）.txt"),
    "lease": ("租赁合同_样例.txt", "商铺租赁合同（样例）.txt"),
}

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".webmanifest": "application/manifest+json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".png": "image/png",
    ".woff2": "font/woff2",
}

# 必须挂在站点根路径的文件：Service Worker 的作用域由它的 URL 决定，
# 放在 /assets/ 下会只能控制 /assets/。
ROOT_FILES = {
    "/manifest.json",
    "/sw.js",
    "/icon-192.png",
    "/icon-512.png",
    "/apple-touch-icon.png",
    "/favicon.png",
}


def _json_bytes(payload, status: int = 200):
    return status, json.dumps(payload, ensure_ascii=False).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "ContractReviewer/1.0"
    protocol_version = "HTTP/1.1"

    # ---------------------------------------------------------------- 工具
    def _send(self, status: int, body: bytes, content_type: str, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_json(self, payload, status: int = 200):
        code, body = _json_bytes(payload, status)
        self._send(code, body, "application/json; charset=utf-8")

    def _error(self, message: str, status: int = 400, detail: str = ""):
        payload = {"error": message}
        if detail:
            payload["detail"] = detail
        self._send_json(payload, status)

    def _read_body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ValueError("Content-Length 非法")
        if length > MAX_UPLOAD:
            raise ValueError(f"文件过大，上限 {MAX_UPLOAD // 1024 // 1024} MB")
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("请求体不是合法 JSON") from exc

    # ---------------------------------------------------------------- 路由
    def do_GET(self):  # noqa: N802
        path = unquote(urlparse(self.path).path)
        try:
            if path in ("/", "/index.html"):
                return self._serve_file(WEB / "index.html")
            if path == "/api/meta":
                # 重新读一次 .env：改完配置刷新页面即可生效，不必重启服务
                _load_env_file()
                book, checkpoints = review.resources()
                return self._send_json(
                    {
                        "statutes": len(book),
                        "checkpoints": len(checkpoints),
                        "llm": llm.available(),
                        "llm_model": llm.config()["model"] if llm.available() else "",
                        "source": book.meta.get("title", "中华人民共和国民法典"),
                        "effective": book.meta.get("effective", ""),
                        "source_url": book.meta.get("source_url", ""),
                    }
                )
            if path == "/api/sample":
                query = parse_qs(urlparse(self.path).query)
                key = (query.get("name") or ["service"])[0]
                if key not in SAMPLE_FILES:
                    return self._error(f"未知样例：{key}", 404)
                filename, display = SAMPLE_FILES[key]
                sample = SAMPLES / filename
                if not sample.exists():
                    return self._error("样例合同不存在", 404)
                text = sample.read_text(encoding="utf-8-sig")
                return self._send_json({"filename": display, "text": text})
            if path == "/api/samples":
                return self._send_json(
                    {
                        "samples": [
                            {"key": key, "label": display}
                            for key, (filename, display) in SAMPLE_FILES.items()
                            if (SAMPLES / filename).exists()
                        ]
                    }
                )
            if path == "/api/checklist":
                return self._send_json(
                    {"checkpoints": [cp.raw for cp in load_checklist()]}
                )
            if path in ROOT_FILES:
                response = self._serve_file(WEB / path.lstrip("/"))
                return response
            if path.startswith("/assets/"):
                return self._serve_file(WEB / path[len("/assets/"):])
            return self._error("接口不存在", 404)
        except BrokenPipeError:
            return
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            return self._error("服务端内部错误", 500)

    def do_HEAD(self):  # noqa: N802
        return self.do_GET()

    def do_POST(self):  # noqa: N802
        path = unquote(urlparse(self.path).path)
        try:
            if path == "/api/review":
                return self._handle_review()
            if path == "/api/export":
                return self._handle_export()
            return self._error("接口不存在", 404)
        except ValueError as exc:
            return self._error(str(exc), 400)
        except ParseError as exc:
            return self._error(str(exc), 422)
        except BrokenPipeError:
            return
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            return self._error("服务端内部错误", 500, traceback.format_exc(limit=2))

    # ---------------------------------------------------------------- 业务
    def _handle_review(self):
        payload = self._read_body()
        filename = str(payload.get("filename") or "contract.txt")
        use_llm = bool(payload.get("use_llm", True))

        if payload.get("sample"):
            key = payload["sample"] if isinstance(payload["sample"], str) else "service"
            if key not in SAMPLE_FILES:
                return self._error(f"未知样例：{key}", 404)
            filename, display = SAMPLE_FILES[key]
            sample = SAMPLES / filename
            if not sample.exists():
                return self._error("样例合同不存在", 404)
            result = review.review_bytes(
                display, text=sample.read_text(encoding="utf-8-sig"), use_llm=use_llm
            )
            return self._send_json(result)

        if payload.get("text"):
            result = review.review_bytes(filename, text=str(payload["text"]), use_llm=use_llm)
            return self._send_json(result)

        encoded = payload.get("content_b64")
        if not encoded:
            return self._error("缺少文件内容：请提供 content_b64 或 text", 400)
        try:
            data = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("文件内容不是合法的 base64 编码")
        if not data:
            raise ValueError("文件内容为空")

        result = review.review_bytes(filename, data=data, use_llm=use_llm)
        return self._send_json(result)

    def _handle_export(self):
        payload = self._read_body()
        result = payload.get("result")
        if not isinstance(result, dict) or "findings" not in result:
            return self._error("缺少审查结果数据", 400)
        try:
            blob = report.build(result)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            return self._error("生成 Word 失败，请检查服务端是否安装 python-docx", 500)

        stem = os.path.splitext(str(result.get("filename") or "contract"))[0]
        return self._send_json(
            {
                "filename": f"{stem}_审查意见书.docx",
                "content_b64": base64.b64encode(blob).decode("ascii"),
            }
        )

    # ---------------------------------------------------------------- 静态
    def _serve_file(self, file_path: Path):
        try:
            resolved = file_path.resolve()
            if WEB.resolve() not in resolved.parents and resolved != WEB.resolve():
                return self._error("禁止访问", 403)
            if not resolved.is_file():
                return self._error("文件不存在", 404)
            body = resolved.read_bytes()
        except OSError:
            return self._error("文件不存在", 404)
        content_type = MIME.get(resolved.suffix.lower(), "application/octet-stream")
        if resolved.name == "manifest.json":
            content_type = MIME[".webmanifest"]
        return self._send(HTTPStatus.OK, body, content_type)


_ENV_FROM_FILE: set[str] = set()


def _load_env_file() -> None:
    """兼容旧调用点：真正的实现在 app/env.py。"""
    from .env import load_env_file

    load_env_file()


def main(host: str = "127.0.0.1", port: int = 8765):
    _load_env_file()
    review.resources()  # 预热，启动即暴露数据加载错误
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    print(f"合同审查服务已启动： http://{host}:{port}")
    print("按 Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        server.server_close()


if __name__ == "__main__":
    sys.exit(main())
