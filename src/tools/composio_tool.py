"""Composio Toolset wrapper for the Wingman Clone agent."""
import logging
from typing import Optional
from src.config import settings
from src.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

def get_composio_langchain_tools(apps: Optional[list[str]] = None, actions: Optional[list[str]] = None) -> list:
    """Initialize and return Composio tools for use with LangChain agents."""
    api_key = settings.composio_api_key
    if not api_key:
        logger.warning("COMPOSIO_API_KEY not set.")
        return []
    try:
        from composio_langchain import ComposioToolSet
        toolset = ComposioToolSet(api_key=api_key)
        if actions:
            return toolset.get_tools(actions=actions)
        elif apps:
            return toolset.get_tools(apps=apps)
        else:
            return toolset.get_tools(apps=["github"])
    except ImportError:
        logger.error("composio-langchain not installed.")
        return []
    except Exception as e:
        logger.error(f"Failed to initialize Composio: {e}")
        return []

class ComposioTool(BaseTool):
    name = "composio"
    description = "Execute an action on an external app via Composio. Supports 250+ integrations."
    parameters = {"type": "object", "properties": {"action": {"type": "string", "description": "Composio action name"}, "params": {"type": "object", "description": "Action parameters"}}, "required": ["action"]}

    async def execute(self, action: str, params: Optional[dict] = None, **kwargs) -> ToolResult:
        api_key = settings.composio_api_key
        if not api_key:
            return ToolResult(success=False, error="COMPOSIO_API_KEY not configured")
        try:
            from composio_langchain import ComposioToolSet
            toolset = ComposioToolSet(api_key=api_key)
            result = toolset.execute_action(action=action, params=params or {})
            return ToolResult(success=True, data=result)
        except Exception as e:
            return ToolResult(success=False, error=str(e))
