"""Langfuse 可观测性追踪器 — 将 Agent 执行过程发送到 Langfuse Dashboard。

Trace 层级:
  Trace: "assistant-session" (span)
  └── turn-{id} (chain)
      ├── llm-generation (generation) — model, tokens, reasoning
      └── {tool_name} (tool) — 工具名、参数、返回值

特性:
  - 懒初始化：缺少环境变量时自动禁用，不影响 Agent 正常工作
  - 手动 observation 生命周期：start_observation() + .end()
  - 所有 Langfuse 操作包裹 try/except，失败不影响主流程
  - 每轮对话结束后自动 flush，确保数据及时上报
"""

from __future__ import annotations

import os
from typing import Any, Optional

# Langfuse 是可选的，只在启用时才导入
_langfuse_imported = False
try:
    from langfuse import Langfuse  # type: ignore[import-untyped]
    _langfuse_imported = True
except ImportError:
    pass


class LangfuseTracer:
    """向 Langfuse 发送结构化 Trace，提供 Agent 的完整可观测性。

    用法示例:
        tracer = LangfuseTracer()
        tracer.start_session(session_id)
        tracer.start_turn(user_input, turn_id=1)

        # ... Agent 执行，拿到 logger.end_turn() 返回的 steps ...

        tracer.end_turn(steps, turn_id=1)
        print(tracer.get_trace_url())

        # 程序退出时
        tracer.shutdown()
    """

    # ── 公开 API ────────────────────────────────────

    def __init__(self) -> None:
        """初始化追踪器。缺少 Langfuse 密钥时自动禁用。"""
        self.enabled: bool = False
        self.lf: Optional[Langfuse] = None
        self.trace_id: Optional[str] = None
        self._session_obs: Any = None
        self._current_turn_obs: Any = None
        self._session_id: str = ""

        if not _langfuse_imported:
            print("[INFO] Langfuse 未安装，追踪功能已禁用")
            return

        self._init_client()

    def start_session(self, session_id: str, user_id: str = "demo_user") -> None:
        """创建 Session 级别的根 Trace。

        调用时机：Agent 会话开始时（Runner 创建后）。
        """
        if not self.enabled:
            return

        try:
            self._session_id = session_id
            self.trace_id = self.lf.create_trace_id()  # type: ignore[union-attr]
            model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
            env = os.environ.get("ENV", "development")

            self._session_obs = self.lf.start_observation(  # type: ignore[union-attr]
                trace_context={"trace_id": self.trace_id},
                name="assistant-session",
                as_type="span",
                input={
                    "session_id": session_id,
                    "user_id": user_id,
                },
                metadata={
                    "model": model,
                    "environment": env,
                    "python_version": os.environ.get("PYTHON_VERSION", ""),
                },
            )
        except Exception as e:
            print(f"[WARN]Langfuse session 创建失败: {e}")

    def start_turn(self, user_input: str, turn_id: int) -> None:
        """创建 Turn 级别的 Observation（chain 类型）。

        调用时机：每次用户输入后、Agent 执行前。
        """
        if not self.enabled or self._session_obs is None:
            return

        try:
            self._current_turn_obs = self._session_obs.start_observation(
                name=f"turn-{turn_id}",
                as_type="chain",
                input={"user_input": user_input},
            )
        except Exception as e:
            print(f"[WARN]Langfuse turn 创建失败: {e}")
            self._current_turn_obs = None

    def end_turn(self, steps: list[dict], turn_id: int) -> None:
        """结束 Turn，遍历 steps 创建 generation 和 tool observations。

        调用时机：logger.end_turn() 返回后。
        """
        if not self.enabled or self._current_turn_obs is None:
            return

        try:
            # 1) 解析工具参数（LLM_CALL 的 tool_calls → TOOL_RESULT 的 input）
            steps = self._resolve_tool_inputs(steps)

            # 2) 收集最终回复文本
            final_text = ""
            for step in steps:
                if step["type"] == "LLM_CALL":
                    text = step.get("output", {}).get("text", "")
                    if text:
                        final_text = text

            # 3) 更新 turn 的 output
            self._current_turn_obs.update(output={"final_response": final_text})

            # 4) 为每个 step 创建子 observation
            for step in steps:
                if step["type"] == "LLM_CALL":
                    self._record_generation(step)
                elif step["type"] == "TOOL_RESULT":
                    self._record_tool(step)

            # 5) 结束 turn
            self._current_turn_obs.end()
            self._current_turn_obs = None

            # 6) 立即 flush，确保数据及时上报
            self.lf.flush()  # type: ignore[union-attr]

        except Exception as e:
            print(f"[WARN]Langfuse turn 记录失败: {e}")

    def get_trace_url(self) -> Optional[str]:
        """返回当前 Session 在 Langfuse 控制台的查看链接。"""
        if not self.enabled or not self.trace_id:
            return None
        try:
            return self.lf.get_trace_url(self.trace_id)  # type: ignore[union-attr]
        except Exception:
            return None

    def flush(self) -> None:
        """强制刷新缓冲区，将积压数据发送到 Langfuse。"""
        if not self.enabled:
            return
        try:
            self.lf.flush()  # type: ignore[union-attr]
        except Exception:
            pass

    def shutdown(self) -> None:
        """优雅关闭：结束 session → flush → shutdown。

        调用时机：程序退出时（finally 块或退出路径）。
        """
        if not self.enabled:
            return
        try:
            if self._session_obs is not None:
                self._session_obs.end()
                self._session_obs = None
            self.lf.flush()  # type: ignore[union-attr]
            self.lf.shutdown()  # type: ignore[union-attr]
        except Exception as e:
            print(f"[WARN]Langfuse 关闭失败: {e}")

    # ── 内部方法 ────────────────────────────────────

    def _init_client(self) -> None:
        """创建 Langfuse 客户端。缺少密钥时警告并禁用。"""
        public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "").strip()
        secret_key = os.environ.get("LANGFUSE_SECRET_KEY", "").strip()
        host = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com").strip()

        if not public_key or not secret_key:
            print("[TRACING]未配置 LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY，追踪功能已禁用")
            return

        try:
            self.lf = Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                host=host,
            )
            self.enabled = True
            print(f"[TRACING] Langfuse 追踪已启用 -> {host}")
        except Exception as e:
            print(f"[WARN]Langfuse 初始化失败: {e}")
            self.enabled = False

    def _record_generation(self, step: dict) -> None:
        """从 LLM_CALL step 创建 Generation observation。"""
        if self._current_turn_obs is None:
            return

        try:
            token_usage = step.get("token_usage") or {}
            output = step.get("output", {})

            gen = self._current_turn_obs.start_observation(
                name="llm-generation",
                as_type="generation",
                model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
                input={"context": "系统提示词 + 对话历史 + 用户消息及之前的工具结果"},
                output=output if output else None,
                usage_details={
                    "input": token_usage.get("prompt_tokens", 0),
                    "output": token_usage.get("completion_tokens", 0),
                    "total": token_usage.get("total_tokens", 0),
                } if token_usage else None,
                metadata={
                    "cached_tokens": token_usage.get("cached_tokens", 0),
                    "thoughts_tokens": token_usage.get("thoughts_tokens", 0),
                } if token_usage else None,
            )
            gen.end()
        except Exception as e:
            print(f"[WARN]Langfuse generation 记录失败: {e}")

    def _record_tool(self, step: dict) -> None:
        """从 TOOL_RESULT step 创建 Tool observation。"""
        if self._current_turn_obs is None:
            return

        try:
            tool_name = step.get("tool_name", "unknown_tool")
            tool_input = step.get("input")  # 已被 _resolve_tool_inputs 填充
            tool_output = step.get("output")

            # 截断过大的输出，避免超过 Langfuse 大小限制
            safe_output = self._truncate_output(tool_output)

            tool_obs = self._current_turn_obs.start_observation(
                name=tool_name,
                as_type="tool",
                input=tool_input,
                output=safe_output,
            )
            tool_obs.end()
        except Exception as e:
            print(f"[WARN]Langfuse tool 记录失败: {e}")

    @staticmethod
    def _resolve_tool_inputs(steps: list[dict]) -> list[dict]:
        """将 TOOL_RESULT step 的 input 字段与 LLM_CALL 的 tool_calls 匹配。

        logger.py 的 TOOL_RESULT 步骤 input 字段为 null，
        因为 function_response 不包含原始调用参数。
        这个方法从 LLM_CALL 步骤的 tool_calls 中提取参数并填充到对应的 TOOL_RESULT。
        """
        # 收集所有待匹配的工具调用参数（FIFO 队列）
        pending_args: dict[str, list[dict]] = {}
        for step in steps:
            if step["type"] == "LLM_CALL":
                for tc in step.get("output", {}).get("tool_calls", []):
                    name = tc.get("name", "")
                    args = tc.get("arguments", {})
                    pending_args.setdefault(name, []).append(args)

        # 填充 TOOL_RESULT 的 input
        for step in steps:
            if step["type"] == "TOOL_RESULT":
                tool_name = step["tool_name"]
                if tool_name in pending_args and pending_args[tool_name]:
                    step["input"] = pending_args[tool_name].pop(0)

        return steps

    @staticmethod
    def _truncate_output(output: Any, max_chars: int = 10_000) -> Any:
        """截断过大输出，避免触达 Langfuse 的上传限制。"""
        if isinstance(output, str) and len(output) > max_chars:
            return output[:max_chars] + f"\n\n... [截断: 原长度 {len(output)} 字符]"
        if isinstance(output, dict):
            return {
                k: LangfuseTracer._truncate_output(v, max_chars)
                for k, v in output.items()
            }
        if isinstance(output, list):
            return [
                LangfuseTracer._truncate_output(v, max_chars)
                for v in output
            ]
        return output
