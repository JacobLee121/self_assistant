"""MCP 天气查询服务器 —— 提供 mock 天气数据。

启动方式:
    python mcp_servers/weather_server.py

测试方式（MCP Inspector）:
    npx @anthropic-ai/mcp-inspector python mcp_servers/weather_server.py
"""

import json
import random
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


# ── Mock 数据生成（与现有 tools.py 逻辑相同） ──────────────

def _get_weather(city: str, country: str | None = None) -> dict:
    """根据城市名生成 mock 天气数据。"""
    conditions = ["晴天 ☀️", "多云 ⛅", "阴天 ☁️", "小雨 🌧️", "雷阵雨 ⛈️"]
    city_hash = sum(ord(c) for c in city) if city else 0
    rng = random.Random(city_hash)  # 同城市始终相同的天气

    temp_base = rng.randint(5, 35)
    humidity = rng.randint(30, 90)
    wind_speed = round(rng.uniform(1.0, 25.0), 1)
    condition = rng.choice(conditions)

    location = f"{city}, {country}" if country else city

    return {
        "location": location,
        "temperature": temp_base,
        "feels_like": temp_base + rng.randint(-3, 3),
        "humidity": humidity,
        "wind_speed_kmh": wind_speed,
        "condition": condition,
        "forecast": {
            "today": f"{temp_base}°C, {condition}",
            "tomorrow": f"{temp_base + rng.randint(-5, 5)}°C, {rng.choice(conditions)}",
            "day_after": f"{temp_base + rng.randint(-8, 8)}°C, {rng.choice(conditions)}",
        },
    }


# ── MCP Server ────────────────────────────────────

app = Server("weather-server")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """声明此 MCP 服务器提供的所有工具。"""
    return [
        Tool(
            name="get_weather",
            description="查询指定城市的天气信息，返回温度、湿度、风速、天气状况和未来预报",
            inputSchema={
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称，例如 Beijing、Tokyo、New York",
                    },
                    "country": {
                        "type": "string",
                        "description": "可选的国家名称，用于区分同名城市",
                    },
                },
                "required": ["city"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """处理工具调用请求。"""
    if name == "get_weather":
        city = arguments.get("city", "")
        country = arguments.get("country")
        result = _get_weather(city, country)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

    raise ValueError(f"Unknown tool: {name}")


# ── 入口：通过 stdio 运行 ──────────────────────────

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
