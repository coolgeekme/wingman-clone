import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Optional, List, Any

from src.agent.prompts import SYSTEM_PROMPT
from src.config import settings
from src.memory.manager import MemoryManager
from src.tools.base import BaseTool, ToolResult
from src.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

# Super-Brain v3.4 Configuration
SUPERBRAIN_CONFIG = {
    "max_iterations_simple": 10,
    "max_iterations_complex": 15,
    "groq_retry_limit": 3,
    "tool_timeout": 60,
    "composio_timeout": 90,
    "temperature": 0,
}

COMPLEX_TASK_PATTERNS = [
    r"(check|look at|review).*(and|then).*(send|create|update|schedule)",
    r"(summarize|analyze).*(emails?|calendar|messages?)",
    r"(set up|configure|deploy|build)",
    r"(compare|research|investigate)",
    r"(morning|daily|weekly)\s*(brief|update|report|summary)",
]

NESTED_JSON_PATTERNS = [
    r"<function=([\w_]+)\s*(\{.*?\})</function>",
    r"<function=([\w_]+)\s*(\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\})</function>",
    r"<function=(\w+)\s*(\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\})></function>",
    r"<function=(\w+)\s*(\{.*?\})></function>",
    r'\{"name":\s*"(\w+)",\s*"arguments":\s*(\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\})\}',
    r'```(?:json)?\s*\{"name":\s*"(\w+)",\s*"arguments":\s*(\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\})\}\s*```',
    r'<function\s*=\s*(\w+)\s*>\s*(\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\})\s*</function>',
]


@dataclass
class AgentResponse:
    content: str
    tool_calls: list[dict]
    iterations_used: int = 0


def get_llm(provider: Optional[str] = None):
    provider = provider or settings.llm_provider
    api_key = settings.get_active_api_key()
    model = settings.get_active_model()
    if not api_key:
        return None
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(api_key=api_key, model=model, temperature=SUPERBRAIN_CONFIG["temperature"])
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(api_key=api_key, model_name=model, temperature=SUPERBRAIN_CONFIG["temperature"])
    elif provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(api_key=api_key, model_name=model, temperature=SUPERBRAIN_CONFIG["temperature"], max_tokens=4096)
    else:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(api_key=settings.openai_api_key, model=settings.openai_model)


def _is_complex_task(prompt: str) -> bool:
    prompt_lower = prompt.lower()
    for pattern in COMPLEX_TASK_PATTERNS:
        if re.search(pattern, prompt_lower):
            return True
    if len(prompt.split('.')) > 3 or len(prompt) > 300:
        return True
    return False


def _greedy_extract_json(text: str) -> Optional[str]:
    start = text.find('{')
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape_next = False
    for i in range(start, len(text)):
        char = text[i]
        if escape_next:
            escape_next = False
            continue
        if char == '\\' and in_string:
            escape_next = True
            continue
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                candidate = text[start:i + 1]
                try:
                    json.loads(candidate)
                    return candidate
                except json.JSONDecodeError:
                    start = text.find('{', i + 1)
                    if start == -1:
                        return None
                    depth = 0
                    continue
    return None


def _reinforce_tool_name(func_name: str, known_tools: list[str]) -> str:
    if func_name in known_tools:
        return func_name
    func_lower = func_name.lower()
    for known in known_tools:
        if known.lower() == func_lower:
            return known
    return func_name


