# 🤖 Self Assistant

基于 **Google ADK** + **Compass API / DeepSeek API** 的通用 AI 助手，通过 **本地 MCP 服务器** 动态获取工具能力。

## 核心设计理念

```
┌──────────────────────────────────────────────────────────────┐
│                      通用 AI 助手 (Agent)                      │
│                                                              │
│  身份是通用的，不绑定任何具体领域                                │
│  能力由连接的 MCP 服务器动态决定                                │
│                                                              │
│  tools: [McpToolset(weather), McpToolset(route), SkillToolset]│
│           ↑ 通过 stdio 连接 ↑              ↑ 加载 skills/       │
│  ┌──────────────────┐  ┌──────────────────┐  ┌─────────────┐ │
│  │ weather_server   │  │  route_server    │  │  (更多...)   │ │
│  │ get_weather()    │  │  get_route()     │  │             │ │
│  │ (Mock 天气数据)   │  │  list_cities()   │  │             │ │
│  └──────────────────┘  └──────────────────┘  └─────────────┘ │
│      独立进程              独立进程             独立进程       │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ skills/                                                  │ │
│  │ travel-route-planner, sichuan-cooking                    │ │
│  │ → list_skills / load_skill / load_skill_resource         │ │
│  └──────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

**关键区别**：工具不再硬编码在 Agent 内部（如 `FunctionTool(get_weather)`），而是通过 MCP 协议从独立进程中动态获取。任务流程指南通过 ADK SkillToolset 从 `skills/` 加载。增减 MCP 服务器或项目内 Skill 即可扩展/缩减 Agent 的能力。

## 📁 项目结构

```
self-assistant/
├── main.py                       # 入口：交互式 CLI + 日志记录
├── agent/
│   ├── __init__.py               # 包声明
│   ├── agent.py                  # 通用 Agent（McpToolset → MCP 服务器）
│   ├── config.py                 # MCP 服务器连接配置
│   ├── langfuse_trace.py         # 可选导出 Langfuse traces
│   ├── llm_config.py             # LLM provider/model/API 配置
│   ├── llm_trace.py              # 捕获完整 LLM request 供日志记录
│   ├── skills.py                 # ADK SkillToolset 加载项目内 Skills
│   └── logger.py                 # ADK 事件日志记录器
├── mcp_servers/                  # MCP 工具服务器（独立进程，标准协议）
│   ├── __init__.py
│   ├── weather_server.py         # 天气 MCP 服务器（get_weather）
│   └── route_server.py           # 路线 MCP 服务器（get_route + list_cities + 周边/对比）
├── skills/                       # ADK Agent Skills（通过 SkillToolset 加载）
│   ├── travel-route-planner/     # 旅游路线、天气、周边城市规划
│   └── sichuan-cooking/          # 四川菜做法指导
├── logs/                         # 【运行时生成】调用过程日志
├── pyproject.toml                # 依赖声明
├── .env.example                  # API Key 配置模板
└── .gitignore
```

## 🏗️ 架构

### ADK × Skill × MCP 调用流程

```
用户输入 "北京天气 + 北京到上海路线"
  │
  ▼
