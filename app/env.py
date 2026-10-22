# -*- coding: utf-8 -*-
"""读取项目根目录的 .env。

只为了省掉 python-dotenv 这个依赖。特性：
- 支持 `KEY=VALUE`、`#` 注释、行首尾空白
- 记住哪些键来自文件：文件被修改后可以覆盖自己上次写入的值
- shell 里显式设置的变量优先级更高，不会被文件覆盖
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_ENV_FROM_FILE: set[str] = set()


def load_env_file(path: Path | None = None) -> None:
    env_path = path or (ROOT / ".env")
    if not env_path.exists():
        return
    try:
        content = env_path.read_text(encoding="utf-8-sig")
    except OSError:
        return

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        if key in os.environ and key not in _ENV_FROM_FILE:
            continue  # shell 变量优先
        os.environ[key] = value
        _ENV_FROM_FILE.add(key)
