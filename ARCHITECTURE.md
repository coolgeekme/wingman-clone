# Wingman Clone — Architecture Document

## Overview

Wingman Clone is a modular, extensible AI personal assistant framework. It receives natural language prompts, orchestrates tool calls via an AI agent loop, persists memory across sessions, and integrates with external services (social media, Notion, etc.).

The system is designed so that **adding a new tool is as simple as dropping a Python module into the `tools/` directory** — no changes to the core agent loop required.

---

## 1. Tech Stack

| Layer              | Technology           | Rationale                                                        |
|--------------------|----------------------|------------------------------------------------------------------|
| **Backend / API**  | FastAPI (Python)     | Async-native, automatic OpenAPI docs, lightweight, fast.         |
| **AI Orchestration** | LangChain           | Mature tool-calling abstractions, model-agnostic, streaming.     |
| **LLM Provider**   | OpenAI (gpt-4o)     | Best tool-calling support; swappable via LangChain.              |
| **Memory Store**   | SQLite + JSON files  | Zero-infra for dev; replaceable with PostgreSQL / Redis later.   |
| **Task Queue**     | (future) Celery/ARQ  | For scheduled tasks and background processing.                   |

---

## 2. System Architecture

```
+----------------------------------------------------------+
|                     Delivery Channels                    |
|         (Telegram, Slack, Web UI, REST API)              |
+----------------------+-----------------------------------+
                       |  HTTP / WebSocket
                       v
+----------------------------------------------------------+
|                   FastAPI Gateway                         |
|  - /chat  -- synchronous prompt -> response              |
|  - /chat/stream -- SSE streaming                         |
|  - /tools -- list registered tools                       |
|  - /memory -- read/write persistent memory               |
+----------------------+-----------------------------------+
                       |
                       v
+----------------------------------------------------------+
|                  Agent Orchestrator                       |
|            (LangChain AgentExecutor)                      |
|                                                          |
|  1. Receive user prompt + conversation history            |
|  2. LLM decides: respond directly OR call tool(s)        |
|  3. If tool call -> dispatch to Tool Sandbox              |
|  4. Feed tool result back to LLM                          |
|  5. Repeat until LLM produces final answer                |
|  6. Persist conversation to Memory Store                  |
+--------+-------------------------+-----------------------+
         |                         |
         v                         v
+-----------------+    +----------------------------------+
|  Memory System   |    |         Tool Sandbox              |
|                  |    |                                    |
| - ConversationMem|    |  Auto-discovers tools from        |
| - Durable Facts  |    |  src/tools/*.py                   |
| - User Prefs     |    |                                    |
|                  |    |  Each tool is a class with:        |
| Storage:         |    |    - name: str                     |
|  SQLite (dev)    |    |    - description: str              |
|  PostgreSQL(prod)|    |    - parameters: JSON Schema       |
|                  |    |    - execute(**kwargs) -> result    |
+-----------------+    |                                    |
                       |  Tools run in isolated context      |
                       |  with timeout + error handling.     |
                       +----------------------------------+
```

---

## 3. Tool Sandbox — Design

### 3.1 Philosophy

The Tool Sandbox is the **plugin system** of Wingman Clone. It mirrors the architecture of modern AI agent frameworks where:

- **Tools are self-describing**: Each tool declares its name, description, and JSON Schema parameters. The LLM uses these descriptions to decide when and how to call them.
- **Tools are auto-discovered**: Drop a `.py` file in `src/tools/`, subclass `BaseTool`, and it's available to the agent on next restart.
- **Tools are sandboxed**: Each execution has a timeout, structured error handling, and runs in an isolated async context.

### 3.2 BaseTool Interface

```python
# src/tools/base.py
class BaseTool(ABC):
    name: str                    # Unique identifier (e.g., "get_weather")
    description: str             # What the tool does (shown to LLM)
    parameters: dict             # JSON Schema for input validation

    async def execute(self, **kwargs) -> ToolResult:
        """Run the tool. Returns structured result or error."""

    def to_langchain_tool(self) -> StructuredTool:
        """Convert to LangChain-compatible tool for AgentExecutor."""
```

### 3.3 Adding a New Tool (3-step process)

1. Create `src/tools/my_tool.py`
2. Subclass `BaseTool`, implement `execute()`
3. That's it — the registry auto-discovers it on startup.

### 3.4 Execution Safety

| Concern        | Mitigation                                      |
|----------------|--------------------------------------------------|
| Timeout        | `asyncio.wait_for()` with configurable limit     |
| Exceptions     | Caught and returned as `ToolResult(error=...)`   |
| Injection      | Input validated against JSON Schema before exec  |
| Rate limits    | Per-tool rate limiter (token bucket)              |
| Secrets        | Tools read credentials from env vars, not args   |

---

## 4. Memory System — Design

### 4.1 Three Layers of Memory

