from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolResult:
    success: bool
    data: Any = None
    error: Optional[str] = None

    def to_str(self) -> str:
        if self.success:
            return str(self.data)
        return f"Error: {self.error}"


class BaseTool(ABC):
    name: str = ""
    description: str = ""
    parameters: dict = field(default_factory=dict)

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with validated parameters."""

    def get_schema(self) -> dict:
        return {"name": self.name, "description": self.description, "parameters": self.parameters}
