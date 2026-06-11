"""通用 AI 助手 — Compass/DeepSeek + Google ADK + 本地 MCP/Skills。

Agent 通过 McpToolset 连接本地 MCP 服务器，自动发现和调用其中的工具。
同时通过 ADK SkillToolset 加载项目内 skills，向模型注入任务流程指南。
工具能力由 agent/config.py 中的 MCP_SERVERS 和 skills/ 目录共同决定。

每轮对话自动记录 LLM 推理和工具调用的完整过程到 logs/ 目录。
"""

import asyncio
import os
import sys
import warnings
from pathlib import Path

# 静音 Google ADK 内部实验性功能的调试警告（不影响功能）
warnings.filterwarnings("ignore", message=".*EXPERIMENTAL.*")

from dotenv import load_dotenv
from google.genai import types
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

# 启动时自动加载 .env 文件
load_dotenv(dotenv_path=Path(__file__).with_name(".env"))

from agent.agent import assistant
from agent.llm_config import resolve_llm_config
from agent.logger import AgentLogger
from agent.skills import load_project_skills

# 全局日志记录器
logger = AgentLogger(log_dir="logs")


def check_api_key() -> bool:
    """检查当前 LLM provider 所需的 API Key 是否已配置。"""
    config = resolve_llm_config()
    key = os.environ.get(config.api_key_env)
    if not key or key.startswith("your-"):
        print(f"❌ 未检测到有效的 {config.api_key_env}")
        print()
        print("请按以下步骤配置：")
        print("  1. 复制 .env.example 为 .env")
        print("     cp .env.example .env")
        print("  2. 编辑 .env，填入你的 API Key")
        print("     COMPASS_API_KEY=xxxxxxxxxxxxxxxx")
        print("  3. 如需切回 DeepSeek，可设置 LLM_PROVIDER=deepseek")
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

    # 2. 创建 Runner
    runner = Runner(
        agent=assistant,
        app_name="assistant_app",
        session_service=session_service,
    )

    # 3. 交互式查询循环
    print("=" * 60)
    llm_config = resolve_llm_config()
    print(f"🤖 通用 AI 助手 ({llm_config.provider}: {llm_config.model} + 本地 MCP 工具)")
    print("=" * 60)
    print("已连接的 MCP 服务：")
    print("  • weather  — 天气查询 (get_weather)")
    print("  • route    — 路线规划 (get_route, list_cities)")
    skills = load_project_skills()
    if skills:
        print("已加载的 ADK Skills：")
        for skill in skills:
            print(f"  • {skill.name}")
    print(f"Langfuse Trace: {logger.langfuse.status}")
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
            logger.end_turn()
            log_path = logger.save()
            print(f"\n\n📝 调用日志已保存: {log_path}")

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
    asyncio.run(main())
