import logging

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.agent.orchestrator import AgentOrchestrator
from src.config import settings
from src.memory.manager import MemoryManager
from src.tools.registry import registry

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

registry.auto_discover()
memory = MemoryManager(storage_path=settings.memory_storage_path)
agent = AgentOrchestrator(tool_registry=registry, memory=memory)

app = FastAPI(title="Wingman Clone", version="0.2.0")


class ChatRequest(BaseModel):
    prompt: str

class ChatResponse(BaseModel):
    response: str
    tool_calls: list[dict] = []

class FactRequest(BaseModel):
    key: str
    value: str


@app.get("/health")
async def health():
    return {"status": "ok", "tools_loaded": len(registry.list_tools()), "llm_provider": settings.llm_provider, "model": settings.get_active_model()}

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")
    result = await agent.process(req.prompt)
    return ChatResponse(response=result.content, tool_calls=result.tool_calls)

@app.get("/tools")
async def list_tools():
    return {"tools": registry.list_tools()}

@app.get("/memory/facts")
async def get_facts():
    return {"facts": memory.get_all_facts()}

@app.post("/memory/facts")
async def save_fact(req: FactRequest):
    memory.save_fact(req.key, req.value)
    return {"status": "saved", "key": req.key}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=settings.port, reload=False)
