# -*- coding: utf-8 -*-
"""本地启动入口： python main.py [--port 8765]"""
from __future__ import annotations

import argparse
import os
import sys

from app.server import main

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="合同中风险审查工作台")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    # 部署平台（Render / Fly / 阿里云）会注入 PORT，必须优先用它
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    args = parser.parse_args()
    sys.exit(main(args.host, args.port))
