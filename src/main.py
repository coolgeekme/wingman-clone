import logging
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.agent.orchestrator import AgentOrchestrator
from src.config import settings
from src.memory.manager import MemoryManager
from src.tools.registry import registry

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

# --- Bootstrap ---
registry.auto_discover()
memory = MemoryManager(storage_path=settings.memory_storage_path)
agent = AgentOrchestrator(tool_registry=registry, memory=memory)

app = FastAPI(title="Wingman Clone", version="0.4.0")

# --- CORS Configuration ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Request / Response models ---
class ChatRequest(BaseModel):
    prompt: Optional[str] = None
    message: Optional[str] = None
    session_id: Optional[str] = None
    history: Optional[list[dict]] = Field(default_factory=list)

    @property
    def query(self) -> str:
        return self.message or self.prompt or ""


class ChatResponse(BaseModel):
    response: str
    session_id: str = ""
    tool_calls: list[dict] = []


class FactRequest(BaseModel):
    key: str
    value: str


class SessionCreate(BaseModel):
    title: Optional[str] = ""


# --- Endpoints ---
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "0.4.0",
        "tools_loaded": len(registry.list_tools()),
        "llm_provider": settings.llm_provider,
        "model": settings.get_active_model(),
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    query = req.query
    if not query.strip():
        raise HTTPException(status_code=400, detail="Prompt or message cannot be empty")
    
    # Use provided session_id or create a new session
    session_id = req.session_id
    if not session_id:
        session_id = memory.create_session(title=query[:80])

    try:
        result = await agent.process(query, history=req.history, session_id=session_id)
        return ChatResponse(response=result.content, session_id=session_id, tool_calls=result.tool_calls)
    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# --- Session endpoints ---
@app.get("/sessions")
async def list_sessions():
    """List all chat sessions, most recent first."""
    sessions = memory.list_sessions()
    return sessions


@app.post("/sessions")
async def create_session(req: SessionCreate):
    """Create a new chat session."""
    session_id = memory.create_session(title=req.title or "")
    return {"session_id": session_id, "title": req.title or ""}


@app.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session details."""
    session = memory.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and all its messages."""
    deleted = memory.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted", "session_id": session_id}


@app.get("/history")
async def get_history(session_id: Optional[str] = None, limit: Optional[int] = Query(default=50, le=200)):
    """Get conversation history for a session."""
    messages = memory.get_history(session_id=session_id, limit=limit)
    return {"session_id": session_id, "messages": messages, "count": len(messages)}


@app.get("/history/{session_id}")
async def get_session_history(session_id: str, limit: Optional[int] = Query(default=50, le=200)):
    """Get conversation history for a specific session."""
    session = memory.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = memory.get_history(session_id=session_id, limit=limit)
    return {"session_id": session_id, "messages": messages, "count": len(messages)}


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


# --- Integrations Management ---

@app.get("/integrations/connect/{app_name}")
async def get_connection_url(app_name: str, redirect_url: Optional[str] = None):
    """Initiate OAuth connection for a given app using Composio SDK v0.17+."""
    if not settings.composio_api_key:
        raise HTTPException(status_code=500, detail="COMPOSIO_API_KEY not configured")
    
    try:
        from composio import Composio
        from composio_langchain import LangchainProvider
        
        client = Composio(provider=LangchainProvider(), api_key=settings.composio_api_key)
        
        # Find the auth config for the requested app
        auth_configs = client.auth_configs.list()
        app_slug = app_name.lower()
        auth_config_id = None
        
        for item in auth_configs.items:
            if hasattr(item, 'toolkit') and item.toolkit.slug == app_slug and item.status == 'ENABLED':
                auth_config_id = item.id
                break
        
        if not auth_config_id:
            raise HTTPException(
                status_code=404,
                detail=f"No auth config found for app '{app_name}'. Create one in the Composio dashboard first."
            )
        
        # Initiate the connection
        connection = client.connected_accounts.initiate(
            user_id="default",
            auth_config_id=auth_config_id,
            callback_url=redirect_url,
            allow_multiple=True,
        )
        
        return {
            "app_name": app_name,
            "redirect_url": connection.redirect_url,
            "connection_id": connection.id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to initiate connection for {app_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/integrations/list")
async def list_integrations():
    """List available app integrations."""
    if not settings.composio_api_key:
        return {"integrations": []}
    
    try:
        from composio import Composio
        from composio_langchain import LangchainProvider
        
        client = Composio(provider=LangchainProvider(), api_key=settings.composio_api_key)
        auth_configs = client.auth_configs.list()
        
        apps = list(set(
            item.toolkit.slug
            for item in auth_configs.items
            if hasattr(item, 'toolkit') and item.status == 'ENABLED'
        ))
        return {"integrations": sorted(apps)}
    except Exception as e:
        logger.error(f"Failed to list integrations: {e}")
        return {"integrations": ["gmail", "googlecalendar", "github", "slack", "notion", "discord", "linkedin"]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=settings.port, reload=False)
