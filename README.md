# Wingman Clone

A modular, extensible AI personal assistant framework built with FastAPI and Python.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set your OpenAI API key (optional — works without it using heuristic mode)
export OPENAI_API_KEY=sk-your-key-here

# Run the server
uvicorn src.main:app --reload

# Test it
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is the weather in Phoenix?"}'
```

## Adding a New Tool

1. Create `src/tools/my_tool.py`
2. Subclass `BaseTool`:

```python
from src.tools.base import BaseTool, ToolResult

class MyTool(BaseTool):
    name = "my_tool"
    description = "Does something useful"
    parameters = {
        "type": "object",
        "properties": {"input": {"type": "string"}},
        "required": ["input"],
    }

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, data="result")
```

3. Done! The tool is auto-discovered on startup.

## Run Tests

```bash
python -m pytest tests/ -x -q
```

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for full system design.

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the integration roadmap.
