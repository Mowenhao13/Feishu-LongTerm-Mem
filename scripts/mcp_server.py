"""
MCP (Model Context Protocol) 服务器入口

通过 stdio 传输协议暴露决策记忆工具给 OpenClaw、Claude Desktop 等 MCP 客户端。

用法:
    python scripts/mcp_server.py

在 OpenClaw 中配置:
    openclaw mcp set feishu-mem '{
        "command": "uv",
        "args": ["run", "python", "scripts/mcp_server.py"],
        "cwd": "/Users/halllo/projects/local/feishu-mem"
    }'
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from src.mcp_server.server import run_server

if __name__ == "__main__":
    run_server()