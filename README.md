# 🤖 Self Assistant

基于 **Google ADK** + **DeepSeek API** 的通用 AI 助手，通过 **本地 MCP 服务器** 动态获取工具能力。

## 核心设计理念

```
┌──────────────────────────────────────────────────────────────┐
│                      通用 AI 助手 (Agent)                      │
│                                                              │
│  身份是通用的，不绑定任何具体领域                                │
│  能力由连接的 MCP 服务器动态决定                                │
│                                                              │
│  tools: [McpToolset(weather), McpToolset(route), ...]        │
│           ↑ 通过 stdio 连接 ↑                                 │
│  ┌──────────────────┐  ┌──────────────────┐  ┌─────────────┐ │
│  │ weather_server   │  │  route_server    │  │  (更多...)   │ │
│  │ get_weather()    │  │  get_route()     │  │             │ │
│  │ (Mock 天气数据)   │  │  list_cities()   │  │             │ │
│  └──────────────────┘  └──────────────────┘  └─────────────┘ │
│      独立进程              独立进程             独立进程       │
└──────────────────────────────────────────────────────────────┘
```

**关键区别**：工具不再硬编码在 Agent 内部（如 `FunctionTool(get_weather)`），而是通过 MCP 协议从独立进程中动态获取。增减 MCP 服务器即可扩展/缩减 Agent 的能力。

## 📁 项目结构

```
self-assistant/
├── main.py                       # 入口：交互式 CLI + 日志记录
├── agent/
│   ├── __init__.py               # 包声明
│   ├── agent.py                  # 通用 Agent（McpToolset → MCP 服务器）
│   ├── config.py                 # MCP 服务器连接配置
│   └── logger.py                 # ADK 事件日志记录器
├── mcp_servers/                  # MCP 工具服务器（独立进程，标准协议）
│   ├── __init__.py
│   ├── weather_server.py         # 天气 MCP 服务器（get_weather）
│   └── route_server.py           # 路线 MCP 服务器（get_route + list_cities）
├── logs/                         # 【运行时生成】调用过程日志
├── pyproject.toml                # 依赖声明
├── .env.example                  # API Key 配置模板
└── .gitignore
```

## 🏗️ 架构

### ADK × MCP 工具调用流程

```
用户输入 "北京天气 + 北京到上海路线"
  │
  ▼
Runner.run_async()
  │
  ├─▶ [LLM Call #1] DeepSeek 推理
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
  ├─▶ [LLM Call #2] DeepSeek 推理 → 格式化天气 + 路线信息
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

## 🔧 技术栈

| 组件 | 选型 | 说明 |
|------|------|------|
| Agent 框架 | Google ADK | 统一的 Agent 定义和 Runner 运行时 |
| LLM 模型 | DeepSeek Chat | 通过 LiteLLM 适配层接入 |
| 模型适配 | LiteLlm | ADK 内置的多模型适配器 |
| 工具协议 | MCP (Model Context Protocol) | stdio JSON-RPC，标准化工具通信 |
| 工具框架 | McpToolset (ADK) | 将 MCP 工具自动转换为 ADK Agent 可调用的工具 |
| MCP SDK | mcp (Python) | MCP 服务器端 SDK |
| 会话存储 | InMemorySessionService | 内存会话（不持久化） |
| 日志记录 | AgentLogger（自建） | 捕获 LLM 推理和工具调用全过程 |

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install google-adk litellm mcp
```

### 2. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY
```

> API Key 获取地址: https://platform.deepseek.com/api_keys

### 3. 运行 Agent（交互式 CLI）

```bash
python main.py
```

Agent 启动时会自动连接 `agent/config.py` 中配置的所有 MCP 服务器，
并在启动界面显示已连接的工具列表。

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

运行后在 `logs/` 目录下查看 `<session_id>.json` 文件，包含每轮对话的完整 LLM 推理和工具调用过程。

## 📝 变更记录

| 日期 | 变更 | 说明 |
|------|------|------|
| 2026-06-08 | 项目初始化 | Google ADK + Gemini API |
| 2026-06-08 | 切换模型 | Gemini → DeepSeek API（通过 LiteLLM） |
| 2026-06-08 | 新增日志 | AgentLogger 记录 LLM/工具调用全过程 |
| 2026-06-09 | 新增 MCP 天气服务器 | `mcp_servers/weather_server.py` — 通过 MCP 协议暴露 get_weather |
| 2026-06-09 | 新增 MCP 路线服务器 | `mcp_servers/route_server.py` — 提供 get_route + list_cities，支持 Haversine 球面距离 |
| 2026-06-09 | **架构重构** | Agent 从 FunctionTool 硬编码改为 McpToolset 动态获取 MCP 工具；重命名 `weather_agent/` → `agent/`；Agent 身份从"天气助手"改为"通用 AI 助手" |
