"""MCP 服务器连接配置。

声明 Agent 应该连接哪些本地 MCP 服务器。
每增加一个 MCP 服务器，Agent 就自动获得其提供的所有工具。
"""

from mcp import StdioServerParameters
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams

# 本地 MCP 服务器列表
# 每个条目代表一个独立的 MCP 服务器进程
# StdioConnectionParams 封装了 StdioServerParameters + timeout
MCP_SERVERS: list[StdioConnectionParams] = [
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
]