class AgentOrchestrator:
    def __init__(self, tool_registry: ToolRegistry, memory: MemoryManager):
        self.registry = tool_registry
        self.memory = memory
        self._llm = get_llm()
        self._composio_tools = self._load_composio_tools()
        self._known_tool_names = self._build_tool_name_index()

    def _get_max_iterations(self, prompt: str) -> int:
        if _is_complex_task(prompt):
            return SUPERBRAIN_CONFIG["max_iterations_complex"]
        return SUPERBRAIN_CONFIG["max_iterations_simple"]

    def _build_tool_name_index(self) -> list[str]:
        names = []
        for tool_schema in self.registry.list_tools():
            names.append(tool_schema.get('name', ''))
        for t in self._composio_tools:
            names.append(getattr(t, 'name', ''))
        return [n for n in names if n]

    def _load_composio_tools(self) -> list:
        if not settings.composio_api_key:
            return []
        try:
            from src.tools.composio_tool import get_composio_langchain_tools
            tools = get_composio_langchain_tools(apps=["gmail", "googlecalendar", "github", "slack", "notion"])
            return tools
        except Exception as e:
            logger.warning(f"Failed to load Composio tools: {e}")
            return []

    def _prepare_tools(self, native_tools: list) -> list:
        all_tools = []
        if native_tools: all_tools.extend(native_tools)
        if self._composio_tools: all_tools.extend(self._composio_tools)
        
        # Groq/OpenAI limit
        if len(all_tools) > 40:
            return all_tools[:40]
        return all_tools

    async def _call_llm(self, messages: list[dict], tools: list[Any], retry_count: int = 0) -> dict:
        if self._llm is None:
            return {"role": "assistant", "content": "AI not configured."}
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
                    # FIX: Pass tool_calls back to LangChain so the next ToolMessage has a valid parent
                    tool_calls = []
                    if "tool_calls" in msg:
                        for tc in msg["tool_calls"]:
                            try:
                                args = json.loads(tc["function"]["arguments"])
                            except:
                                args = {}
                            tool_calls.append({
                                "id": tc.get("id"),
                                "name": tc["function"]["name"],
                                "args": args
                            })
                    lc_messages.append(AIMessage(content=content, tool_calls=tool_calls))
                elif role == "tool":
                    lc_messages.append(ToolMessage(content=content, tool_call_id=msg.get("tool_call_id", "unknown")))
            
            llm = self._llm
            all_tools = self._prepare_tools(tools)
            if all_tools:
                llm = llm.bind_tools(all_tools)
            
            response = await llm.ainvoke(lc_messages)
            
            result = {"role": "assistant", "content": response.content or ""}
            if hasattr(response, "tool_calls") and response.tool_calls:
                result["tool_calls"] = [
                    {
                        "id": tc.get("id", f"call_{i}"),
                        "function": {
                            "name": _reinforce_tool_name(tc["name"], self._known_tool_names),
                            "arguments": json.dumps(tc.get("args", {}))
                        }
                    }
                    for i, tc in enumerate(response.tool_calls)
                ]
            
            # Hallucination recovery fallback
            if not result.get("tool_calls") and result["content"] and "<function=" in result["content"]:
                recovered = self._recover_tool_call_v33(result["content"], 99)
                if recovered:
                    result["tool_calls"] = recovered["tool_calls"]
                    result["content"] = re.sub(r"<function=.*?</function>", "", result["content"], flags=re.DOTALL).strip()

            return result
        except Exception as e:
            error_str = str(e)
            if "failed_generation" in error_str:
                recovered = self._recover_tool_call_v33(error_str, retry_count)
                if recovered: return recovered
            
            if retry_count < SUPERBRAIN_CONFIG["groq_retry_limit"]:
                if any(kw in error_str.lower() for kw in ["rate_limit", "timeout", "503"]):
                    await asyncio.sleep((retry_count + 1) * 2)
                    return await self._call_llm(messages, tools, retry_count + 1)
            
            return {"role": "assistant", "content": f"Neural error: {error_str}"}

    def _recover_tool_call_v33(self, error_str: str, retry_count: int) -> Optional[dict]:
        for pattern in NESTED_JSON_PATTERNS:
            match = re.search(pattern, error_str, re.DOTALL)
            if match:
                func_name = match.group(1)
                raw_args = match.group(2).strip()
                try:
                    json.loads(raw_args)
                    func_name = _reinforce_tool_name(func_name, self._known_tool_names)
                    return {"role": "assistant", "content": "", "tool_calls": [{"id": f"recovered_{retry_count}", "function": {"name": func_name, "arguments": raw_args}}]}
                except: continue
        return None

    async def process(self, user_prompt: str, history: Optional[List[dict]] = None) -> AgentResponse:
        self.memory.save_message("user", user_prompt)
        system_msg = SYSTEM_PROMPT.format(memory_context=self.memory.get_system_context())
        messages = [{"role": "system", "content": system_msg}]
        if history:
            messages.extend(history)
        else:
            messages.extend(self.memory.get_history()[:-1])
        messages.append({"role": "user", "content": user_prompt})

        native_schemas = self.registry.list_tools()
        tool_call_log = []
        max_iter = self._get_max_iterations(user_prompt)

        for iteration in range(max_iter):
            assistant_msg = await self._call_llm(messages, native_schemas)
            messages.append(assistant_msg)
            
            if "tool_calls" not in assistant_msg or not assistant_msg["tool_calls"]:
                final_content = assistant_msg.get("content", "")
                if final_content: self.memory.save_message("assistant", final_content)
                return AgentResponse(content=final_content, tool_calls=tool_call_log, iterations_used=iteration+1)

            for tc in assistant_msg["tool_calls"]:
                func_name = tc["function"]["name"]
                func_args_str = tc["function"]["arguments"]
                call_id = tc.get("id", f"call_{iteration}")

                try:
                    func_args = json.loads(func_args_str)
                except:
                    func_args = {}

                tool = self.registry.get(func_name)
                comp_tool = next((t for t in self._composio_tools if t.name == func_name), None)

                result_text = ""
                success = False
                try:
                    if tool:
                        res_obj = await tool.execute(**func_args)
                        result_text = res_obj.to_str()
                        success = res_obj.success
                    elif comp_tool:
                        comp_res = await comp_tool.ainvoke(func_args)
                        result_text = str(comp_res)
                        success = True
                    else:
                        result_text = f"Error: Tool {func_name} not found."
                except Exception as e:
                    result_text = f"Error: {str(e)}"

                tool_call_log.append({"tool": func_name, "args": func_args, "result": result_text[:500], "success": success})
                messages.append({"role": "tool", "tool_call_id": call_id, "content": result_text})

        return AgentResponse(content=messages[-1].get("content", "Max iterations reached."), tool_calls=tool_call_log, iterations_used=max_iter)
