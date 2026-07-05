import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Optional

from src.agent.prompts import SYSTEM_PROMPT
from src.config import settings
from src.memory.manager import MemoryManager
from src.tools.base import BaseTool, ToolResult
from src.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class AgentResponse:
    content: str
    tool_calls: list[dict]


def get_llm(provider: Optional[str] = None):
    """Factory: return a LangChain ChatModel for the configured provider."""
    provider = provider or settings.llm_provider
    api_key = settings.get_active_api_key()
    model = settings.get_active_model()

    if not api_key:
        return None

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        kwargs = {"api_key": api_key, "model": model}
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
        return ChatOpenAI(**kwargs)
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(api_key=api_key, model_name=model)
    elif provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(api_key=api_key, model_name=model)
    else:
        logger.warning(f"Unknown LLM provider '{provider}', falling back to openai")
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(api_key=settings.openai_api_key, model=settings.openai_model)


class AgentOrchestrator:
    """Core agent loop with swappable LLM providers and Composio Toolset integration."""

    def __init__(self, tool_registry: ToolRegistry, memory: MemoryManager, llm_call=None):
        self.registry = tool_registry
        self.memory = memory
        self._llm_call = llm_call or self._default_llm_call
        self.max_iterations = 5
        self._llm = get_llm()
        self._composio_tools = self._load_composio_tools()

    def _load_composio_tools(self) -> list:
        if not settings.composio_api_key:
            logger.info("No COMPOSIO_API_KEY set, skipping Composio tools")
            return []
        try:
            from src.tools.composio_tool import get_composio_langchain_tools
            tools = get_composio_langchain_tools()
            logger.info(f"Loaded {len(tools)} Composio tools")
            return tools
        except Exception as e:
            logger.warning(f"Failed to load Composio tools: {e}")
            return []

    async def _default_llm_call(self, messages: list[dict], tools: list[dict]) -> dict:
        if self._llm is None:
            return self._heuristic_response(messages, tools)
        try:
            from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
            lc_messages = []
            for msg in messages:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role == "system":
                    lc_messages.append(SystemMessage(content=content))
                elif role == "user":
                    lc_messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    lc_messages.append(AIMessage(content=content))
                elif role == "tool":
                    lc_messages.append(ToolMessage(content=content, tool_call_id=msg.get("tool_call_id", "unknown")))

            llm = self._llm
            if tools:
                openai_tools = [{"type": "function", "function": t} for t in tools]
                llm = llm.bind_tools(openai_tools)

            response = await llm.ainvoke(lc_messages)
            result = {"role": "assistant", "content": response.content or ""}
            if hasattr(response, "tool_calls") and response.tool_calls:
                result["tool_calls"] = [{"id": tc.get("id", f"call_{i}"), "function": {"name": tc["name"], "arguments": json.dumps(tc.get("args", {}))}} for i, tc in enumerate(response.tool_calls)]
            return result
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return self._heuristic_response(messages, tools)

    def _heuristic_response(self, messages: list[dict], tools: list[dict]) -> dict:
        if messages and messages[-1].get("role") == "tool":
            return {"role": "assistant", "content": f"Here are the results: {messages[-1].get('content', '')}"}
        user_msg = ""
        for m in reversed(messages):
            if m["role"] == "user":
                user_msg = m["content"].lower()
                break
        for tool in tools:
            tool_name = tool["name"]
            if tool_name == "get_weather" and any(w in user_msg for w in ["weather", "temperature", "forecast"]):
                city = user_msg.split("in ")[-1].strip().rstrip("?.") if "in " in user_msg else "Unknown"
                return {"role": "assistant", "content": "", "tool_calls": [{"id": "call_1", "function": {"name": "get_weather", "arguments": json.dumps({"city": city})}}]}
            elif tool_name == "get_time" and any(w in user_msg for w in ["time", "date", "clock"]):
                return {"role": "assistant", "content": "", "tool_calls": [{"id": "call_1", "function": {"name": "get_time", "arguments": "{}"}}]}
            elif tool_name == "calculator" and any(w in user_msg for w in ["calculate", "math", "compute", "+"]):
                expr = user_msg
                for prefix in ["calculate ", "compute ", "what is ", "what's "]:
                    if prefix in expr:
                        expr = expr.split(prefix)[-1].strip().rstrip("?.")
                        break
                return {"role": "assistant", "content": "", "tool_calls": [{"id": "call_1", "function": {"name": "calculator", "arguments": json.dumps({"expression": expr})}}]}
        return {"role": "assistant", "content": "I received your message. How can I help you further?"}

    async def process(self, user_prompt: str) -> AgentResponse:
        self.memory.save_message("user", user_prompt)
        memory_context = self.memory.get_system_context()
        system_msg = SYSTEM_PROMPT.format(memory_context=memory_context)
        messages = [{"role": "system", "content": system_msg}]
        messages.extend(self.memory.get_history())
        tool_schemas = self.registry.list_tools()
        tool_call_log = []

        for iteration in range(self.max_iterations):
            assistant_msg = await self._llm_call(messages, tool_schemas)
            messages.append(assistant_msg)
            if "tool_calls" not in assistant_msg or not assistant_msg["tool_calls"]:
                final_content = assistant_msg.get("content", "")
                self.memory.save_message("assistant", final_content)
                return AgentResponse(content=final_content, tool_calls=tool_call_log)

            for tc in assistant_msg["tool_calls"]:
                func_name = tc["function"]["name"]
                func_args_str = tc["function"]["arguments"]
                call_id = tc.get("id", f"call_{iteration}")
                try:
                    func_args = json.loads(func_args_str)
                except json.JSONDecodeError:
                    func_args = {}
                tool = self.registry.get(func_name)
                if tool is None:
                    result = ToolResult(success=False, error=f"Unknown tool: {func_name}")
                else:
                    try:
                        result = await asyncio.wait_for(tool.execute(**func_args), timeout=settings.tool_timeout_seconds)
                    except asyncio.TimeoutError:
                        result = ToolResult(success=False, error=f"Tool '{func_name}' timed out")
                    except Exception as e:
                        result = ToolResult(success=False, error=str(e))
                tool_call_log.append({"tool": func_name, "args": func_args, "result": result.data if result.success else result.error, "success": result.success})
                messages.append({"role": "tool", "tool_call_id": call_id, "content": result.to_str()})

        final_content = messages[-1].get("content", "Max iterations reached.")
        self.memory.save_message("assistant", final_content)
        return AgentResponse(content=final_content, tool_calls=tool_call_log)
