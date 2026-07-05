from abc import ABC, abstractmethod
from src.tools.base import BaseTool

class BaseIntegration(ABC):
    name: str = ""
    description: str = ""

    @abstractmethod
    async def authenticate(self, credentials: dict) -> bool:
        pass

    @abstractmethod
    def get_tools(self) -> list[BaseTool]:
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        pass
