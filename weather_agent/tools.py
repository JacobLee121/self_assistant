"""Mock weather tool for the Weather Agent."""

import random
from typing import Optional


def get_weather(city: str, country: Optional[str] = None) -> dict:
    """查询指定城市的天气信息。

    Args:
        city: 城市名称，例如 "Beijing"、"Tokyo"、"New York"
        country: 可选的国家名称，用于区分同名城市

    Returns:
        包含天气信息的字典，包括温度、湿度、天气状况、风速等
    """
    # Mock 数据：根据城市名生成看起来合理的天气
    conditions = ["晴天 ☀️", "多云 ⛅", "阴天 ☁️", "小雨 🌧️", "雷阵雨 ⛈️"]
    city_hash = sum(ord(c) for c in city) if city else 0
    random.seed(city_hash)

    temp_base = random.randint(5, 35)
    humidity = random.randint(30, 90)
    wind_speed = round(random.uniform(1.0, 25.0), 1)
    condition = random.choice(conditions)

    # Reset random seed to avoid affecting other code
    random.seed()

    location = f"{city}, {country}" if country else city

    return {
        "location": location,
        "temperature": temp_base,
        "feels_like": temp_base + random.randint(-3, 3),
        "humidity": humidity,
        "wind_speed_kmh": wind_speed,
        "condition": condition,
        "forecast": {
            "today": f"{temp_base}°C, {condition}",
            "tomorrow": f"{temp_base + random.randint(-5, 5)}°C, {random.choice(conditions)}",
            "day_after": f"{temp_base + random.randint(-8, 8)}°C, {random.choice(conditions)}",
        },
    }
