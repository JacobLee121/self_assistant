"""通用 AI 助手 — 通过 McpToolset 连接本地 MCP 服务器获取工具能力。

与 weather_agent 的区别:
  - 旧: tools=[FunctionTool(get_weather)]  ← 工具硬编码，Agent 绑定具体函数
  - 新: tools=[McpToolset(weather_server), McpToolset(route_server)]  ← 工具来自 MCP

优势:
  1. Agent 身份是通用的，不绑定任何具体领域
  2. 通过增减 MCP 服务器即可扩展/缩减能力
  3. MCP 服务器可被任何 MCP 客户端复用（不只是 ADK）
"""

import os
from datetime import datetime, timezone

from mcp import StdioServerParameters
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.mcp_tool import McpToolset

from .config import MCP_SERVERS

# ── 模型配置 ──────────────────────────────────────

_raw_model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
if "/" not in _raw_model:
    _raw_model = f"deepseek/{_raw_model}"
DEEPSEEK_MODEL = _raw_model

# ── System Instruction ────────────────────────────

_CURRENT_DATE = datetime.now(timezone.utc).strftime("%Y 年 %m 月 %d 日")

SYSTEM_INSTRUCTION = f"""\
你是一个通用的 AI 助手，可以调用各种工具来帮助用户完成任务。

当前日期: {_CURRENT_DATE} (UTC)

工作原则:
1. 理解用户的意图，选择合适的工具来处理请求
2. 如果任务需要多个步骤，依次调用相关工具
3. 将工具返回的数据用中文友好地呈现给用户
4. 如果缺少必要信息（如城市名），请主动询问
5. 回复要简洁清晰，适当使用 emoji 和表格增强可读性
6. 如果用户的请求超出你现有工具的能力范围，诚实告知
"""

# ── 构建 McpToolset 列表 ─────────────────────────

def _build_toolsets() -> list[McpToolset]:
    """根据 config.py 中的 MCP_SERVERS 配置，创建对应的 McpToolset 列表。

    每个 MCP 服务器对应一个 McpToolset，Agent 通过它发现并调用该服务器上的工具。
    """
    toolsets: list[McpToolset] = []
    for server_params in MCP_SERVERS:
        toolset = McpToolset(connection_params=server_params)
        toolsets.append(toolset)
    return toolsets


# ── 创建 Agent 实例 ──────────────────────────────

assistant = Agent(
    name="assistant",
    model=LiteLlm(model=DEEPSEEK_MODEL),
    instruction=SYSTEM_INSTRUCTION,
    tools=_build_toolsets(),
)
