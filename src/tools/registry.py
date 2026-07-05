import importlib
import inspect
import logging
import pkgutil
from pathlib import Path
from typing import Optional

from src.tools.base import BaseTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def list_tools(self) -> list[dict]:
        return [tool.get_schema() for tool in self._tools.values()]

    def get_all(self) -> list[BaseTool]:
        return list(self._tools.values())

    def auto_discover(self) -> None:
        tools_dir = Path(__file__).parent
        package_name = "src.tools"
        for module_info in pkgutil.iter_modules([str(tools_dir)]):
            if module_info.name in ("base", "registry", "__init__"):
                continue
            try:
                module = importlib.import_module(f"{package_name}.{module_info.name}")
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (inspect.isclass(attr) and issubclass(attr, BaseTool) and attr is not BaseTool and hasattr(attr, "name") and attr.name):
                        self.register(attr())
            except Exception as e:
                logger.error(f"Failed to load tool module '{module_info.name}': {e}")


registry = ToolRegistry()
