"""MCP 路线查询服务器 —— 提供 mock 城市间路线规划。

启动方式:
    python mcp_servers/route_server.py

测试方式（MCP Inspector）:
    npx @anthropic-ai/mcp-inspector python mcp_servers/route_server.py
"""

import json
import math
import random
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


# ── 城市坐标表（简化的经纬度） ──────────────────────

CITY_COORDS: dict[str, tuple[float, float]] = {
    "北京": (39.91, 116.40),
    "上海": (31.23, 121.47),
    "广州": (23.13, 113.26),
    "深圳": (22.54, 114.06),
    "杭州": (30.27, 120.15),
    "成都": (30.57, 104.07),
    "武汉": (30.58, 114.30),
    "重庆": (29.56, 106.55),
    "西安": (34.26, 108.94),
    "南京": (32.06, 118.80),
    "天津": (39.13, 117.20),
    "长沙": (28.23, 112.94),
    "东京": (35.68, 139.76),
    "首尔": (37.57, 126.98),
    "曼谷": (13.75, 100.50),
    "新加坡": (1.35, 103.82),
    "纽约": (40.71, -74.01),
    "伦敦": (51.51, -0.13),
    "巴黎": (48.86, 2.35),
    "悉尼": (-33.87, 151.21),
}


def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """计算两点间的球面距离（公里）。"""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _plan_route(
    origin: str,
    destination: str,
    mode: str = "driving",
) -> dict:
    """生成两点之间的 mock 路线方案。"""
    # 查找坐标
    if origin not in CITY_COORDS:
        return {"error": f"未找到出发城市 '{origin}'", "available_cities": list(CITY_COORDS.keys())}
    if destination not in CITY_COORDS:
        return {"error": f"未找到目的城市 '{destination}'", "available_cities": list(CITY_COORDS.keys())}

    if origin == destination:
        return {"error": "出发地和目的地不能相同"}

    lat1, lon1 = CITY_COORDS[origin]
    lat2, lon2 = CITY_COORDS[destination]

    direct_distance = _haversine_distance(lat1, lon1, lat2, lon2)

    # 模式对应的速度和路线因子
    mode_config = {
        "driving": {"speed_kmh": 100, "name": "驾车", "factor": 1.15},
        "walking": {"speed_kmh": 5, "name": "步行", "factor": 1.0},
        "cycling": {"speed_kmh": 20, "name": "骑行", "factor": 1.05},
        "transit": {"speed_kmh": 60, "name": "公共交通", "factor": 1.3},
    }

    if mode not in mode_config:
        return {"error": f"不支持的出行方式 '{mode}'", "available_modes": list(mode_config.keys())}

    config = mode_config[mode]
    route_distance = round(direct_distance * config["factor"], 1)
    duration_minutes = int(route_distance / config["speed_kmh"] * 60)

    # 生成中间的途经点
    rng = random.Random(hash(f"{origin}{destination}{mode}"))
    waypoints_count = 0 if mode == "walking" else rng.randint(1, 3)
    mid_cities = [c for c in CITY_COORDS if c not in (origin, destination)]
    waypoints = rng.sample(mid_cities, min(waypoints_count, len(mid_cities)))

    # 费用估算
    cost = None
    if mode == "driving":
        cost = round(route_distance * rng.uniform(0.4, 0.8), 2)  # 油费/过路费
    elif mode == "transit":
        cost = round(route_distance * rng.uniform(0.1, 0.3), 2)

    return {
        "origin": origin,
        "destination": destination,
        "mode": config["name"],
        "direct_distance_km": round(direct_distance, 1),
        "route_distance_km": route_distance,
        "estimated_duration": f"{duration_minutes // 60}小时{duration_minutes % 60}分钟",
        "duration_minutes": duration_minutes,
        "waypoints": waypoints,
        "estimated_cost": cost,
        "cost_unit": "元" if cost else None,
    }


def _find_nearby_cities(city: str, max_distance_km: float = 500) -> dict:
    """查找指定城市周边一定范围内的所有城市。

    Args:
        city: 中心城市名称
        max_distance_km: 最大搜索半径（公里），默认 500
    """
    if city not in CITY_COORDS:
        return {"error": f"未找到城市 '{city}'", "available_cities": list(CITY_COORDS.keys())}

    lat1, lon1 = CITY_COORDS[city]
    nearby: list[dict] = []
    for name, (lat2, lon2) in CITY_COORDS.items():
        if name == city:
            continue
        dist = _haversine_distance(lat1, lon1, lat2, lon2)
        if dist <= max_distance_km:
            nearby.append({"city": name, "distance_km": round(dist, 1)})

    nearby.sort(key=lambda x: x["distance_km"])
    return {
        "center": city,
        "max_distance_km": max_distance_km,
        "count": len(nearby),
        "nearby_cities": nearby,
    }


