"""通用 AI 助手 — 通过 McpToolset 连接本地 MCP 服务器获取工具能力。

与 weather_agent 的区别:
  - 旧: tools=[FunctionTool(get_weather)]  ← 工具硬编码，Agent 绑定具体函数
  - 新: tools=[McpToolset(weather_server), McpToolset(route_server)]  ← 工具来自 MCP

优势:
  1. Agent 身份是通用的，不绑定任何具体领域
  2. 通过增减 MCP 服务器即可扩展/缩减能力
  3. MCP 服务器可被任何 MCP 客户端复用（不只是 ADK）
"""

from google.adk.agents import Agent
from google.adk.tools.mcp_tool import McpToolset

from .config import MCP_SERVERS
from .llm_config import create_lite_llm
from .llm_trace import capture_llm_request
from .skills import build_skill_toolset
from .skills import append_project_skills_to_request

# ── System Instruction ────────────────────────────

SYSTEM_INSTRUCTION = """\
你是一个通用的 AI 助手，可以调用各种工具来帮助用户完成任务。

工作原则:
1. 理解用户的意图，选择合适的工具来处理请求
2. 如果任务需要多个步骤，依次调用相关工具
3. 将工具返回的数据用中文友好地呈现给用户
4. 如果缺少必要信息（如城市名），请主动询问
5. 回复要简洁清晰，适当使用 emoji 和表格增强可读性
6. 如果用户的请求超出你现有工具的能力范围，诚实告知
7. 当用户请求与已列出的 skills 匹配时，必须先调用 load_skill 读取对应 skill，再按 skill 指南继续处理
"""

# ── 构建工具列表 ─────────────────────────────────

def _build_tools() -> list:
    """Create MCP toolsets plus the ADK skill toolset.

    MCP toolsets expose executable tools. SkillToolset exposes project-local
    instructions through ADK's `list_skills`, `load_skill`, and
    `load_skill_resource` tools.
    """
    tools: list = []
    for server_params in MCP_SERVERS:
        tools.append(McpToolset(connection_params=server_params))

    skill_toolset = build_skill_toolset()
    if skill_toolset:
        tools.append(skill_toolset)

    return tools


# ── 创建 Agent 实例 ──────────────────────────────

def _before_model_callback(callback_context, llm_request):
    """Inject project-local ADK skills before every model call."""
    append_project_skills_to_request(llm_request)
    capture_llm_request(llm_request)
    return None

assistant = Agent(
    name="assistant",
    model=create_lite_llm(),
    instruction=SYSTEM_INSTRUCTION,
    tools=_build_tools(),
    before_model_callback=_before_model_callback,
)
