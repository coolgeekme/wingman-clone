"""Composio Toolset wrapper for the Wingman Clone agent.

Hallucination-Proof v3.3: Added tool-name validation, deterministic execution,
and structured error responses to prevent LLM hallucinations on tool names.

Updated for composio SDK v0.17.x which removed the legacy ComposioToolSet class.
The new API uses: Composio(provider=LangchainProvider(), api_key=...) with
sdk.tools.get() for fetching LangChain-wrapped tools and sdk.tools.execute() for
direct action execution.
"""
import logging
import re
from typing import Optional
from src.config import settings
from src.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

_TOOL_NAME_CACHE: dict[str, list[str]] = {}


def _get_composio_sdk():
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


def _validate_tool_name(action: str) -> str:
    if not action:
        return action
    if re.match(r'^[A-Z][A-Z0-9_]+$', action):
        return action
    if any(c.islower() for c in action) and any(c.isupper() for c in action):
        converted = re.sub(r'([A-Z])', r'_\1', action).upper().lstrip('_')
        converted = re.sub(r'_+', '_', converted)
        logger.info(f"v3.3 tool-name fix: '{action}' -> '{converted}'")
        return converted
    if '.' in action or '-' in action:
        converted = action.replace('.', '_').replace('-', '_').upper()
        logger.info(f"v3.3 tool-name fix: '{action}' -> '{converted}'")
        return converted
    return action.upper()


def get_composio_langchain_tools(apps: Optional[list[str]] = None, actions: Optional[list[str]] = None, user_id: str = "default") -> list:
    global _TOOL_NAME_CACHE
    sdk = _get_composio_sdk()
    if sdk is None:
        return []
    try:
        kwargs = {"user_id": user_id}
        if actions:
            validated_actions = [_validate_tool_name(a) for a in actions]
            kwargs["tools"] = validated_actions
        elif apps:
            kwargs["toolkits"] = apps
        else:
            kwargs["toolkits"] = ["github"]
        tools = sdk.tools.get(**kwargs)
        tool_list = list(tools) if tools else []
        for t in tool_list:
            name = getattr(t, 'name', '')
            if name:
                parts = name.split('_')
                if parts:
                    app_key = parts[0]
                    if app_key not in _TOOL_NAME_CACHE:
                        _TOOL_NAME_CACHE[app_key] = []
                    if name not in _TOOL_NAME_CACHE[app_key]:
                        _TOOL_NAME_CACHE[app_key].append(name)
        logger.info(f"v3.3 Loaded {len(tool_list)} Composio tools | Cache: {', '.join(f'{k}({len(v)})' for k, v in _TOOL_NAME_CACHE.items())}")
        return tool_list
    except ImportError:
        logger.error("composio or composio-langchain not installed.")
        return []
    except Exception as e:
        logger.error(f"Failed to get Composio tools: {e}")
        return []


def get_cached_tool_names(app: Optional[str] = None) -> list[str]:
    if app:
        return _TOOL_NAME_CACHE.get(app.upper(), [])
    return [name for names in _TOOL_NAME_CACHE.values() for name in names]


class ComposioTool(BaseTool):
    name = "composio"
    description = "Execute an action on an external app via Composio. Supports 250+ integrations."
    parameters = {"type": "object", "properties": {"action": {"type": "string", "description": "Composio action slug in SCREAMING_SNAKE_CASE (e.g. GMAIL_SEND_EMAIL). Must be exact match."}, "params": {"type": "object", "description": "Action parameters"}}, "required": ["action"]}

    async def execute(self, action: str, params: Optional[dict] = None, **kwargs) -> ToolResult:
        sdk = _get_composio_sdk()
        if sdk is None:
            return ToolResult(success=False, error="COMPOSIO_API_KEY not configured")
        original_action = action
        action = _validate_tool_name(action)
        if action != original_action:
            logger.info(f"v3.3 ComposioTool: normalized '{original_action}' -> '{action}'")
        try:
            result = sdk.tools.execute(slug=action, arguments=params or {})
            return ToolResult(success=True, data=result)
        except Exception as e:
            error_msg = str(e)
            if "not found" in error_msg.lower() or "invalid" in error_msg.lower():
                app_prefix = action.split('_')[0] if '_' in action else action
                suggestions = _TOOL_NAME_CACHE.get(app_prefix, [])[:5]
                if suggestions:
                    error_msg += f" | Available {app_prefix} tools: {suggestions}"
            logger.error(f"Composio execute failed for {action}: {error_msg}")
            return ToolResult(success=False, error=error_msg)
