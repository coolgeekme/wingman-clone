import asyncio
import pytest
from src.tools.base import BaseTool, ToolResult
from src.tools.registry import ToolRegistry
from src.tools.get_weather import GetWeatherTool
from src.tools.get_time import GetTimeTool
from src.tools.calculator import CalculatorTool


class TestToolResult:
    def test_success_to_str(self):
        r = ToolResult(success=True, data={"temp": 75})
        assert "75" in r.to_str()

    def test_error_to_str(self):
        r = ToolResult(success=False, error="Connection failed")
        assert "Error: Connection failed" == r.to_str()


class TestGetWeatherTool:
    @pytest.fixture
    def tool(self):
        return GetWeatherTool()

    def test_name(self, tool):
        assert tool.name == "get_weather"

    def test_has_parameters(self, tool):
        assert "city" in tool.parameters["properties"]

    @pytest.mark.asyncio
    async def test_execute_returns_success(self, tool):
        result = await tool.execute(city="Phoenix, AZ")
        assert result.success is True
        assert result.data["city"] == "Phoenix, AZ"
        assert "temperature_f" in result.data
        assert "condition" in result.data
        assert "humidity_pct" in result.data

    @pytest.mark.asyncio
    async def test_execute_unknown_city(self, tool):
        result = await tool.execute()
        assert result.success is True
        assert result.data["city"] == "Unknown"


class TestGetTimeTool:
    @pytest.fixture
    def tool(self):
        return GetTimeTool()

    def test_name(self, tool):
        assert tool.name == "get_time"

    @pytest.mark.asyncio
    async def test_execute_returns_time(self, tool):
        result = await tool.execute()
        assert result.success is True
        assert "utc_time" in result.data
        assert "date" in result.data
        assert "time" in result.data


class TestCalculatorTool:
    @pytest.fixture
    def tool(self):
        return CalculatorTool()

    def test_name(self, tool):
        assert tool.name == "calculator"

    @pytest.mark.asyncio
    async def test_simple_addition(self, tool):
        result = await tool.execute(expression="2 + 3")
        assert result.success is True
        assert result.data["result"] == 5

    @pytest.mark.asyncio
    async def test_complex_expression(self, tool):
        result = await tool.execute(expression="2 + 3 * 4")
        assert result.success is True
        assert result.data["result"] == 14

    @pytest.mark.asyncio
    async def test_power(self, tool):
        result = await tool.execute(expression="2 ** 10")
        assert result.success is True
        assert result.data["result"] == 1024

    @pytest.mark.asyncio
    async def test_division(self, tool):
        result = await tool.execute(expression="10 / 3")
        assert result.success is True
        assert abs(result.data["result"] - 3.333333) < 0.01

    @pytest.mark.asyncio
    async def test_invalid_expression(self, tool):
        result = await tool.execute(expression="import os")
        assert result.success is False
        assert "Cannot evaluate" in result.error

    @pytest.mark.asyncio
    async def test_division_by_zero(self, tool):
        result = await tool.execute(expression="1 / 0")
        assert result.success is False


class TestToolRegistry:
    def test_register_and_get(self):
        reg = ToolRegistry()
        tool = GetWeatherTool()
        reg.register(tool)
        assert reg.get("get_weather") is tool

    def test_get_unknown(self):
        reg = ToolRegistry()
        assert reg.get("nonexistent") is None

    def test_list_tools(self):
        reg = ToolRegistry()
        reg.register(GetWeatherTool())
        reg.register(GetTimeTool())
        schemas = reg.list_tools()
        assert len(schemas) == 2
        names = {s["name"] for s in schemas}
        assert names == {"get_weather", "get_time"}

    def test_auto_discover(self):
        reg = ToolRegistry()
        reg.auto_discover()
        names = {t["name"] for t in reg.list_tools()}
        assert "get_weather" in names
        assert "get_time" in names
        assert "calculator" in names

    def test_get_all(self):
        reg = ToolRegistry()
        reg.register(GetWeatherTool())
        reg.register(CalculatorTool())
        all_tools = reg.get_all()
        assert len(all_tools) == 2
