"""MCP 服务器连接配置。

声明 Agent 应该连接哪些 MCP 服务器（本地和远程）。
每增加一个 MCP 服务器，Agent 就自动获得其提供的所有工具。

连接类型说明:
  - StdioConnectionParams: 本地进程 MCP（通过标准输入/输出通信）
  - StreamableHTTPConnectionParams: 远程 HTTP MCP（通过 HTTP 协议通信，如 Tavily 搜索）
"""

from mcp import StdioServerParameters
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StdioConnectionParams,
    StreamableHTTPConnectionParams,
)

MCP_SERVERS: list[StdioConnectionParams | StreamableHTTPConnectionParams] = [
    # ── 本地 MCP 服务器 ─────────────────────────
    StdioConnectionParams(
        server_params=StdioServerParameters(
            command="python",
            args=["mcp_servers/weather_server.py"],
        ),
        timeout=10.0,
    ),
    StdioConnectionParams(
        server_params=StdioServerParameters(
            command="python",
            args=["mcp_servers/route_server.py"],
        ),
        timeout=10.0,
    ),
    # ── 远程 MCP 服务器 ─────────────────────────
    StreamableHTTPConnectionParams(
        url="https://mcp.tavily.com/mcp/?tavilyApiKey=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",
        timeout=30.0,
        sse_read_timeout=60.0,
    ),
]
