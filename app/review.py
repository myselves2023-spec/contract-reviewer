# -*- coding: utf-8 -*-
"""审查编排：解析 -> 规则扫描 -> （可选）LLM 增强 -> 评分 -> 结构化结果。"""
from __future__ import annotations

import hashlib
import time

from . import llm
from .checklist import StatuteBook, load_checklist, scan
from .parsing import extract

DISCLAIMER = (
    "本报告由程序自动生成，基于公开法条与预设审查规则，仅供内部初筛参考，"
    "不构成正式法律意见。合同涉及重大权益的，请交由执业律师复核。"
)

LEVELS = (
    (85, "低风险", "未发现明显问题，建议常规复核后签署。"),
    (70, "中低风险", "存在少量可改进条款，建议逐条确认后签署。"),
    (50, "较高风险", "存在多处需要修改的条款，建议修改后再签署。"),
    (0, "高风险", "存在可能导致条款无效或明显不利的重大问题，建议重点谈判。"),
)

_BOOK = None
_CHECKPOINTS = None


def resources():
    """惰性加载，避免每次请求都读盘。"""
    global _BOOK, _CHECKPOINTS
    if _BOOK is None:
        _BOOK = StatuteBook()
    if _CHECKPOINTS is None:
        _CHECKPOINTS = load_checklist()
    return _BOOK, _CHECKPOINTS


def _level_for(score: int):
    for threshold, label, advice in LEVELS:
        if score >= threshold:
            return label, advice
    return "高风险", LEVELS[-1][2]


def _build_offline_comment(findings: list[dict], stats: dict, level: str) -> str:
    if not findings:
        return "规则层未命中预设风险点。这不等于合同无风险，仍建议人工复核。"
    top = [f["name"] for f in findings if f["severity"] == "high"][:3]
    head = f"共命中 {stats['total']} 项关注点，其中高风险 {stats['high']} 项、中风险 {stats['medium']} 项。"
    if top:
        head += "优先处理：" + "、".join(top) + "。"
    return head + f"整体评级：{level}。"


def review_bytes(filename: str, data: bytes | None = None, text: str | None = None,
                 use_llm: bool = True) -> dict:
    book, checkpoints = resources()

    if text is not None:
        # 直接传入文本（用于内置样例/接口调试），仍然构造统一的分段结构
        from .parsing import _clean  # 复用清洗逻辑

        paragraphs = _clean(text.splitlines())
        if not paragraphs:
            from .parsing import ParseError

            raise ParseError("文本为空。")
        segments, parts, pos = [], [], 0
        for paragraph in paragraphs:
            start = pos
            parts.append(paragraph)
            pos += len(paragraph)
            segments.append({"index": len(segments), "text": paragraph, "start": start, "end": pos})
            parts.append("\n")
            pos += 1
        document = {
            "filename": filename,
            "text": "".join(parts),
            "segments": segments,
            "chars": pos,
            "paragraphs": len(segments),
        }
    else:
        if data is None:
            raise ValueError("data 与 text 不能同时为空")
        document = extract(filename, data)

    findings = scan(checkpoints, document["text"])

    stats = {"high": 0, "medium": 0, "low": 0, "total": len(findings)}
    for finding in findings:
        stats[finding["severity"]] += 1

    score = max(0, 100 - sum(f["weight"] for f in findings))
    level, advice = _level_for(score)

    engine = {
        "rules": True,
        "llm": False,
        "llm_model": "",
        "llm_prompt": "",
        "llm_verdicts": {},
        "llm_latency_ms": 0,
        "llm_error": "",
    }
    overall = _build_offline_comment(findings, stats, level)

    if use_llm and llm.available() and findings:
        statutes_by_id = {
            finding["id"]: [book.get(sid) for sid in finding["statute_ids"] if book.get(sid)]
            for finding in findings
        }
        outcome = llm.enrich(findings, document["segments"], statutes_by_id)
        outcome_stats = outcome.get("stats") or {}

        engine["llm"] = bool(outcome.get("available"))
        engine["llm_model"] = outcome_stats.get("model", "")
        engine["llm_prompt"] = outcome_stats.get("prompt", "")
        engine["llm_verdicts"] = outcome_stats.get("verdicts", {})
        engine["llm_latency_ms"] = outcome_stats.get("latency_ms", 0)
        if outcome.get("errors"):
            engine["llm_error"] = "；".join(outcome["errors"][:3])

        patches = outcome.get("items") or {}
        for finding in findings:
            patch = patches.get(finding["id"])
            if patch:
                finding.update(patch)
                finding["detected_by"] = "rule+llm"

        if engine["llm"]:
            verdicts = engine["llm_verdicts"]
            reviewed = sum(verdicts.values())
            overall = (
                f"{overall} 大模型复核 {reviewed} 项：确认 {verdicts.get('confirm', 0)} 项、"
                f"排除 {verdicts.get('dismiss', 0)} 项、存疑 {verdicts.get('uncertain', 0)} 项。"
            )
            stats["dismissed"] = sum(
                1 for f in findings if f.get("llm_verdict") == "dismiss"
            )

    for finding in findings:
        finding["statutes"] = book.resolve(finding.pop("statute_ids"))

    digest = hashlib.sha256(document["text"].encode("utf-8")).hexdigest()[:12]

    return {
        "review_id": f"CR-{int(time.time())}-{digest[:6]}",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "filename": document["filename"],
        "contract": {
            "text": document["text"],
            "segments": document["segments"],
            "chars": document["chars"],
            "paragraphs": document["paragraphs"],
        },
        "engine": engine,
        "score": score,
        "risk_level": level,
        "advice": advice,
        "stats": stats,
        "findings": findings,
        "overall_comment": overall,
        "disclaimer": DISCLAIMER,
    }
