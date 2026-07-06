"""Composio Toolset wrapper for the Wingman Clone agent.

Provides access to 250+ external app integrations.
Updated for v0.17+ with dangerously_skip_version_check=True to avoid version errors.
"""
import logging
from typing import Optional
from src.config import settings
from src.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


def _get_composio_sdk():
    api_key = settings.composio_api_key
    if not api_key:
        return None
    try:
        from composio import Composio
        from composio_langchain import LangchainProvider
        # Initialize with version check skipping to prevent manual execution errors
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
        sdk = _get_composio_sdk()
        if sdk is None:
            return ToolResult(success=False, error="COMPOSIO_API_KEY not configured")
        try:
            # We use the SDK client to execute directly with version skipping
            result = sdk.client.tools.execute(
                slug=action, 
                arguments=params or {},
                dangerously_skip_version_check=True
            )
            return ToolResult(success=True, data=result)
        except Exception as e:
            logger.error(f"Composio execute failed for {action}: {e}")
            return ToolResult(success=False, error=str(e))
