from datetime import datetime, timezone
from src.tools.base import BaseTool, ToolResult

class GetTimeTool(BaseTool):
    name = "get_time"
    description = "Get the current date and time in UTC."
    parameters = {"type": "object", "properties": {}}

    async def execute(self, **kwargs) -> ToolResult:
        now = datetime.now(timezone.utc)
        return ToolResult(success=True, data={"utc_time": now.isoformat(), "date": now.strftime("%Y-%m-%d"), "time": now.strftime("%H:%M:%S")})
