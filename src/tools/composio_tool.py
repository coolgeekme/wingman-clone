"""Composio Toolset wrapper for the Wingman Clone agent.

Provides access to 250+ external app integrations.
Updated for v0.17+ with individual toolkit loading for better reliability.
v45: 'Direct Execution' — pre-loads specific action slugs for Gmail send,
Calendar create, and GitHub actions so the agent can execute them immediately
without an extra discovery step.
"""
import logging
from typing import Optional, List
from src.config import settings
from src.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

# Actions the agent is authorized to execute directly without discovery
DIRECT_EXECUTION_ACTIONS = [
    # Gmail
    "GMAIL_SEND_EMAIL",
    "GMAIL_REPLY_TO_THREAD",
    "GMAIL_CREATE_EMAIL_DRAFT",
    "GMAIL_FETCH_EMAILS",
    "GMAIL_GET_EMAIL",
    "GMAIL_LIST_LABELS",
    # Google Calendar
    "GOOGLECALENDAR_CREATE_EVENT",
    "GOOGLECALENDAR_FIND_EVENT",
    "GOOGLECALENDAR_LIST_CALENDARS",
    "GOOGLECALENDAR_GET_CALENDAR",
    "GOOGLECALENDAR_QUICK_ADD",
    "GOOGLECALENDAR_DELETE_EVENT",
    "GOOGLECALENDAR_UPDATE_EVENT",
    # GitHub
    "GITHUB_CREATE_AN_ISSUE",
    "GITHUB_LIST_REPO_ISSUES",
    "GITHUB_CREATE_A_PULL_REQUEST",
    "GITHUB_GET_A_REPOSITORY",
]

# Toolkits to load in full (for broader discovery)
DEFAULT_TOOLKITS = ["gmail", "googlecalendar", "github"]


def _get_composio_sdk():
    api_key = settings.composio_api_key
    if not api_key:
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
    
    Loading strategy (v45 Direct Execution):
    1. Always pre-load DIRECT_EXECUTION_ACTIONS so send/create are immediately available.
    2. Then load any additional toolkits requested via `apps`.
    3. Deduplicate by tool name to avoid conflicts.
    """
    sdk = _get_composio_sdk()
    if sdk is None:
        return []
    
    all_tools = []
    seen_names = set()
    
    def _add_tools(tools):
        """Add tools while deduplicating by name."""
        nonlocal all_tools, seen_names
        for tool in tools:
            name = getattr(tool, 'name', None) or str(tool)
            if name not in seen_names:
                seen_names.add(name)
                all_tools.append(tool)

    try:
        # Step 1: Always load direct-execution actions first
        logger.info(f"Loading {len(DIRECT_EXECUTION_ACTIONS)} direct-execution actions...")
        try:
            direct_tools = sdk.tools.get(user_id=user_id, tools=DIRECT_EXECUTION_ACTIONS)
            if direct_tools:
                _add_tools(list(direct_tools))
                logger.info(f"Loaded {len(list(direct_tools))} direct-execution tools")
        except Exception as e:
            logger.warning(f"Failed to load direct-execution actions in batch: {e}")
            # Fallback: load them one by one
            for action in DIRECT_EXECUTION_ACTIONS:
                try:
                    tools = sdk.tools.get(user_id=user_id, tools=[action])
                    if tools:
                        _add_tools(list(tools))
                except Exception as inner_e:
                    logger.debug(f"Skipping action {action}: {inner_e}")

        # Step 2: Load specific actions if requested
        if actions:
            extra_actions = [a for a in actions if a not in DIRECT_EXECUTION_ACTIONS]
            if extra_actions:
                try:
                    tools = sdk.tools.get(user_id=user_id, tools=extra_actions)
                    if tools:
                        _add_tools(list(tools))
                except Exception as e:
                    logger.error(f"Failed to load extra actions: {e}")

        # Step 3: Load additional toolkits
        elif apps:
            for app in apps:
                try:
                    logger.info(f"Loading toolkit: {app}")
                    tools = sdk.tools.get(user_id=user_id, toolkits=[app])
                    if tools:
                        _add_tools(list(tools))
                        logger.info(f"Loaded tools from {app} (total unique now: {len(all_tools)})")
                except Exception as e:
                    logger.error(f"Failed to load toolkit {app}: {e}")
        else:
            # Default: load standard toolkits beyond direct actions
            for toolkit in DEFAULT_TOOLKITS:
                try:
                    tools = sdk.tools.get(user_id=user_id, toolkits=[toolkit])
                    if tools:
                        _add_tools(list(tools))
                except Exception as e:
                    logger.error(f"Failed to load default toolkit {toolkit}: {e}")

        logger.info(f"Total Composio tools loaded: {len(all_tools)}")
        return all_tools
    except Exception as e:
        logger.error(f"Failed to get Composio tools: {e}")
        return all_tools


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
            result = sdk.tools.execute(
                slug=action, 
                arguments=params or {},
                dangerously_skip_version_check=True
            )
            return ToolResult(success=True, data=result)
        except Exception as e:
            logger.error(f"Composio execute failed for {action}: {e}")
            return ToolResult(success=False, error=str(e))
