import random
from src.tools.base import BaseTool, ToolResult

class GetWeatherTool(BaseTool):
    name = "get_weather"
    description = "Get the current weather for a given city."
    parameters = {"type": "object", "properties": {"city": {"type": "string", "description": "The city name"}}, "required": ["city"]}

    async def execute(self, **kwargs) -> ToolResult:
        city = kwargs.get("city", "Unknown")
        conditions = ["Sunny", "Cloudy", "Rainy", "Partly Cloudy", "Windy"]
        return ToolResult(success=True, data={"city": city, "temperature_f": random.randint(60, 105), "condition": random.choice(conditions), "humidity_pct": random.randint(10, 90)})
