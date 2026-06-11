---
name: travel-route-planner
description: Use this skill when the user asks to plan a trip, compare travel routes, query destination weather, find nearby cities, list supported cities, or combine route and weather information into a practical itinerary. It is designed for this project's MCP tools such as get_weather, get_route, list_cities, find_nearby_cities, and compare_routes.
---

# Travel Route Planner

## Overview

Plan concise travel routes using the assistant's available MCP tools. Prefer actual tool calls over guessing when the user asks about weather, routes, nearby cities, supported destinations, travel mode comparison, or a route-based itinerary.

## Workflow

1. Identify the travel intent:
   - Weather only: call `get_weather(city, optional country)`.
   - Route only: call `get_route(origin, destination, optional mode)`.
   - Mode comparison: call `compare_routes(origin, destination)`.
   - Nearby destination ideas: call `find_nearby_cities(city, optional max_distance_km)`.
   - Unsupported or unknown city list: call `list_cities()`.
2. If origin or destination is missing, ask a short clarification. If travel mode is missing, default to `driving` and state that assumption instead of asking first.
3. Combine tool results into a practical answer:
   - Start with the recommended route or plan.
   - Include distance, duration, estimated cost, weather, and any caveats.
   - For multi-city plans, order stops geographically and keep the schedule realistic.
4. If a tool returns an error or unsupported city, explain the limitation and offer supported alternatives from `available_cities` or `list_cities()`.

## Output Shape

For route planning, use this compact structure:

```text
推荐方案：
- 路线：
- 出行方式：
- 预计耗时：
- 距离/费用：
- 天气：

行程建议：
1. ...
2. ...

注意：
- ...
```

For comparison requests, show a small table with mode, time, distance, and cost. Avoid overclaiming accuracy because the current tools provide mock route and weather data.

## Tool Guidance

- Use `mode="driving"` by default unless the user mentions walking, cycling, public transit, fastest, cheapest, or comparison. Do not ask for travel mode when origin and destination are already clear.
- Use `compare_routes` when the user asks "最快", "最省钱", "怎么去更合适", or similar.
- Use `find_nearby_cities` for "周边", "附近", "短途", "周末去哪", or "500km 内".
- Use `get_weather` for every city where weather materially affects the plan.
- Mention when weather or route data is mock data if the user is making real travel decisions.

## Examples

User: "帮我规划北京到上海的路线，顺便看天气"

Action: call `get_route("北京", "上海", "driving")`, then `get_weather("北京")` and `get_weather("上海")`. Summarize route and weather together.

User: "上海附近 300km 有什么城市适合周末去？"

Action: call `find_nearby_cities("上海", 300)`. If cities are returned, optionally call weather for the top options before recommending.
