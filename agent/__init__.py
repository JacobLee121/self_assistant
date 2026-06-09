"""通用 AI 助手 — Google ADK + DeepSeek API + MCP 工具。

核心设计:
  - agent.py : 通用 Agent，通过 McpToolset 连接本地 MCP 服务器获取工具
  - config.py: MCP 服务器配置（声明连接哪些 MCP 服务）
  - logger.py: ADK 事件日志记录器（LLM 推理 + 工具调用全过程）

工具能力由连接的 MCP 服务器决定，Agent 本身不硬编码任何具体工具。
"""
