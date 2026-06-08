"""Weather Agent definition using Google ADK + DeepSeek API."""

import os

from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import FunctionTool

from .tools import get_weather

# DeepSeek 模型配置
# 支持: 完整格式 "deepseek/deepseek-chat" 或 简写 "deepseek-chat"
_raw_model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
if "/" not in _raw_model:
    _raw_model = f"deepseek/{_raw_model}"
DEEPSEEK_MODEL = _raw_model

# 定义 Agent 的 system instruction
SYSTEM_INSTRUCTION = """\
你是一个专业的天气查询助手。当用户询问天气时，请：

1. 使用 `get_weather` 工具获取指定城市的天气数据
2. 将数据用中文友好地呈现给用户，包括：
   - 当前温度、体感温度
   - 湿度、风速
   - 天气状况
   - 未来两天的简要预报
3. 如果用户没有指定城市，请主动询问
4. 回复要简洁清晰，适当使用 emoji 增加可读性
"""

# 创建 Agent 实例
weather_agent = Agent(
    name="weather_agent",
    model=LiteLlm(model=DEEPSEEK_MODEL),
    instruction=SYSTEM_INSTRUCTION,
    tools=[FunctionTool(get_weather)],
)