def _compare_routes(origin: str, destination: str) -> dict:
    """对比所有出行方式在同一路线上的耗时、距离和费用。"""
    if origin not in CITY_COORDS:
        return {"error": f"未找到出发城市 '{origin}'", "available_cities": list(CITY_COORDS.keys())}
    if destination not in CITY_COORDS:
        return {"error": f"未找到目的城市 '{destination}'", "available_cities": list(CITY_COORDS.keys())}
    if origin == destination:
        return {"error": "出发地和目的地不能相同"}

    modes = ["driving", "walking", "cycling", "transit"]
    results = []
    for mode in modes:
        r = _plan_route(origin, destination, mode)
        results.append({
            "mode": r["mode"],
            "distance_km": r["route_distance_km"],
            "duration": r["estimated_duration"],
            "duration_minutes": r["duration_minutes"],
            "estimated_cost": r["estimated_cost"],
        })

    # 按耗时排序，最快的排最前
    results.sort(key=lambda x: x["duration_minutes"])

    return {
        "origin": origin,
        "destination": destination,
        "direct_distance_km": _plan_route(origin, destination, "walking")["direct_distance_km"],
        "comparison": results,
        "fastest": results[0]["mode"],
        "cheapest": next((r for r in results if r["estimated_cost"] is not None), results[0])["mode"],
    }


# ── MCP Server ────────────────────────────────────

app = Server("route-server")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """声明此 MCP 服务器提供的所有工具。"""
    return [
        Tool(
            name="get_route",
            description="查询两个城市之间的路线规划，支持驾车、步行、骑行、公共交通等出行方式。返回距离、预计时间、途经点、费用估算等信息。",
            inputSchema={
                "type": "object",
                "properties": {
                    "origin": {
                        "type": "string",
                        "description": "出发城市名称，例如 北京、上海、东京",
                    },
                    "destination": {
                        "type": "string",
                        "description": "目的城市名称，例如 广州、纽约、伦敦",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["driving", "walking", "cycling", "transit"],
                        "description": "出行方式：driving(驾车)、walking(步行)、cycling(骑行)、transit(公共交通)。默认为 driving",
                    },
                },
                "required": ["origin", "destination"],
            },
        ),
        Tool(
            name="list_cities",
            description="列出所有支持路线查询的城市",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="find_nearby_cities",
            description="查找指定城市周边一定范围内的其他城市。例如'北京周围 500km 内有哪些城市'。返回按距离排序的城市列表。",
            inputSchema={
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "中心城市名称，例如 北京、上海",
                    },
                    "max_distance_km": {
                        "type": "number",
                        "description": "最大搜索半径（公里），默认 500。例如 300 表示只查找 300km 以内的城市",
                    },
                },
                "required": ["city"],
            },
        ),
        Tool(
            name="compare_routes",
            description="对比同一路线上所有出行方式（驾车、步行、骑行、公共交通）的耗时、距离和费用，并按速度排序。用于快速了解'怎么走最快'或'怎么走最省钱'。",
            inputSchema={
                "type": "object",
                "properties": {
                    "origin": {
                        "type": "string",
                        "description": "出发城市名称",
                    },
                    "destination": {
                        "type": "string",
                        "description": "目的城市名称",
                    },
                },
                "required": ["origin", "destination"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """处理工具调用请求。"""
    if name == "get_route":
        origin = arguments.get("origin", "")
        destination = arguments.get("destination", "")
        mode = arguments.get("mode", "driving")
        result = _plan_route(origin, destination, mode)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

    elif name == "list_cities":
        return [TextContent(
            type="text",
            text=json.dumps(
                {"cities": list(CITY_COORDS.keys()), "total": len(CITY_COORDS)},
                ensure_ascii=False,
            ),
        )]

    elif name == "find_nearby_cities":
        city = arguments.get("city", "")
        max_dist = arguments.get("max_distance_km", 500)
        result = _find_nearby_cities(city, max_dist)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

    elif name == "compare_routes":
        origin = arguments.get("origin", "")
        destination = arguments.get("destination", "")
        result = _compare_routes(origin, destination)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

    raise ValueError(f"Unknown tool: {name}")


# ── 入口：通过 stdio 运行 ──────────────────────────

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
