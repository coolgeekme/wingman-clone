"""
Web Search Tool — real-time internet search via DuckDuckGo.
Drop-in for the Wingman Clone Tool Sandbox.
Requires: pip install duckduckgo-search
"""

import json
import logging
from src.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class WebSearchTool(BaseTool):
    name = "web_search"
    description = (
        "Search the web for real-time information. Use this when the user asks about "
        "current events, news, prices, sports scores, weather, or anything that requires "
        "up-to-date internet data. Returns a list of relevant results with title, URL, and snippet."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query to run on the web.",
            },
            "max_results": {
                "type": "integer",
                "description": "Number of results to return (default 5, max 10).",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    async def execute(self, query: str, max_results: int = 5) -> ToolResult:
        try:
            from duckduckgo_search import DDGS

            max_results = min(max_results, 10)

            with DDGS() as ddgs:
                results = list(ddgs.text(
                    query,
                    max_results=max_results,
                    safesearch="moderate",
                ))

            if not results:
                return ToolResult(
                    success=True,
                    data="No results found for that query. Try rephrasing the search.",
                )

            formatted = []
            for i, r in enumerate(results, 1):
                title = r.get("title", "No Title")
                href = r.get("href", "")
                body = r.get("body", "")
                formatted.append(f"**[{i}] {title}**\nURL: {href}\n{body}\n")

            return ToolResult(
                success=True,
                data="\n".join(formatted),
            )

        except ImportError:
            return ToolResult(
                success=False,
                error="duckduckgo-search is not installed. Run: pip install duckduckgo-search",
            )
        except Exception as e:
            logger.error(f"Web search failed: {e}")
            return ToolResult(success=False, error=str(e))
