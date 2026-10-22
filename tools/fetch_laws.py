# -*- coding: utf-8 -*-
"""从 LawRefBook/Laws 拉取法条，解析成 data/statutes.json。

默认只拉「民法典合同编」，因为合同审查用不到全库。想扩展就改 BOOKS。

用法：
  python tools/fetch_laws.py
  python tools/fetch_laws.py --books 总则 合同编 物权编
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "statutes_full.json"

BASE = "https://raw.githubusercontent.com/LawRefBook/Laws/master/民法典/"
DEFAULT_BOOKS = ["总则", "合同编"]

ARTICLE_RE = re.compile(r"^(第[一二三四五六七八九十百千零〇]+条)\s+(.*)$")
HEADING_RE = re.compile(r"^#{1,6}\s")

PREFIX = {"总则": "mfd-z", "合同编": "mfd-h"}


CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "三": 3, "四": 4,
             "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CN_UNITS = {"十": 10, "百": 100, "千": 1000}


def cn_to_int(text: str) -> int:
    """第四百七十 → 470。用于生成与 data/statutes.json 一致的 id。"""
    section = 0
    number = 0
    for char in text:
        if char in CN_DIGITS:
            number = CN_DIGITS[char]
        elif char in CN_UNITS:
            unit = CN_UNITS[char]
            section += (number or 1) * unit
            number = 0
        else:
            raise ValueError(f"无法解析的中文数字：{text!r}（字符 {char}）")
    return section + number


def fetch(book: str) -> str:
    url = BASE + urllib.parse.quote(book) + ".md"
    request = urllib.request.Request(url, headers={"User-Agent": "contract-reviewer/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8-sig")


def parse(text: str, book: str):
    articles = []
    current = None
    chapter = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("<!--"):
            continue
        if HEADING_RE.match(line):
            chapter = line.lstrip("#").strip()
            continue
        match = ARTICLE_RE.match(line)
        if match:
            if current:
                current["text"] = "\n".join(current["lines"]).strip()
                del current["lines"]
                articles.append(current)
            number = match.group(1)
            try:
                index = cn_to_int(number[1:-1])  # 去掉「第」「条」
            except ValueError:
                index = 0
            current = {
                # id 与 data/statutes.json 保持同一套命名，便于 checklist.json 引用
                "id": f"mfd-{index}" if index else f"mfd-{book}-{len(articles)}",
                "article": number,
                "book": f"{book} {chapter}".strip(),
                "lines": [match.group(2)],
            }
            continue
        if current is not None:
            current["lines"].append(line)
    if current:
        current["text"] = "\n".join(current["lines"]).strip()
        del current["lines"]
        articles.append(current)
    return articles


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--books", nargs="*", default=DEFAULT_BOOKS)
    parser.add_argument("--output", default=str(OUT))
    args = parser.parse_args()

    all_articles = []
    for book in args.books:
        print(f"抓取 民法典/{book}.md ...", end=" ")
        text = fetch(book)
        parsed = parse(text, book)
        print(f"{len(parsed)} 条")
        all_articles.extend(parsed)

    payload = {
        "meta": {
            "title": "中华人民共和国民法典",
            "effective": "2021-01-01",
            "source": "LawRefBook/Laws",
            "source_url": "https://github.com/LawRefBook/Laws",
            "note": "由 tools/fetch_laws.py 自动生成，条文正文未作改写。",
        },
        "articles": all_articles,
    }
    output = Path(args.output)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已写入 {output}（{len(all_articles)} 条）")
    print("如需替换默认库：改 app/checklist.py 中 StatuteBook 的默认路径，或把本文件复制为 data/statutes.json")


if __name__ == "__main__":
    main()
