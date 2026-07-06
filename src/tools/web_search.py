"""
Web Search Tool — real-time internet search via DuckDuckGo.
Updated for latest ddgs package compatibility.
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
            # Try new ddgs package first, fall back to old duckduckgo_search
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS

            max_results = min(max_results, 10)

            # Updated for the latest library structure
            with DDGS() as ddgs:
                results = list(ddgs.text(
                    query,
                    max_results=max_results
                ))

            if not results:
                # Fallback search query if the first one was too specific
                logger.info(f"No results for '{query}', trying broader search...")
                with DDGS() as ddgs:
                    results = list(ddgs.text(query.split(' ')[0], max_results=3))

            if not results:
                return ToolResult(
                    success=True,
                    data="No search results found for that query. The service might be temporarily unavailable.",
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

        except Exception as e:
            logger.error(f"Web search failed: {e}")
            return ToolResult(success=False, error=str(e))
