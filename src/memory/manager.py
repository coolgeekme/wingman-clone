from typing import Optional
from src.memory.conversation import ConversationMemory
from src.memory.durable import DurableMemory


class MemoryManager:
    def __init__(self, storage_path: str = "./data"):
        self.conversation = ConversationMemory(db_path=f"{storage_path}/conversations.db")
        self.durable = DurableMemory(storage_path)

    # --- Session management ---
    def create_session(self, title: str = "") -> str:
        return self.conversation.create_session(title=title)

    def list_sessions(self) -> list[dict]:
        return self.conversation.list_sessions()

    def get_session(self, session_id: str) -> Optional[dict]:
        return self.conversation.get_session(session_id)

    def delete_session(self, session_id: str) -> bool:
        return self.conversation.delete_session(session_id)

    # --- Message handling ---
    def get_system_context(self) -> str:
        facts = self.durable.get_all()
        if not facts:
            return ""
        lines = ["Known facts about the user:"]
        for key, value in facts.items():
            lines.append(f"  - {key}: {value}")
        return "\n".join(lines)

    def save_message(self, role: str, content: str, session_id: Optional[str] = None) -> str:
        return self.conversation.add(role, content, session_id=session_id)

    def get_history(self, session_id: Optional[str] = None, limit: Optional[int] = None) -> list[dict]:
        return self.conversation.get_history(session_id=session_id, limit=limit)

    def save_fact(self, key: str, value: str) -> None:
        self.durable.set(key, value)

    def get_fact(self, key: str) -> Optional[str]:
        return self.durable.get(key)

    def get_all_facts(self) -> dict[str, str]:
        return self.durable.get_all()
