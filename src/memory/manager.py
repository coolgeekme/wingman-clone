from typing import Optional
from src.memory.conversation import ConversationMemory
from src.memory.durable import DurableMemory

class MemoryManager:
    def __init__(self, storage_path: str = "./data"):
        self.conversation = ConversationMemory()
        self.durable = DurableMemory(storage_path)

    def get_system_context(self) -> str:
        facts = self.durable.get_all()
        if not facts:
            return ""
        lines = ["Known facts about the user:"]
        for key, value in facts.items():
            lines.append(f"  - {key}: {value}")
        return "\n".join(lines)

    def save_message(self, role: str, content: str) -> None:
        self.conversation.add(role, content)

    def get_history(self) -> list[dict]:
        return self.conversation.get_history()

    def save_fact(self, key: str, value: str) -> None:
        self.durable.set(key, value)

    def get_fact(self, key: str) -> Optional[str]:
        return self.durable.get(key)

    def get_all_facts(self) -> dict[str, str]:
        return self.durable.get_all()
