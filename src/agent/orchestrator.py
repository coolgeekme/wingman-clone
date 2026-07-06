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

# Hallucination-Proof v3.3 Configuration
SUPERBRAIN_CONFIG = {
    "max_iterations_simple": 10,
    "max_iterations_complex": 15,
    "groq_retry_limit": 3,
    "tool_timeout": 45,
    "composio_timeout": 60,
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
        return ChatGroq(api_key=api_key, model_name=model, temperature=SUPERBRAIN_CONFIG["temperature"], max_tokens=4096, model_kwargs={"top_p": 0.85})
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
            logger.info(f"Tool-name reinforcement: '{func_name}' -> '{known}' (case fix)")
            return known
    candidates = [k for k in known_tools if k.lower().startswith(func_lower)]
    if len(candidates) == 1:
        logger.info(f"Tool-name reinforcement: '{func_name}' -> '{candidates[0]}' (prefix match)")
        return candidates[0]
    candidates = [k for k in known_tools if func_lower in k.lower()]
    if len(candidates) == 1:
        logger.info(f"Tool-name reinforcement: '{func_name}' -> '{candidates[0]}' (contains match)")
        return candidates[0]
    normalized = re.sub(r'([A-Z])', r'_\1', func_name).upper().lstrip('_')
    for known in known_tools:
        if known == normalized:
            logger.info(f"Tool-name reinforcement: '{func_name}' -> '{known}' (camelCase fix)")
            return known
    return func_name


class AgentOrchestrator:
    def __init__(self, tool_registry: ToolRegistry, memory: MemoryManager):
        self.registry = tool_registry
        self.memory = memory
        self._llm = get_llm()
        self._composio_tools = self._load_composio_tools()
        self._known_tool_names = self._build_tool_name_index()

    @property
    def max_iterations(self) -> int:
        return SUPERBRAIN_CONFIG["max_iterations_simple"]

    def _get_max_iterations(self, prompt: str) -> int:
        if _is_complex_task(prompt):
            return SUPERBRAIN_CONFIG["max_iterations_complex"]
        return SUPERBRAIN_CONFIG["max_iterations_simple"]

    def _build_tool_name_index(self) -> list[str]:
        names = []
        for tool_schema in self.registry.list_tools():
            if hasattr(tool_schema, 'name'):
                names.append(tool_schema.name)
            elif isinstance(tool_schema, dict) and 'name' in tool_schema:
                names.append(tool_schema['name'])
        for t in self._composio_tools:
            if hasattr(t, 'name'):
                names.append(t.name)
        logger.info(f"v3.3 Tool-name index built: {len(names)} tools registered")
        return names

    def _load_composio_tools(self) -> list:
        if not settings.composio_api_key:
            return []
        try:
            from src.tools.composio_tool import get_composio_langchain_tools
            tools = get_composio_langchain_tools(apps=["gmail", "googlecalendar", "github", "slack", "notion"])
            logger.info(f"Hallucination-Proof v3.3 loaded {len(tools)} Composio tools")
            return tools
        except Exception as e:
            logger.warning(f"Failed to load Composio tools: {e}")
            return []

    def _prepare_groq_tools(self, native_tools: list, composio_tools: list) -> list:
        all_tools = []
        if native_tools:
            all_tools.extend(native_tools)
        if composio_tools:
            priority_prefixes = ["GMAIL_", "GOOGLECALENDAR_", "GITHUB_"]
            prioritized = []
            others = []
            for t in composio_tools:
                name = getattr(t, 'name', '')
                if any(name.startswith(p) for p in priority_prefixes):
                    prioritized.append(t)
                else:
                    others.append(t)
            max_tools = 40
            all_tools.extend(prioritized[:max_tools])
            remaining = max_tools - len(prioritized[:max_tools])
            if remaining > 0:
                all_tools.extend(others[:remaining])
        return all_tools

    async def _call_llm(self, messages: list[dict], tools: list[Any], retry_count: int = 0) -> dict:
        if self._llm is None:
            return {"role": "assistant", "content": "AI not configured. Check LLM API key."}
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
            is_groq = settings.llm_provider == "groq"
            if is_groq:
                all_tools = self._prepare_groq_tools(tools, self._composio_tools)
            else:
                all_tools = []
                if tools:
                    all_tools.extend(tools)
                if self._composio_tools:
                    all_tools.extend(self._composio_tools)
            if all_tools:
                llm = llm.bind_tools(all_tools)
            response = await llm.ainvoke(lc_messages)
            result = {"role": "assistant", "content": response.content or ""}
            if hasattr(response, "tool_calls") and response.tool_calls:
                result["tool_calls"] = [{"id": tc.get("id", f"call_{i}"), "function": {"name": _reinforce_tool_name(tc["name"], self._known_tool_names), "arguments": json.dumps(tc.get("args", {}))}} for i, tc in enumerate(response.tool_calls)]
            return result
        except Exception as e:
            error_str = str(e)
            logger.error(f"LLM call failed (attempt {retry_count + 1}): {error_str}")
            if "failed_generation" in error_str or "tool_call" in error_str.lower():
                recovered = self._recover_tool_call_v33(error_str, retry_count)
                if recovered:
                    return recovered
            if retry_count < SUPERBRAIN_CONFIG["groq_retry_limit"]:
                if any(keyword in error_str.lower() for keyword in ["rate_limit", "timeout", "503", "502", "overloaded"]):
                    wait_time = (retry_count + 1) * 2
                    logger.info(f"Retrying LLM call in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    return await self._call_llm(messages, tools, retry_count + 1)
            return {"role": "assistant", "content": f"Neural error: {error_str}"}

    def _recover_tool_call_v33(self, error_str: str, retry_count: int) -> Optional[dict]:
        for pattern in NESTED_JSON_PATTERNS:
            match = re.search(pattern, error_str, re.DOTALL)
            if match:
                func_name = match.group(1)
                raw_args = match.group(2).strip() if match.group(2) else "{}"
                try:
                    json.loads(raw_args)
                    func_name = _reinforce_tool_name(func_name, self._known_tool_names)
                    logger.info(f"v3.3 Regex recovery: {func_name}")
                    return {"role": "assistant", "content": "", "tool_calls": [{"id": f"recovered_call_{retry_count}", "function": {"name": func_name, "arguments": raw_args}}]}
                except json.JSONDecodeError:
                    continue
        name_match = re.search(r"<function=(\w+)", error_str)
        if not name_match:
            name_match = re.search(r'"name":\s*"(\w+)"', error_str)
        if name_match:
            func_name = name_match.group(1)
            start_idx = name_match.end()
            remaining = error_str[start_idx:]
            extracted_json = _greedy_extract_json(remaining)
            if extracted_json:
                func_name = _reinforce_tool_name(func_name, self._known_tool_names)
                logger.info(f"v3.3 Greedy recovery: {func_name} with nested JSON")
                return {"role": "assistant", "content": "", "tool_calls": [{"id": f"recovered_greedy_{retry_count}", "function": {"name": func_name, "arguments": extracted_json}}]}
        simple_match = re.search(r"<function=(\w+)\s*({.*?})></function>", error_str, re.DOTALL)
        if simple_match:
            func_name = simple_match.group(1)
            raw_args = simple_match.group(2).strip()
            try:
                json.loads(raw_args)
            except json.JSONDecodeError:
                raw_args = "{}"
            func_name = _reinforce_tool_name(func_name, self._known_tool_names)
            logger.info(f"v3.3 Simple recovery fallback: {func_name}")
            return {"role": "assistant", "content": "", "tool_calls": [{"id": f"recovered_simple_{retry_count}", "function": {"name": func_name, "arguments": raw_args}}]}
        logger.warning("v3.3: All recovery strategies exhausted")
        return None

    async def process(self, user_prompt: str, history: Optional[List[dict]] = None) -> AgentResponse:
        self.memory.save_message("user", user_prompt)
        memory_context = self.memory.get_system_context()
        system_msg = SYSTEM_PROMPT.format(memory_context=memory_context)
        messages = [{"role": "system", "content": system_msg}]
        if history:
            messages.extend(history)
        else:
            messages.extend(self.memory.get_history()[:-1])
        messages.append({"role": "user", "content": user_prompt})
        native_schemas = self.registry.list_tools()
        tool_call_log = []
        max_iter = self._get_max_iterations(user_prompt)
        logger.info(f"Hallucination-Proof v3.3 processing | max_iterations={max_iter} | complex={_is_complex_task(user_prompt)} | tools_indexed={len(self._known_tool_names)}")
        for iteration in range(max_iter):
            assistant_msg = await self._call_llm(messages, native_schemas)
            messages.append(assistant_msg)
            if "tool_calls" not in assistant_msg or not assistant_msg["tool_calls"]:
                final_content = assistant_msg.get("content", "")
                if final_content:
                    self.memory.save_message("assistant", final_content)
                return AgentResponse(content=final_content, tool_calls=tool_call_log, iterations_used=iteration + 1)
            for tc in assistant_msg["tool_calls"]:
                func_name = tc["function"]["name"]
                func_args_str = tc["function"]["arguments"]
                call_id = tc.get("id", f"call_{iteration}")
                func_name = _reinforce_tool_name(func_name, self._known_tool_names)
                try:
                    clean_args = func_args_str.replace("'", '"')
                    clean_args = re.sub(r',\s*}', '}', clean_args)
                    clean_args = re.sub(r',\s*]', ']', clean_args)
                    extracted = _greedy_extract_json(clean_args)
                    if extracted:
                        func_args = json.loads(extracted)
                    else:
                        func_args = json.loads(clean_args)
                except json.JSONDecodeError:
                    try:
                        pairs = re.findall(r'(\w+)\s*[=:]\s*"?([^",}]+)"?', func_args_str)
                        func_args = {k: v.strip() for k, v in pairs} if pairs else {}
                    except Exception:
                        func_args = {}
                    logger.warning(f"v3.3 force-parsed args for {func_name}: {func_args}")
                tool = self.registry.get(func_name)
                comp_tool = next((t for t in self._composio_tools if t.name == func_name), None)
                result_text = ""
                success = False
                try:
                    if tool:
                        timeout = SUPERBRAIN_CONFIG["tool_timeout"]
                        res_obj = await asyncio.wait_for(tool.execute(**func_args), timeout=timeout)
                        result_text = res_obj.to_str()
                        success = res_obj.success
                    elif comp_tool:
                        timeout = SUPERBRAIN_CONFIG["composio_timeout"]
                        comp_res = await asyncio.wait_for(comp_tool.ainvoke(func_args), timeout=timeout)
                        result_text = str(comp_res)
                        success = True
                    else:
                        similar = [n for n in self._known_tool_names if func_name.split('_')[0] in n][:5]
                        suggestion = f" Did you mean one of: {similar}" if similar else ""
                        result_text = f"Error: Tool '{func_name}' not found.{suggestion}"
                        logger.warning(f"Tool not found: {func_name} | suggestions: {similar}")
                except asyncio.TimeoutError:
                    result_text = f"Tool '{func_name}' timed out after {timeout}s."
                    logger.error(f"Tool timeout: {func_name}")
                except Exception as e:
                    result_text = f"Error executing {func_name}: {str(e)}"
                    logger.error(f"Tool execution error: {func_name} - {str(e)}")
                tool_call_log.append({"tool": func_name, "args": func_args, "result": result_text[:500], "success": success, "iteration": iteration})
                messages.append({"role": "tool", "tool_call_id": call_id, "content": result_text})
        final_msg = messages[-1].get("content", "")
        if not final_msg:
            final_msg = "I've been working on this but hit my processing limit. Here's what I accomplished so far."
        self.memory.save_message("assistant", final_msg)
        return AgentResponse(content=final_msg, tool_calls=tool_call_log, iterations_used=max_iter)
