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

app = FastAPI(title="Wingman Clone", version="0.3.0")

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
    history: Optional[list[dict]] = Field(default_factory=list)

    @property
    def query(self) -> str:
        return self.message or self.prompt or ""


class ChatResponse(BaseModel):
    response: str
    tool_calls: list[dict] = []


class FactRequest(BaseModel):
    key: str
    value: str


# --- Endpoints ---
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "tools_loaded": len(registry.list_tools()),
        "llm_provider": settings.llm_provider,
        "model": settings.get_active_model(),
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    query = req.query
    if not query.strip():
        raise HTTPException(status_code=400, detail="Prompt or message cannot be empty")
    
    try:
        result = await agent.process(query, history=req.history)
        return ChatResponse(response=result.content, tool_calls=result.tool_calls)
    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


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
    """Initiate an OAuth connection for a given app (e.g. gmail, github).
    
    Uses composio SDK v0.17+ with Composio client to:
    1. Look up the auth config for the toolkit
    2. Create a connected account with the redirect URI
    3. Return the OAuth redirect URL to the caller
    """
    if not settings.composio_api_key:
        raise HTTPException(status_code=500, detail="COMPOSIO_API_KEY not configured")
    
    try:
        from composio import Composio

        sdk = Composio(api_key=settings.composio_api_key)

        # Find the auth config for this toolkit
        auth_configs = sdk.client.auth_configs.list(toolkit_slug=app_name.lower())
        if not auth_configs.items:
            raise HTTPException(
                status_code=404,
                detail=f"No auth configuration found for app '{app_name}'"
            )

        # Use the first available auth config
        auth_config_id = auth_configs.items[0].id

        # Build the connection params
        connection_params = {}
        if redirect_url:
            connection_params["redirect_uri"] = redirect_url

        # Initiate the connection
        result = sdk.client.connected_accounts.create(
            auth_config={"id": auth_config_id},
            connection=connection_params
        )

        return {
            "app_name": app_name,
            "redirect_url": result.redirect_url,
            "connection_id": result.id,
            "status": result.status
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to initiate connection for {app_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/integrations/list")
async def list_integrations():
    """List available integration toolkits."""
    if not settings.composio_api_key:
        return {"integrations": []}
    
    try:
        from composio import Composio

        sdk = Composio(api_key=settings.composio_api_key)
        # Return a curated list of apps we support in the UI
        apps = ["gmail", "googlecalendar", "github", "slack", "notion", "discord", "linkedin"]
        return {"integrations": apps}
    except Exception as e:
        logger.error(f"Failed to list integrations: {e}")
        return {"integrations": []}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=settings.port, reload=False)
