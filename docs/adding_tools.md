# Adding New Tools to Wingman Clone

## Overview

The Tool Sandbox uses **auto-discovery** — any Python file in `src/tools/` that contains a `BaseTool` subclass is automatically registered on startup. No configuration changes needed.

## Step-by-Step

### 1. Create the tool file

Create `src/tools/my_tool.py`:

```python
from src.tools.base import BaseTool, ToolResult


class MyTool(BaseTool):
    name = "my_tool"
    description = "Brief description of what this tool does. The LLM reads this to decide when to use it."
    parameters = {
        "type": "object",
        "properties": {
            "input_param": {
                "type": "string",
                "description": "What this parameter is for",
            }
        },
        "required": ["input_param"],
    }

    async def execute(self, **kwargs) -> ToolResult:
        input_val = kwargs.get("input_param", "")
        
        # Your logic here
        result = f"Processed: {input_val}"
        
        return ToolResult(success=True, data=result)
```

### 2. That's it!

Restart the server and the tool will be available:
- Listed at `GET /tools`
- Available to the agent in the chat loop
- The LLM will use it when the user's request matches the tool's description

### Tips

- **Description matters**: The LLM decides which tool to call based on the `description`. Be specific and clear.
- **Parameter descriptions**: Help the LLM understand what to pass. Include examples.
- **Error handling**: Return `ToolResult(success=False, error="message")` for expected errors.
- **Async**: All tools are async. Use `httpx` for HTTP calls, not `requests`.
- **Secrets**: Read API keys from environment variables, never from tool parameters.
