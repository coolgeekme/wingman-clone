from dataclasses import dataclass

@dataclass
class Message:
    role: str
    content: str

class ConversationMemory:
    def __init__(self, max_messages: int = 50):
        self._messages: list[Message] = []
        self._max_messages = max_messages

    def add(self, role: str, content: str) -> None:
        self._messages.append(Message(role=role, content=content))
        if len(self._messages) > self._max_messages:
            self._messages = self._messages[-self._max_messages:]

    def get_history(self) -> list[dict]:
        return [{"role": m.role, "content": m.content} for m in self._messages]

    def clear(self) -> None:
        self._messages.clear()

    def __len__(self) -> int:
        return len(self._messages)
