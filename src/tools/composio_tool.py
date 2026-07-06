"""Composio Toolset wrapper for the Wingman Clone agent.

Provides access to 250+ external app integrations.
Uses the Composio SDK v0.17+ with LangchainProvider.
"""
import logging
from typing import Optional
from src.config import settings
from src.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


def _get_composio_client():
    """Create and return a Composio client with LangchainProvider."""
    api_key = settings.composio_api_key
    if not api_key:
        logger.warning("COMPOSIO_API_KEY not set.")
        return None
    try:
        from composio import Composio
        from composio_langchain import LangchainProvider
        return Composio(provider=LangchainProvider(), api_key=api_key)
    except Exception as e:
        logger.error(f"Failed to initialize Composio client: {e}")
        return None


def get_composio_langchain_tools(
    apps: Optional[list[str]] = None,
    actions: Optional[list[str]] = None,
) -> list:
    """Initialize and return Composio tools for use with LangChain agents."""
    client = _get_composio_client()
    if client is None:
        return []
    try:
        kwargs = {"user_id": "default"}
        if actions:
            kwargs["tools"] = actions
        elif apps:
            kwargs["toolkits"] = apps
        else:
            kwargs["toolkits"] = ["github"]
        
        tools = client.tools.get(**kwargs)
        return list(tools) if tools else []
    except Exception as e:
        logger.error(f"Failed to get Composio tools: {e}")
        return []


class ComposioTool(BaseTool):
    name = "composio_generic_action"
    description = "Execute an action on an external app via Composio. ONLY use this if a specific tool (like GMAIL_*) is NOT available."
    parameters = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "Composio action slug"},
            "params": {"type": "object", "description": "Action parameters"},
        },
        "required": ["action"],
    }

    async def execute(self, action: str, params: Optional[dict] = None, **kwargs) -> ToolResult:
        client = _get_composio_client()
        if client is None:
            return ToolResult(success=False, error="COMPOSIO_API_KEY not configured")
        try:
            tools = client.tools.get(user_id="default", tools=[action])
            if not tools:
                return ToolResult(success=False, error=f"Tool '{action}' not found")
            result = tools[0].invoke(params or {})
            return ToolResult(success=True, data=result)
        except Exception as e:
            logger.error(f"Composio execute failed for {action}: {e}")
            return ToolResult(success=False, error=str(e))
