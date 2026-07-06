"""Composio Toolset wrapper for the Wingman Clone agent.

Updated for composio SDK v0.17.x which removed the legacy ComposioToolSet class.
The new API uses: Composio(provider=LangchainProvider(), api_key=...) with
sdk.tools.get() for fetching LangChain-wrapped tools and sdk.tools.execute() for
direct action execution.
"""
import logging
from typing import Optional
from src.config import settings
from src.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


def _get_composio_sdk():
    """Create and return a Composio SDK instance with the LangChain provider."""
    api_key = settings.composio_api_key
    if not api_key:
        logger.warning("COMPOSIO_API_KEY not set.")
        return None
    try:
        from composio import Composio
        from composio_langchain import LangchainProvider
        sdk = Composio(provider=LangchainProvider(), api_key=api_key)
        return sdk
    except Exception as e:
        logger.error(f"Failed to initialize Composio SDK: {e}")
        return None


def get_composio_langchain_tools(
    apps: Optional[list[str]] = None,
    actions: Optional[list[str]] = None,
    user_id: str = "default",
) -> list:
    """Initialize and return Composio tools for use with LangChain agents.

    Args:
        apps: List of toolkit/app names (e.g. ["github", "gmail"]).
        actions: List of specific action/tool slugs.
        user_id: The Composio user ID (defaults to "default").

    Returns:
        List of LangChain StructuredTool objects.
    """
    sdk = _get_composio_sdk()
    if sdk is None:
        return []
    try:
        kwargs = {"user_id": user_id}
        if actions:
            kwargs["tools"] = actions
        elif apps:
            kwargs["toolkits"] = apps
        else:
            kwargs["toolkits"] = ["github"]
        tools = sdk.tools.get(**kwargs)
        logger.info(f"Loaded {len(tools) if tools else 0} Composio tools.")
        return list(tools) if tools else []
    except ImportError:
        logger.error("composio or composio-langchain not installed.")
        return []
    except Exception as e:
        logger.error(f"Failed to get Composio tools: {e}")
        return []


class ComposioTool(BaseTool):
    name = "composio"
    description = "Execute an action on an external app via Composio. Supports 250+ integrations."
    parameters = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "Composio action slug (e.g. GITHUB_CREATE_ISSUE)"},
            "params": {"type": "object", "description": "Action parameters"},
        },
        "required": ["action"],
    }

    async def execute(self, action: str, params: Optional[dict] = None, **kwargs) -> ToolResult:
        sdk = _get_composio_sdk()
        if sdk is None:
            return ToolResult(success=False, error="COMPOSIO_API_KEY not configured")
        try:
            result = sdk.tools.execute(slug=action, arguments=params or {})
            return ToolResult(success=True, data=result)
        except Exception as e:
            logger.error(f"Composio execute failed for {action}: {e}")
            return ToolResult(success=False, error=str(e))
