import json
import pytest
from src.agent.orchestrator import AgentOrchestrator, AgentResponse
from src.memory.manager import MemoryManager
from src.tools.registry import ToolRegistry
from src.tools.get_weather import GetWeatherTool
from src.tools.get_time import GetTimeTool
from src.tools.calculator import CalculatorTool


@pytest.fixture
def registry():
    reg = ToolRegistry()
    reg.register(GetWeatherTool())
    reg.register(GetTimeTool())
    reg.register(CalculatorTool())
    return reg


@pytest.fixture
def memory(tmp_path):
    return MemoryManager(storage_path=str(tmp_path))


class TestAgentOrchestrator:
    @pytest.mark.asyncio
    async def test_simple_response(self, registry, memory):
        """Agent responds to a prompt that doesn't match any tool."""
        agent = AgentOrchestrator(tool_registry=registry, memory=memory)
        result = await agent.process("Hello, how are you?")
        assert isinstance(result, AgentResponse)
        assert result.content != ""
        assert result.tool_calls == []

    @pytest.mark.asyncio
    async def test_weather_tool_call(self, registry, memory):
        """Agent calls get_weather when asked about weather."""
        agent = AgentOrchestrator(tool_registry=registry, memory=memory)
        result = await agent.process("What's the weather in Phoenix?")
        assert isinstance(result, AgentResponse)
        assert len(result.tool_calls) >= 1
        assert result.tool_calls[0]["tool"] == "get_weather"
        assert result.tool_calls[0]["success"] is True

    @pytest.mark.asyncio
    async def test_time_tool_call(self, registry, memory):
        """Agent calls get_time when asked about the time."""
        agent = AgentOrchestrator(tool_registry=registry, memory=memory)
        result = await agent.process("What time is it?")
        assert len(result.tool_calls) >= 1
        assert result.tool_calls[0]["tool"] == "get_time"
        assert result.tool_calls[0]["success"] is True

    @pytest.mark.asyncio
    async def test_calculator_tool_call(self, registry, memory):
        """Agent calls calculator when asked to compute."""
        agent = AgentOrchestrator(tool_registry=registry, memory=memory)
        result = await agent.process("Calculate 2 + 3 * 4")
        assert len(result.tool_calls) >= 1
        assert result.tool_calls[0]["tool"] == "calculator"
        assert result.tool_calls[0]["success"] is True

    @pytest.mark.asyncio
    async def test_conversation_memory(self, registry, memory):
        """Messages are saved to conversation memory."""
        agent = AgentOrchestrator(tool_registry=registry, memory=memory)
        await agent.process("Hello!")
        history = memory.get_history()
        assert len(history) >= 2
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Hello!"

    @pytest.mark.asyncio
    async def test_custom_llm_call(self, registry, memory):
        """Agent works with a custom LLM call function."""

        async def mock_llm(messages, tools):
            return {
                "role": "assistant",
                "content": "Custom response from mock LLM",
            }

        agent = AgentOrchestrator(
            tool_registry=registry, memory=memory, llm_call=mock_llm
        )
        result = await agent.process("Test prompt")
        assert result.content == "Custom response from mock LLM"

    @pytest.mark.asyncio
    async def test_custom_llm_with_tool_call(self, registry, memory):
        """Agent handles tool calls from a custom LLM."""
        call_count = 0

        async def mock_llm(messages, tools):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {
                                "name": "get_weather",
                                "arguments": json.dumps({"city": "Denver"}),
                            },
                        }
                    ],
                }
            else:
                return {
                    "role": "assistant",
                    "content": "The weather in Denver is great!",
                }

        agent = AgentOrchestrator(
            tool_registry=registry, memory=memory, llm_call=mock_llm
        )
        result = await agent.process("Weather in Denver?")
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["tool"] == "get_weather"
        assert result.tool_calls[0]["args"]["city"] == "Denver"
        assert result.content == "The weather in Denver is great!"

    @pytest.mark.asyncio
    async def test_unknown_tool_handled(self, registry, memory):
        """Agent handles gracefully when LLM calls a tool that doesn't exist."""

        call_count = 0

        async def mock_llm(messages, tools):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {
                                "name": "nonexistent_tool",
                                "arguments": "{}",
                            },
                        }
                    ],
                }
            else:
                return {
                    "role": "assistant",
                    "content": "Sorry, I couldn't find that tool.",
                }

        agent = AgentOrchestrator(
            tool_registry=registry, memory=memory, llm_call=mock_llm
        )
        result = await agent.process("Do something impossible")
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["success"] is False
        assert "Unknown tool" in result.tool_calls[0]["result"]
