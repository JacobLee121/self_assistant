"""通用 AI 助手 — DeepSeek API + Google ADK + 本地 MCP 服务器。

Agent 通过 McpToolset 连接本地 MCP 服务器，自动发现和调用其中的工具。
工具能力由 agent/config.py 中的 MCP_SERVERS 配置决定，Agent 本身不绑定具体工具。

每轮对话自动记录 LLM 推理和工具调用的完整过程到 logs/ 目录。
"""

import asyncio
import os
import sys
import warnings

# 静音 Google ADK 内部实验性功能的调试警告（不影响功能）
warnings.filterwarnings("ignore", message=".*EXPERIMENTAL.*")

# LiteLLM 默认会尝试向远端上报指标，网络不通时会超时报错，不影响功能但很碍眼
os.environ.setdefault("LITELLM_TELEMETRY", "False")
os.environ.setdefault("OUTDATED_PACKAGE_CHECK", "False")
# LiteLLM logging worker 会在后台 asyncio 任务超时时报 RED ERROR，
# 这里将它的日志级别提升到 CRITICAL 来隐藏这些无害的超时错误
import logging
logging.getLogger("LiteLLM").setLevel(logging.CRITICAL)

from dotenv import load_dotenv
from google.genai import types
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

# 启动时自动加载 .env 文件
load_dotenv()

from agent.agent import assistant
from agent.logger import AgentLogger
from agent.tracing import LangfuseTracer

# 全局日志记录器 & Langfuse 追踪器
logger = AgentLogger(log_dir="logs")
tracer = LangfuseTracer()


def check_api_key() -> bool:
    """检查 API Key 是否已配置。"""
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key or key.startswith("your-"):
        print("❌ 未检测到有效的 DEEPSEEK_API_KEY")
        print()
        print("请按以下步骤配置：")
        print("  1. 复制 .env.example 为 .env")
        print("     cp .env.example .env")
        print("  2. 编辑 .env，填入你的 API Key")
        print("     DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx")
        print("  3. API Key 获取地址: https://platform.deepseek.com/api_keys")
        print()
        return False
    return True


async def main():
    if not check_api_key():
        sys.exit(1)

    # 1. 创建会话服务（内存版本，不持久化）
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name="assistant_app",
        user_id="demo_user",
    )

    logger.start_session(session.id)
    tracer.start_session(session.id, user_id="demo_user")

    # 2. 创建 Runner
    runner = Runner(
        agent=assistant,
        app_name="assistant_app",
        session_service=session_service,
    )

    # 3. 交互式查询循环
    print("=" * 60)
    print("🤖 通用 AI 助手 (DeepSeek API + 本地 MCP 工具)")
    print("=" * 60)
    print("已连接的 MCP 服务：")
    print("  • weather  — 天气查询 (get_weather)")
    print("  • route    — 路线规划 (get_route, list_cities)")
    print("  • tavily   — 网络搜索 (tavily_search/tavily_extract/tavily_crawl/tavily_map/tavily_research)")
    print()
    print("输入 'quit' 退出")
    print("-" * 60)
    print()

    while True:
        try:
            user_input = input("👤 你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 再见！")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("👋 再见！")
            break

        print("\n🤖 助手: ", end="", flush=True)

        # 4. 构造用户消息
        user_content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_input)],
        )

        try:
            # ── 开始新的 Turn ──
            logger.start_turn(user_input)
            tracer.start_turn(user_input, logger._turn_counter)

            full_response = []
            async for event in runner.run_async(
                session_id=session.id,
                user_id="demo_user",
                new_message=user_content,
            ):
                # ── 记录原始事件 ──
                logger.log_event(event)

                # ── 打印最终文本输出（跳过 reasoning） ──
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text and not event.partial and not part.thought:
                            full_response.append(part.text)
                            print(part.text, end="", flush=True)

            # ── 结束 Turn，分类 + 统计 token ──
            turn_result = logger.end_turn()
            tracer.end_turn(turn_result["steps"], turn_result["turn_id"])
            log_path = logger.save()
            print(f"\n\n📝 调用日志已保存: {log_path}")
            trace_url = tracer.get_trace_url()
            if trace_url:
                print(f"🔍 Langfuse 追踪: {trace_url}")

        except Exception as e:
            error_msg = str(e)
            if "AuthenticationError" in error_msg or "Authentication" in error_msg:
                print(f"\n❌ API 认证失败，请检查 DEEPSEEK_API_KEY 是否正确")
            elif "ConnectionError" in error_msg or "connect" in error_msg.lower():
                print(f"\n❌ 网络连接失败，请检查网络状态")
            else:
                print(f"\n❌ 运行错误: {error_msg}")

        print()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        tracer.shutdown()
