"""ADK 事件日志记录器 — 按 Turn 组织，记录每步的 input/output 和 token 消耗。

保存格式:
  logs/<session_id>.json

每个 Turn 结构:
  {
    "turn_id": 1,
    "user_input": "北京天气",
    "steps": [
      { LLM_CALL: { reasoning, tool_calls, token_usage } },
      { TOOL_RESULT: { tool_name, input, output } },
      { LLM_CALL: { reasoning, output_text, token_usage } }
    ]
  }
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from google.adk.events import Event
from google.genai.types import Part

from .llm_trace import clear_llm_requests
from .llm_trace import consume_llm_requests
from .langfuse_trace import LangfuseTraceExporter


class AgentLogger:
    """按 Turn（对话回合）记录 ADK Agent 的完整执行过程。"""

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.session_id: str = ""
        self.turns: list[dict] = []
        self._turn_counter = 0
        self._start_time = time.time()

        # 当前 Turn 的暂存区
        self._current_turn: dict | None = None
        self._raw_events: list[Event] = []
        self.langfuse = LangfuseTraceExporter()

    # ── 公开 API ────────────────────────────────────

    def start_session(self, session_id: str) -> None:
        """开始新的会话记录。"""
        self.session_id = session_id
        self.turns = []
        self._turn_counter = 0
        self._start_time = time.time()

    def start_turn(self, user_input: str) -> None:
        """开始新的一轮对话。"""
        self._turn_counter += 1
        self._current_turn = {
            "turn_id": self._turn_counter,
            "user_input": user_input,
            "steps": [],
        }
        self._raw_events = []
        clear_llm_requests()

    def log_event(self, event: Event) -> None:
        """记录原始 ADK 事件（暂存，end_turn 时分类）。"""
        self._raw_events.append(event)

    def end_turn(self) -> dict:
        """结束当前回合，分类事件并构建结构化日志。"""
        if not self._current_turn:
            return {}

        turn = self._current_turn
        steps = self._build_steps(self._raw_events, consume_llm_requests())
        turn["steps"] = steps

        self.turns.append(turn)
        self._current_turn = None
        self._raw_events = []

        # 控制台摘要
        self._print_turn(turn)
        self.langfuse.export_turn(session_id=self.session_id, turn=turn)
        return turn

    def save(self) -> Path:
        """将会话日志写入 JSON 文件。"""
        log_file = self.log_dir / f"{self.session_id}.json"

        total_llm_calls = sum(
            1 for t in self.turns for s in t["steps"] if s["type"] == "LLM_CALL"
        )
        total_tool_calls = sum(
            1 for t in self.turns for s in t["steps"] if s["type"] == "TOOL_RESULT"
        )
        total_tokens = sum(
            s.get("token_usage", {}).get("total_tokens", 0)
            for t in self.turns
            for s in t["steps"]
            if s["type"] == "LLM_CALL"
        )

        payload = {
            "session_id": self.session_id,
            "total_turns": len(self.turns),
            "total_llm_calls": total_llm_calls,
            "total_tool_calls": total_tool_calls,
            "total_tokens": total_tokens,
            "turns": self.turns,
        }

        log_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return log_file

    # ── 事件分类引擎 ────────────────────────────────

    def _build_steps(
        self,
        events: list[Event],
        llm_inputs: list[dict] | None = None,
    ) -> list[dict]:
        """将零散的 ADK 事件组装为带 input/output 的步骤列表。"""
        llm_inputs = llm_inputs or []
        llm_input_index = 0

        # 合并同属一个 content 的 parts（同一事件 = 同一次 LLM 响应）
        # 但一个事件可能同时包含 reasoning text + function_call
        flat: list[dict] = []
        for event in events:
            if not event.content or not event.content.parts:
                continue
            for part in event.content.parts:
                classified = self._classify_part(part, event)
                if classified:
                    classified["_event"] = event  # 保留原始事件引用
                    flat.append(classified)

        if not flat:
            return []

        # ── 后处理：区分 REASONING 和 LLM_RESPONSE ──
        # 规则：找最后一个 plain text（非 reasoning 标记），它就是最终回复
        # 其余 text 都是 reasoning
        text_indices = [
            i for i, item in enumerate(flat)
            if item["kind"] == "text"
        ]
        if text_indices:
            # 最后一段 text 标记为最终回复，其余为推理
            for idx in text_indices[:-1]:
                flat[idx]["kind"] = "reasoning"
            flat[text_indices[-1]]["kind"] = "response"

        # ── 合成步骤 ──
        steps: list[dict] = []

        # 把同一个 LLM 调用的 reasoning + tool_call 合并
        i = 0
        while i < len(flat):
            item = flat[i]

            if item["kind"] in ("reasoning",):
                # LLM 推理 → 开始一个 LLM_CALL 步骤
                llm_step = self._build_llm_call(item, flat, i)
                llm_step["input"] = _next_llm_input(llm_inputs, llm_input_index)
                llm_input_index += 1
                steps.append(llm_step)
                i = llm_step["_end_index"] + 1
            elif item["kind"] == "tool_call":
                llm_step = self._build_llm_call(item, flat, i)
                llm_step["input"] = _next_llm_input(llm_inputs, llm_input_index)
                llm_input_index += 1
                steps.append(llm_step)
                i = llm_step["_end_index"] + 1
            elif item["kind"] == "tool_result":
                # 工具结果 → TOOL_RESULT 步骤
                steps.append({
                    "type": "TOOL_RESULT",
                    "tool_name": item["tool_name"],
                    "input": item["tool_args"],
                    "output": item["tool_response"],
                })
                i += 1
            elif item["kind"] == "response":
                # 独立最终回复（无工具调用时）
                llm_step = self._build_llm_call(item, flat, i)
                llm_step["input"] = _next_llm_input(llm_inputs, llm_input_index)
                llm_input_index += 1
                steps.append(llm_step)
                i = llm_step["_end_index"] + 1
            else:
                i += 1

        return steps

    def _build_llm_call(self, start_item: dict, flat: list[dict], start_idx: int) -> dict:
        """构建一个 LLM_CALL 步骤，合并 reasoning + tool_calls + response。"""
        reasoning_parts: list[str] = []
        tool_calls: list[dict] = []
        response_parts: list[str] = []
        token_usage: dict = {}

        end_idx = start_idx
        for i in range(start_idx, len(flat)):
            item = flat[i]
            if item["kind"] == "tool_result":
                # 遇到工具结果，LLM 调用结束
                break
            end_idx = i

            if item["kind"] == "reasoning":
                reasoning_parts.append(item["text"])
            elif item["kind"] == "tool_call":
                tool_calls.append({
                    "name": item["tool_name"],
                    "arguments": item["tool_args"],
                })
            elif item["kind"] == "response":
                response_parts.append(item["text"])
            elif item["kind"] == "text":
                # 未被重新分类的单段 text
                response_parts.append(item["text"])

            # 提取 token 统计
            ev = item.get("_event")
            if ev and hasattr(ev, "usage_metadata") and ev.usage_metadata:
                token_usage = self._extract_tokens(ev.usage_metadata)

        step: dict = {
            "type": "LLM_CALL",
            "input": {},
            "output": {},
        }

        if reasoning_parts:
            step["output"]["reasoning"] = "\n".join(reasoning_parts)
        if tool_calls:
            step["output"]["tool_calls"] = tool_calls
        if response_parts:
            step["output"]["text"] = "\n".join(response_parts)
        if token_usage:
            step["token_usage"] = token_usage

        step["_end_index"] = end_idx
        return step

    # ── 底层分类 ────────────────────────────────────

    def _classify_part(self, part: Part, event: Event) -> dict | None:
        """将单个 Part 初步分类。"""
        fc = part.function_call
        fr = part.function_response
        text = (part.text or "").strip()
        thought = part.thought or False

        # 1) 工具调用请求（模型请求调用工具）
        if fc is not None:
            return {
                "kind": "tool_call",
                "tool_name": fc.name,
                "tool_args": dict(fc.args) if fc.args else {},
                "timestamp": datetime.now().isoformat(),
            }

        # 2) 工具返回结果
        if fr is not None:
            return {
                "kind": "tool_result",
                "tool_name": fr.name,
                "tool_args": None,  # 非 LLM 调用时无法获取原始参数，由调用方补充
                "tool_response": _safe_serialize(fr.response),
                "timestamp": datetime.now().isoformat(),
            }

        # 3) 文本内容（暂标为 text，后处理区分 reasoning/response）
        if text:
            # DeepSeek 的 thought 字段可能不可靠，先标记为 text
            if thought:
                return {
                    "kind": "reasoning",
                    "text": text,
                }
            else:
                return {
                    "kind": "text",
                    "text": text,
                }

        return None

    # ── 工具方法 ────────────────────────────────────

    @staticmethod
    def _extract_tokens(usage_metadata) -> dict:
        """从 ADK usage_metadata 提取 token 统计。"""
        return {
            "prompt_tokens": getattr(usage_metadata, "prompt_token_count", None) or 0,
            "completion_tokens": getattr(usage_metadata, "candidates_token_count", None) or 0,
            "total_tokens": getattr(usage_metadata, "total_token_count", None) or 0,
            "cached_tokens": getattr(usage_metadata, "cached_content_token_count", None) or 0,
            "thoughts_tokens": getattr(usage_metadata, "thoughts_token_count", None) or 0,
        }

    def _print_turn(self, turn: dict) -> None:
        """控制台摘要。"""
        turn_id = turn["turn_id"]
        user_input = turn["user_input"][:60]
        print(f"\n{'─' * 50}")
        print(f"  Turn #{turn_id} | 用户: {user_input}")
        for step in turn["steps"]:
            if step["type"] == "LLM_CALL":
                tokens = step.get("token_usage", {})
                tok_str = f"  tokens: ↓{tokens.get('prompt_tokens', '?')} ↑{tokens.get('completion_tokens', '?')} ∑{tokens.get('total_tokens', '?')}" if tokens else ""
                reasoning = step["output"].get("reasoning", "")
                tool_calls = step["output"].get("tool_calls", [])
                text = step["output"].get("text", "")
                if reasoning:
                    snippet = reasoning[:80].replace("\n", " ")
                    print(f"    🧠 REASONING: {snippet}...{tok_str}")
                if tool_calls:
                    for tc in tool_calls:
                        args_str = json.dumps(tc["arguments"], ensure_ascii=False)
                        print(f"    🔧 TOOL_CALL: {tc['name']}({args_str}){tok_str}")
                if text:
                    snippet = text[:100].replace("\n", " ")
                    print(f"    💬 RESPONSE: {snippet}{tok_str}")
            elif step["type"] == "TOOL_RESULT":
                resp = json.dumps(step["output"], ensure_ascii=False)
                snippet = resp[:120]
                print(f"    📦 TOOL_RESULT: {step['tool_name']} → {snippet}")


# ── 工具函数 ──────────────────────────────────────

def _safe_serialize(obj: Any) -> Any:
    """安全序列化任意对象为 JSON 兼容格式。"""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _safe_serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_serialize(v) for v in obj]
    try:
        return str(obj)
    except Exception:
        return f"<unserializable: {type(obj).__name__}>"


def _next_llm_input(llm_inputs: list[dict], index: int) -> dict:
    """Return a captured full LLM input or an explicit missing marker."""
    if index < len(llm_inputs):
        return llm_inputs[index]
    return {
        "missing": True,
        "reason": "No captured LLM request snapshot for this LLM_CALL.",
    }
