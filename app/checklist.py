# -*- coding: utf-8 -*-
"""规则层：审查点加载、法条库查询、确定性扫描。

这一层刻意不用大模型。它的职责是「可解释、可回归测试」——同样的合同永远得到
同样的结果，便于做评测集和回归。语义判断交给可选的 LLM 层。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

SEVERITY_WEIGHT = {"high": 10, "medium": 5, "low": 2}
SEVERITY_LABEL = {"high": "高", "medium": "中", "low": "低"}

# 整改动作，借鉴 contract-copilot 的 revision-strategy：
# 识别风险要完整，改动正文要克制，优先最小必要动作。
REMEDY_LABEL = {
    "delete": "局部删减",
    "insert": "局部补入",
    "local-replace": "局部替换",
    "replace": "整条重写",
    "comment": "批注提示",
    "report-only": "仅入意见书",
}


def default_remedy(mode: str, severity: str) -> str:
    """没有模型参与时，按检查点性质推断整改动作。

    缺失型条款只能「补入」；命中型条款优先「局部替换」而不是整条重写；
    低风险且不涉及明确违法/失衡的，只做批注或仅入意见书。
    """
    if mode == "absent":
        return "insert"
    if severity in ("high", "medium"):
        return "local-replace"
    return "comment"


class StatuteBook:
    """民法典条文查询。只读 json，不做全文检索。"""

    def __init__(self, path: Path | None = None):
        self.path = path or (DATA / "statutes.json")
        with open(self.path, encoding="utf-8") as fh:
            self.raw = json.load(fh)
        self.meta = self.raw.get("meta", {})
        self.articles = {a["id"]: a for a in self.raw.get("articles", [])}

    def __len__(self):
        return len(self.articles)

    def get(self, article_id: str) -> dict | None:
        return self.articles.get(article_id)

    def cite(self, article_id: str) -> str:
        """法条简称，用于列表展示：民法典第五百八十五条。"""
        article = self.articles.get(article_id)
        if not article:
            return article_id
        return f'民法典{article["article"]}'

    def resolve(self, ids) -> list[dict]:
        out = []
        for article_id in ids or []:
            article = self.articles.get(article_id)
            if article:
                out.append(
                    {
                        "id": article_id,
                        "cite": self.cite(article_id),
                        "article": article["article"],
                        "book": article.get("book", ""),
                        "text": article["text"],
                    }
                )
        return out


class Checkpoint:
    __slots__ = ("raw", "id", "name", "category", "severity", "weight", "rationale",
                 "suggestion", "statutes", "mode", "_any", "_all", "_none")

    def __init__(self, raw: dict):
        self.raw = raw
        self.id = raw["id"]
        self.name = raw["name"]
        self.category = raw.get("category", "")
        self.severity = raw.get("severity", "medium")
        self.weight = int(raw.get("weight") or SEVERITY_WEIGHT.get(self.severity, 5))
        self.rationale = raw.get("rationale", "")
        self.suggestion = raw.get("suggestion", "")
        self.statutes = raw.get("statutes", [])
        detect = raw.get("detect") or {}
        self.mode = detect.get("mode", "present")
        self._any = [re.compile(p) for p in detect.get("any") or []]
        self._all = [re.compile(p) for p in detect.get("all") or []]
        self._none = [re.compile(p) for p in detect.get("none") or []]

    def evaluate(self, match_text: str):
        """返回 (triggered, primary_spans, related_spans)。

        primary_spans 用于前端高亮定位；related_spans 只喂给大模型做上下文，
        用来解决「跨条款」问题——例如 CP05 的触发词在违约责任条款，但判断它
        是否成立需要看到定金条款，后者通过 all 条件命中进入 related。

        match_text 与原文等长（仅换行被替换为空格），因此 span 可直接用于高亮。
        """
        any_hits = []
        for pattern in self._any:
            found = pattern.search(match_text)
            if found:
                any_hits.append(found)

        all_hits = []
        for pattern in self._all:
            found = pattern.search(match_text)
            if not found:
                return False, [], []
            all_hits.append(found)

        for pattern in self._none:
            if pattern.search(match_text):
                return False, [], []

        if self.mode == "absent":
            # 缺失型：应出现的关键词一个都没命中。没有可高亮的位置。
            if any_hits:
                return False, [], []
            return True, [], [(m.start(), m.end()) for m in all_hits]

        if self._any:
            if not any_hits:
                return False, [], []
            primary = [(any_hits[0].start(), any_hits[0].end())]
            related = [(m.start(), m.end()) for m in any_hits[1:] + all_hits]
            return True, primary, related

        # 纯条件型（如 CP09 要求出现「保证人」）：不产生高亮，但命中条款要进上下文，
        # 否则模型会在没有任何条款的情况下臆断"全文没有保证条款"。
        if not all_hits:
            return False, [], []
        return True, [], [(m.start(), m.end()) for m in all_hits]


def load_checklist(path: Path | None = None) -> list[Checkpoint]:
    path = path or (DATA / "checklist.json")
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    return [Checkpoint(item) for item in raw.get("checkpoints", [])]


def normalize(text: str) -> str:
    """等长规范化：换行替换为空格，保证偏移不变。"""
    return text.replace("\r\n", " \n").replace("\r", " ").replace("\n", " ")


def _expand_to_clause(text: str, start: int, end: int, limit: int = 400):
    """把命中片段扩展到所在整行（一条条款），避免只高亮三个字。

    行数超过 limit 时退回原始片段，防止整段合同被标黄。
    """
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end == -1:
        line_end = len(text)
    if 0 <= line_end - line_start <= limit:
        return line_start, line_end
    return start, end


def scan(checkpoints: list[Checkpoint], text: str) -> list[dict]:
    """对全文执行规则扫描，返回按严重度排序的风险列表。"""
    match_text = normalize(text)
    findings = []
    for cp in checkpoints:
        triggered, primary, related = cp.evaluate(match_text)
        if not triggered:
            continue

        evidence = []
        seen = set()
        for raw_start, raw_end in primary:
            # 注意：normalize 保留了长度，所以可以直接用原始 text 求行边界
            start, end = _expand_to_clause(text, raw_start, raw_end)
            snippet = match_text[start:end].strip()
            if not snippet or (start, end) in seen:
                continue
            seen.add((start, end))
            evidence.append({"start": start, "end": end, "text": snippet})

        # 相关条款：只作为大模型上下文，不在界面上高亮
        related_spans = []
        for raw_start, raw_end in related:
            start, end = _expand_to_clause(text, raw_start, raw_end)
            if not match_text[start:end].strip() or (start, end) in seen:
                continue
            seen.add((start, end))
            related_spans.append({"start": start, "end": end})
            if len(related_spans) >= 4:
                break
        findings.append(
            {
                "id": cp.id,
                "name": cp.name,
                "category": cp.category,
                "severity": cp.severity,
                "severity_label": SEVERITY_LABEL.get(cp.severity, cp.severity),
                "weight": cp.weight,
                "rationale": cp.rationale,
                "suggestion": cp.suggestion,
                "statute_ids": list(cp.statutes),
                "evidence": evidence,
                "evidence_kind": "clause" if evidence else "absence",
                "related": related_spans,
                "remedy": default_remedy(cp.mode, cp.severity),
                "detected_by": "rule",
            }
        )

    order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: (order.get(f["severity"], 9), f["id"]))
    return findings
