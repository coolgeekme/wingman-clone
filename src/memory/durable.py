import json
from pathlib import Path
from typing import Optional

class DurableMemory:
    def __init__(self, storage_path: str = "./data"):
        self._storage_dir = Path(storage_path)
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._file = self._storage_dir / "durable_facts.json"
        self._facts: dict[str, str] = self._load()

    def _load(self) -> dict[str, str]:
        if self._file.exists():
            with open(self._file, "r") as f:
                return json.load(f)
        return {}

    def _save(self) -> None:
        with open(self._file, "w") as f:
            json.dump(self._facts, f, indent=2)

    def set(self, key: str, value: str) -> None:
        self._facts[key] = value
        self._save()

    def get(self, key: str) -> Optional[str]:
        return self._facts.get(key)

    def get_all(self) -> dict[str, str]:
        return dict(self._facts)

    def delete(self, key: str) -> bool:
        if key in self._facts:
            del self._facts[key]
            self._save()
            return True
        return False