| Layer                | What it stores                        | Lifetime          | Storage          |
|----------------------|---------------------------------------|--------------------|------------------|
| **Conversation**     | Message history for current session   | Per-session        | In-memory list   |
| **Durable Facts**    | User name, timezone, preferences      | Permanent          | SQLite / JSON    |
| **Episodic**         | Summaries of past conversations       | Permanent          | SQLite           |

### 4.2 How It Works

```
User says: "My name is Marcus and I'm in Phoenix, AZ"

Agent Orchestrator:
  1. Processes prompt with LLM
  2. LLM responds AND the system detects durable facts
  3. Memory Manager saves:
     - conversation_memory: append message pair
     - durable_facts: { "user_name": "Marcus", "timezone": "America/Phoenix" }

Next session:
  Agent loads durable_facts into system prompt ->
  "You know the user's name is Marcus, timezone is America/Phoenix"
```

### 4.3 Implementation

```python
# src/memory/manager.py
class MemoryManager:
    def __init__(self, storage_path: str):
        self.conversation = ConversationMemory()   # In-memory, per session
        self.durable = DurableMemory(storage_path)  # SQLite-backed
    
    def get_context(self) -> str:
        """Build context string for LLM system prompt."""
    
    def save_message(self, role: str, content: str):
        """Append to conversation history."""
    
    def save_fact(self, key: str, value: str):
        """Persist a durable fact."""
    
    def get_fact(self, key: str) -> Optional[str]:
        """Retrieve a durable fact."""
```

---

## 5. Directory Structure

```
wingman-clone/
|-- ARCHITECTURE.md          # This document
|-- ROADMAP.md               # Integration roadmap
|-- README.md                # Quick start guide
|-- requirements.txt         # Python dependencies
|-- pyproject.toml           # Project metadata
|-- .env.example             # Environment variable template
|
|-- src/
|   |-- __init__.py
|   |-- main.py              # FastAPI app entry point
|   |-- config.py            # Settings via pydantic-settings
|   |
|   |-- agent/
|   |   |-- __init__.py
|   |   |-- orchestrator.py  # Core agent loop
|   |   +-- prompts.py       # System prompts and templates
|   |
|   |-- tools/
|   |   |-- __init__.py
|   |   |-- base.py          # BaseTool ABC + ToolResult
|   |   |-- registry.py      # Auto-discovery and registration
|   |   |-- get_weather.py   # Example: dummy weather tool
|   |   |-- get_time.py      # Example: current time tool
|   |   +-- calculator.py    # Example: math calculator tool
|   |
|   |-- memory/
|   |   |-- __init__.py
|   |   |-- manager.py       # MemoryManager (conversation + durable)
|   |   |-- conversation.py  # In-memory conversation buffer
|   |   +-- durable.py       # SQLite-backed persistent facts
|   |
|   +-- integrations/        # Future: social media, Notion, etc.
|       |-- __init__.py
|       +-- base.py          # BaseIntegration interface
|
|-- tests/
|   |-- __init__.py
|   |-- test_agent.py        # Agent orchestrator tests
|   |-- test_tools.py        # Tool registry + execution tests
|   +-- test_memory.py       # Memory system tests
|
+-- docs/
    +-- adding_tools.md      # Guide for adding new tools
```

---

## 6. API Endpoints

| Method | Path            | Description                        |
|--------|-----------------|------------------------------------|
| POST   | `/chat`         | Send prompt, get response          |
| POST   | `/chat/stream`  | SSE streaming response             |
| GET    | `/tools`        | List all registered tools          |
| GET    | `/memory/facts` | Read all durable facts             |
| POST   | `/memory/facts` | Write a durable fact               |
| GET    | `/health`       | Health check                       |

---

## 7. Configuration

All config via environment variables (12-factor app):

```env
OPENAI_API_KEY=sk-...           # Required for LLM
OPENAI_MODEL=gpt-4o             # Model to use
MEMORY_STORAGE_PATH=./data      # Where to store SQLite DB
TOOL_TIMEOUT_SECONDS=30         # Max time per tool execution
LOG_LEVEL=INFO                  # Logging verbosity
```

---

## 8. Scaling Path

| Phase    | What changes                                           |
|----------|--------------------------------------------------------|
| **Dev**  | SQLite, single process, local only                     |
| **Beta** | PostgreSQL, Redis for caching, Docker Compose          |
| **Prod** | Kubernetes, async task queue (Celery/ARQ), CDN         |

---

## 9. Security Considerations

- **Prompt injection defense**: Tool inputs validated against JSON Schema; tool descriptions don't leak internal details.
- **Secret management**: All API keys via env vars; never passed through LLM.
- **Rate limiting**: Per-user and per-tool rate limits.
- **Input sanitization**: All user input escaped before storage.
- **Audit logging**: Every tool call logged with timestamp, user, input, output.
