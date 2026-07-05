import asyncio
import os
from dotenv import load_dotenv

# Load env vars
load_dotenv()

from src.agent.orchestrator import AgentOrchestrator
from src.tools.registry import ToolRegistry
from src.memory.manager import MemoryManager

async def test_gemma():
    registry = ToolRegistry()
    # No need to register tools for a simple chat test
    memory = MemoryManager()
    
    agent = AgentOrchestrator(registry, memory)
    
    print("Testing connection to Gemma on VPS...")
    try:
        response = await agent.process("Hello Gemma! Who are you?")
        print("\n--- Response from Gemma ---")
        print(response.content)
        print("---------------------------\n")
    except Exception as e:
        print(f"Error connecting to Gemma: {e}")

if __name__ == "__main__":
    asyncio.run(test_gemma())
