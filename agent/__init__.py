"""通用 AI 助手 — Google ADK + Compass/DeepSeek + MCP + ADK Skills。

核心设计:
  - agent.py     : 通用 Agent，组合 McpToolset、SkillToolset 和模型配置
  - config.py    : MCP 服务器配置（声明连接哪些 MCP 服务）
  - llm_config.py: LLM provider/model/API 配置，支持 Compass 和 DeepSeek
  - llm_trace.py : 捕获每次 ADK LLM request，用于日志记录完整模型输入
  - langfuse_trace.py: 可选导出 Langfuse traces
  - skills.py    : 加载 skills/ 下的项目内 ADK Skills
  - logger.py    : ADK 事件日志记录器（LLM 推理 + 工具调用全过程）

工具能力由连接的 MCP 服务器和项目内 ADK Skills 决定，Agent 本身不硬编码具体业务函数。
"""
