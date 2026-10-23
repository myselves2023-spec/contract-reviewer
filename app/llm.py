# -*- coding: utf-8 -*-
"""LLM 层（可选增强）：OpenAI 兼容端点，逐条复核审查点。

与「把整份合同丢给模型」的做法相比，这里做了三个刻意的设计：

1. **逐个审查点单独判定**。每次只发该审查点命中的条款 + 上下文段落 + 相关法条，
   上下文短、锚点明确，模型不容易跑题，token 成本也低一个数量级。
2. **允许模型否决规则层**（verdict=dismiss）。规则层高召回、低精度，LLM 负责
   把这部分误报挡掉；被否决的项不会删除，只是打标记，保留可追溯性。
3. **法条只由规则层提供**。这个函数只把法条原文塞进 prompt 当依据，从不要求模型
   "检索"法条，从架构上消除编造条文的可能。

任何失败（超时、额度、返回非 JSON、字段不合法）都降级为「不可用」，审查流程继续。
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

PROMPT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "prompts")

VALID_VERDICTS = ("confirm", "dismiss", "uncertain")
VALID_REMEDIES = ("delete", "insert", "local-replace", "replace", "comment", "report-only")
MAX_ITEMS = 12
DEFAULT_PROMPT = "review_v1"

# 中文输入法常见的全角标点。曾经因为 LLM_BASE_URL 里混进全角冒号（：），
# 部署后所有模型调用都静默失败，报错只写 "unknown url type"。
_FULLWIDTH = str.maketrans({
    "：": ":",
    "／": "/",
    "．": ".",
    "　": " ",
    "\u00a0": " ",
})


def normalize_base_url(value: str) -> str:
    """纠正配置里误输入的全角标点，去掉尾部斜杠，并把公网的 http 升级为 https。

    公网 API 端点几乎都只认真 https：写成 http 会 302 跳转，而 urllib 跟随
    重定向时会把 POST 改成 GET，导致调用失败且报错难懂。本地/内网地址保持原样。
    """
    text = (value or "").translate(_FULLWIDTH).strip().rstrip("/")
    if text.startswith("http://"):
        host = (urlparse(text).hostname or "").lower()
        private = (
            not host
            or host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
            or host.startswith(("192.168.", "10.", "172.16.", "172.17.", "172.18.",
                                "172.19.", "172.2", "172.30.", "172.31."))
        )
        if not private:
            text = "https://" + text[len("http://"):]
    return text


def config() -> dict:
    return {
        "base_url": normalize_base_url(os.environ.get("LLM_BASE_URL") or ""),
        "api_key": (os.environ.get("LLM_API_KEY") or "").strip(),
        "model": (os.environ.get("LLM_MODEL") or "deepseek-chat").strip(),
        "timeout": int(os.environ.get("LLM_TIMEOUT") or 45),
        "retries": int(os.environ.get("LLM_RETRIES") or 2),
        "concurrency": max(1, int(os.environ.get("LLM_CONCURRENCY") or 4)),
        "prompt": (os.environ.get("LLM_PROMPT") or DEFAULT_PROMPT).strip(),
        "temperature": float(os.environ.get("LLM_TEMPERATURE") or 0.2),
        "max_items": int(os.environ.get("LLM_MAX_ITEMS") or MAX_ITEMS),
    }


# 占位符不算有效 key，否则照抄 .env.example 会导致每次审查都卡在超时上
PLACEHOLDER_KEYS = {"", "sk-your-key-here", "sk-xxx", "your-key", "changeme", "test"}


def available() -> bool:
    if os.environ.get("LLM_DISABLE") == "1":
        return False
    cfg = config()
    if not cfg["base_url"] or cfg["api_key"].strip().lower() in PLACEHOLDER_KEYS:
        return False
    return True


# ------------------------------------------------------------------ prompt

_PROMPT_CACHE: dict[str, tuple[str, str]] = {}


def load_prompt(name: str) -> tuple[str, str]:
    """返回 (system, user_template)。prompt 放在 data/prompts 下，改文案不用动代码。"""
    if name in _PROMPT_CACHE:
        return _PROMPT_CACHE[name]
    system_path = os.path.join(PROMPT_DIR, f"{name}.system.txt")
    user_path = os.path.join(PROMPT_DIR, f"{name}.user.txt")
    with open(system_path, encoding="utf-8-sig") as fh:
        system = fh.read().strip()
    with open(user_path, encoding="utf-8-sig") as fh:
        user = fh.read().strip()
    _PROMPT_CACHE[name] = (system, user)
    return system, user


def build_user_prompt(template: str, *, finding: dict, context: str, statutes: list[dict]) -> str:
    statute_block = "\n".join(
        f'{i}. 《民法典》{s["article"]}\n{s["text"]}' for i, s in enumerate(statutes, 1)
    ) or "（本审查点无直接对应法条，请仅依据合同条款本身判断。）"

    evidence = "；".join(ev["text"] for ev in finding.get("evidence") or []) or "全文未检索到对应条款（缺失型）"

    return (
        template.replace("{{ID}}", finding["id"])
        .replace("{{NAME}}", finding["name"])
        .replace("{{SEVERITY}}", finding.get("severity_label", ""))
        .replace("{{EVIDENCE}}", evidence)
        .replace("{{CONTEXT}}", context or "（未定位到具体条款，本审查点按条款缺失处理）")
        .replace("{{STATUTES}}", statute_block)
    )


def context_for(segments: list[dict], finding: dict, limit: int = 6) -> str:
    """组装该审查点的相关条款：命中条款 + 规则层为判定该审查点而匹配到的其他条款。

    这里刻意不是「命中段前后各一段」——跨条款的问题（例如违约金与定金并存）
    必须把另一条也看到，否则模型会据局部片段臆断全文。
    """
    offsets = [ev["start"] for ev in finding.get("evidence") or []]
    offsets += [item["start"] for item in finding.get("related") or []]
    if not offsets:
        return ""

    indices = []
    for offset in offsets:
        for segment in segments:
            if segment["start"] <= offset < segment["end"]:
                indices.append(segment["index"])
                break

    ordered = sorted(set(indices))[:limit]
    if not ordered:
        return ""
    return "\n".join(segments[i]["text"] for i in ordered)


# ------------------------------------------------------------------ 调用

def _post(cfg: dict, body: dict) -> dict:
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    if not url.startswith(("http://", "https://")):
        raise ValueError(
            f"LLM_BASE_URL 格式不正确：{cfg['base_url']!r}，应形如 https://api.deepseek.com/v1"
        )
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg['api_key']}",
        },
    )
    with urllib.request.urlopen(request, timeout=cfg["timeout"]) as response:
        return json.loads(response.read().decode("utf-8"))


def _chat(system: str, user: str, cfg: dict) -> dict:
    body = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": cfg["temperature"],
        "stream": False,
        "response_format": {"type": "json_object"},
    }

    delay = 1.0
    attempt = 0
    last_error: Exception | None = None
    while attempt <= cfg["retries"]:
        try:
            return _post(cfg, body)
        except urllib.error.HTTPError as exc:
            last_error = exc
            # 不是所有 OpenAI 兼容端点都支持 response_format。
            # 遇到 400 时去掉该参数立即重试一次——这次不消耗重试次数。
            if exc.code == 400 and "response_format" in body:
                body.pop("response_format", None)
                continue
            if exc.code not in (408, 429, 500, 502, 503, 504) or attempt >= cfg["retries"]:
                raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt >= cfg["retries"]:
                raise
        attempt += 1
        time.sleep(delay)
        delay *= 2
    raise last_error or RuntimeError("LLM 调用失败")


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        return json.loads(text[start : end + 1])
    raise ValueError("模型返回内容不是合法 JSON")


def _normalize_result(payload: dict) -> dict:
    verdict = str(payload.get("verdict") or "").strip().lower()
    if verdict not in VALID_VERDICTS:
        verdict = "uncertain"

    try:
        confidence = float(payload.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = min(1.0, max(0.0, confidence))

    analysis = str(payload.get("analysis") or "").strip()[:300]
    revised = str(payload.get("revised_clause") or "").strip()[:1200]
    if verdict != "confirm":
        revised = ""

    remedy = str(payload.get("remedy") or "").strip().lower()
    if remedy not in VALID_REMEDIES:
        remedy = ""  # 交给上层用规则层推断的默认值
    # 不改正文的动作不应该带建议条款
    if remedy in ("comment", "report-only") and verdict == "confirm":
        pass  # 允许「只提示」但仍保留条款供参考

    result = {
        "llm_verdict": verdict,
        "llm_confidence": round(confidence, 2),
        "llm_analysis": analysis,
        "revised_clause": revised,
    }
    if remedy:
        result["remedy"] = remedy
    return result


# ------------------------------------------------------------------ 编排

def _review_one(finding: dict, segments: list[dict], statutes: list[dict],
                system: str, template: str, cfg: dict) -> tuple[str, dict] | tuple[str, Exception]:
    user = build_user_prompt(
        template,
        finding=finding,
        context=context_for(segments, finding),
        statutes=statutes,
    )
    try:
        response = _chat(system, user, cfg)
        content = response["choices"][0]["message"]["content"]
        return finding["id"], _normalize_result(_extract_json(content))
    except Exception as exc:  # noqa: BLE001 - 单条失败不应拖垮整体
        return finding["id"], exc


def enrich(findings: list[dict], segments: list[dict], statutes_by_id: dict) -> dict:
    """逐条复核。返回 {available, items, stats, errors}。"""
    if not available() or not findings:
        return {"available": False, "items": {}, "stats": {}, "errors": []}

    cfg = config()
    try:
        system, template = load_prompt(cfg["prompt"])
    except OSError as exc:
        return {"available": False, "items": {}, "stats": {},
                "errors": [f"prompt 文件加载失败：{exc}"]}

    order = {"high": 0, "medium": 1, "low": 2}
    shortlist = sorted(findings, key=lambda f: (order.get(f.get("severity"), 9), f["id"]))
    shortlist = shortlist[: cfg["max_items"]]

    started = time.time()
    items: dict[str, dict] = {}
    errors: list[str] = []

    with ThreadPoolExecutor(max_workers=cfg["concurrency"]) as pool:
        futures = [
            pool.submit(
                _review_one,
                finding,
                segments,
                statutes_by_id.get(finding["id"], []),
                system,
                template,
                cfg,
            )
            for finding in shortlist
        ]
        for future in futures:
            key, value = future.result()
            if isinstance(value, Exception):
                errors.append(f"{key}: {type(value).__name__}: {value}")
            else:
                items[key] = value

    verdicts = {v: 0 for v in VALID_VERDICTS}
    for item in items.values():
        verdicts[item["llm_verdict"]] += 1

    return {
        "available": bool(items),
        "items": items,
        "stats": {
            "model": cfg["model"],
            "prompt": cfg["prompt"],
            "reviewed": len(shortlist),
            "succeeded": len(items),
            "verdicts": verdicts,
            "latency_ms": int((time.time() - started) * 1000),
            "concurrency": cfg["concurrency"],
        },
        "errors": errors,
    }