Runner.run_async()
  │
  ├─▶ before_model_callback
  │     → 注入 skills/ 中的项目内 ADK Skill instructions
  │
  ├─▶ [LLM Call #1] Compass / DeepSeek 推理
  │     → 匹配 travel-route-planner
  │     → 调用 load_skill("travel-route-planner")
  │
  ├─▶ [SkillToolset] 返回 travel-route-planner 完整 instructions
  │
  ├─▶ [LLM Call #2] Compass / DeepSeek 推理
  │     → 决定调用 get_weather("北京")
  │     → 决定调用 get_route("北京", "上海")
  │       │
  │       │  McpToolset 通过 stdio 协议
  │       │  向 MCP 服务器子进程发送 JSON-RPC 请求
  │       ▼
  ├─▶ [MCP: weather_server] get_weather → Mock 天气数据
  ├─▶ [MCP: route_server]  get_route    → Mock 路线数据
  │       │
  │       ▼
  ├─▶ [LLM Call #3] Compass / DeepSeek 推理 → 按 Skill 格式输出路线 + 天气
  │       │
  │       ▼
  └─▶ 最终输出给用户
```

### 两种工具方案对比

| 维度 | FunctionTool (旧方案) | McpToolset (新方案) |
|------|---------------------|---------------------|
| 工具来源 | Agent 内硬编码 | 动态从 MCP 服务器获取 |
| Agent 身份 | 绑定具体领域（天气助手） | 通用助手 |
| 扩展能力 | 需修改 agent.py 代码 | 在 config.py 加一行 MCP 服务器配置 |
| 工具复用 | 仅此 Agent 可用 | 任何 MCP 客户端可复用 |
| 进程隔离 | 同进程内调用 | 独立子进程，故障隔离 |

### 如何新增工具能力

只需两步，不需要修改 Agent 代码：

```python
# 1. 编写 MCP 服务器（或使用已有的）
# 2. 在 agent/config.py 中添加一行
MCP_SERVERS.append(
    StdioConnectionParams(
        server_params=StdioServerParameters(
            command="python",
            args=["mcp_servers/my_new_server.py"],
        ),
    )
)
```

Agent 重启后自动获得新工具。

### ADK Agent Skills

`skills/` 目录存放 ADK Agent 可动态加载的任务指南。启动时 `agent/skills.py` 会读取 `skills/*/SKILL.md`，创建 `SkillToolset`，并向 Agent 暴露以下工具：

- `list_skills`
- `load_skill`
- `load_skill_resource`

当用户问题匹配某个 skill 时，模型应先调用 `load_skill` 读取完整说明，再按说明调用 MCP 工具或生成回答。

另外，Agent 使用 ADK `before_model_callback` 将项目内 skills 作为运行时 instruction 注入每次模型请求，确保这些 skills 对当前 Agent 生效，而不是只作为 Codex 开发环境技能存在。

| Skill | 用途 |
|------|------|
| `travel-route-planner` | 根据已有 MCP 工具规划旅游路线、查询天气、对比出行方式、查找周边城市 |
| `sichuan-cooking` | 输出四川菜家常做法、调味原则、替代方案和安全注意 |

## 🔧 技术栈

| 组件 | 选型 | 说明 |
|------|------|------|
| Agent 框架 | Google ADK | 统一的 Agent 定义和 Runner 运行时 |
| LLM 模型 | Compass Gemini / DeepSeek Chat | 通过 LiteLLM 适配层接入，默认走 Compass OpenAI-compatible 路由 |
| 模型适配 | LiteLlm | ADK 内置的多模型适配器 |
| 工具协议 | MCP (Model Context Protocol) | stdio JSON-RPC，标准化工具通信 |
| 工具框架 | McpToolset (ADK) | 将 MCP 工具自动转换为 ADK Agent 可调用的工具 |
| Skill 框架 | SkillToolset (ADK) | 将 `skills/*/SKILL.md` 暴露为 ADK 可加载的 Agent Skills |
| MCP SDK | mcp (Python) | MCP 服务器端 SDK |
| Trace 平台 | Langfuse（可选） | 将每个 Turn 导出为 trace，LLM call 导出为 generation，工具结果导出为 tool span |
| 会话存储 | InMemorySessionService | 内存会话（不持久化） |
| 日志记录 | AgentLogger（自建） | 捕获 LLM 推理和工具调用全过程 |

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install google-adk litellm mcp langfuse
```

### 2. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入 COMPASS_API_KEY
```

默认使用 Compass：

```bash
LLM_PROVIDER=compass
COMPASS_API_KEY=your-compass-api-key
COMPASS_MODEL=gemini-2.5-flash
```

如需切回 DeepSeek：

```bash
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your-deepseek-api-key
DEEPSEEK_MODEL=deepseek-chat
```

可选：启用 Langfuse trace：

```bash
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://langfuse-poc.data-infra.shopee.io
LANGFUSE_FLUSH_AT_EXIT=true
LANGFUSE_FLUSH_EACH_TURN=false
LANGFUSE_TIMEOUT=30
LANGFUSE_MAX_INPUT_LEN=100000000
LANGFUSE_MAX_OUTPUT_LEN=400000000
```

Langfuse credentials 必须来自你的 Langfuse project；仓库不会保存真实 key。参考实现的默认 host 是 Shopee 内部 `langfuse-poc.data-infra.shopee.io`。
默认不在每轮结束后强制 `flush()`，避免内部 Langfuse 网络慢时阻塞 CLI 或打印 OpenTelemetry read timeout；需要实时上报时再设置 `LANGFUSE_FLUSH_EACH_TURN=true`。

### 3. 运行 Agent（交互式 CLI）

```bash
python main.py
```

Agent 启动时会自动连接 `agent/config.py` 中配置的所有 MCP 服务器，
并在启动界面显示已连接的 MCP 服务、已加载的 ADK Skills 和 Langfuse trace 状态。

### 4. 独立运行 MCP 服务器

```bash
# 天气服务器
python mcp_servers/weather_server.py

# 路线服务器
python mcp_servers/route_server.py
```

### 5. 测试 MCP 工具（不依赖 LLM）

```bash
# 直接调用 mock 函数验证数据
python -c "from mcp_servers.weather_server import _get_weather; print(_get_weather('北京'))"
python -c "from mcp_servers.route_server import _plan_route; print(_plan_route('北京', '上海'))"

# 使用 MCP Inspector 可视化调试
npx @anthropic-ai/mcp-inspector python mcp_servers/weather_server.py
```

### 6. 查看调用日志

运行后在 `logs/` 目录下查看 `<session_id>.json` 文件，包含每轮对话的完整 LLM 输入、模型输出和工具调用过程。

每个 `LLM_CALL.input` 会记录真实发送给模型的结构化输入：

- `model`
- `system_instruction`
- `contents`
- `tools`
- `generation_config`

不再使用“系统提示词 + 对话历史 + 用户消息及之前的工具结果”这种摘要占位。

如果 `LANGFUSE_ENABLED=true` 且 Langfuse credentials 已配置，每轮对话也会导出到 Langfuse：

- Turn → `agent` observation
- LLM_CALL → `generation`
- TOOL_RESULT → `tool`

## 📝 变更记录

| 日期 | 变更 | 说明 |
|------|------|------|
| 2026-06-08 | 项目初始化 | Google ADK + Gemini API |
| 2026-06-08 | 切换模型 | Gemini → DeepSeek API（通过 LiteLLM） |
| 2026-06-08 | 新增日志 | AgentLogger 记录 LLM/工具调用全过程 |
| 2026-06-09 | 新增 MCP 天气服务器 | `mcp_servers/weather_server.py` — 通过 MCP 协议暴露 get_weather |
| 2026-06-09 | 新增 MCP 路线服务器 | `mcp_servers/route_server.py` — 提供 get_route + list_cities，支持 Haversine 球面距离 |
| 2026-06-09 | **架构重构** | Agent 从 FunctionTool 硬编码改为 McpToolset 动态获取 MCP 工具；重命名 `weather_agent/` → `agent/`；Agent 身份从"天气助手"改为"通用 AI 助手" |
| 2026-06-11 | 新增 Compass LLM 路由 | 默认通过 Compass OpenAI-compatible API 调用 Gemini 模型，保留 DeepSeek fallback |
| 2026-06-11 | 新增 ADK Agent Skills | 通过 SkillToolset 加载 `travel-route-planner` 和 `sichuan-cooking` 两个项目内 Skills |
| 2026-06-11 | 完善 LLM 日志输入 | `LLM_CALL.input` 记录完整 ADK LLM request，而不是摘要描述 |
| 2026-06-11 | 新增 Langfuse trace 导出 | 可选将本地 turn/LLM/tool 日志同步到 Langfuse 查看 trace |
