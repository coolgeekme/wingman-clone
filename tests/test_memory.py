import os
import tempfile
import pytest
from src.memory.conversation import ConversationMemory
from src.memory.durable import DurableMemory
from src.memory.manager import MemoryManager


class TestConversationMemory:
    def test_add_and_get(self):
        mem = ConversationMemory()
        mem.add("user", "Hello")
        mem.add("assistant", "Hi there!")
        history = mem.get_history()
        assert len(history) == 2
        assert history[0] == {"role": "user", "content": "Hello"}
        assert history[1] == {"role": "assistant", "content": "Hi there!"}

    def test_max_messages(self):
        mem = ConversationMemory(max_messages=3)
        for i in range(5):
            mem.add("user", f"msg {i}")
        assert len(mem) == 3
        history = mem.get_history()
        assert history[0]["content"] == "msg 2"

    def test_clear(self):
        mem = ConversationMemory()
        mem.add("user", "Hello")
        mem.clear()
        assert len(mem) == 0
        assert mem.get_history() == []


class TestDurableMemory:
    @pytest.fixture
    def storage(self, tmp_path):
        return DurableMemory(storage_path=str(tmp_path))

    def test_set_and_get(self, storage):
        storage.set("user_name", "Marcus")
        assert storage.get("user_name") == "Marcus"

    def test_get_missing(self, storage):
        assert storage.get("nonexistent") is None

    def test_get_all(self, storage):
        storage.set("name", "Marcus")
        storage.set("tz", "MST")
        facts = storage.get_all()
        assert facts == {"name": "Marcus", "tz": "MST"}

    def test_delete(self, storage):
        storage.set("key", "value")
        assert storage.delete("key") is True
        assert storage.get("key") is None

    def test_delete_missing(self, storage):
        assert storage.delete("nonexistent") is False

    def test_persistence(self, tmp_path):
        mem1 = DurableMemory(storage_path=str(tmp_path))
        mem1.set("user_name", "Marcus")
        mem2 = DurableMemory(storage_path=str(tmp_path))
        assert mem2.get("user_name") == "Marcus"

    def test_clear(self, storage):
        storage.set("a", "1")
        storage.set("b", "2")
        storage.clear()
        assert storage.get_all() == {}


class TestMemoryManager:
    @pytest.fixture
    def manager(self, tmp_path):
        return MemoryManager(storage_path=str(tmp_path))

    def test_save_and_get_message(self, manager):
        manager.save_message("user", "Hello")
        history = manager.get_history()
        assert len(history) == 1

    def test_save_and_get_fact(self, manager):
        manager.save_fact("timezone", "America/Phoenix")
        assert manager.get_fact("timezone") == "America/Phoenix"

    def test_system_context_empty(self, manager):
        assert manager.get_system_context() == ""

    def test_system_context_with_facts(self, manager):
        manager.save_fact("user_name", "Marcus")
        manager.save_fact("timezone", "MST")
        ctx = manager.get_system_context()
        assert "user_name" in ctx
        assert "Marcus" in ctx
        assert "timezone" in ctx
        assert "MST" in ctx

    def test_get_all_facts(self, manager):
        manager.save_fact("a", "1")
        manager.save_fact("b", "2")
        facts = manager.get_all_facts()
        assert facts == {"a": "1", "b": "2"}
