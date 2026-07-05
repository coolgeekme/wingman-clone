import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Settings:
    # LLM Provider: "openai", "anthropic", or "groq"
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "openai"))

    # OpenAI settings
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_base_url: str = field(default_factory=lambda: os.getenv("OPENAI_BASE_URL", ""))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o"))

    # Anthropic settings
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    anthropic_model: str = field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"))

    # Groq settings
    groq_api_key: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    groq_model: str = field(default_factory=lambda: os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"))

    # Composio settings
    composio_api_key: str = field(default_factory=lambda: os.getenv("COMPOSIO_API_KEY", ""))

    # General settings
    memory_storage_path: str = field(default_factory=lambda: os.getenv("MEMORY_STORAGE_PATH", "./data"))
    tool_timeout_seconds: int = field(default_factory=lambda: int(os.getenv("TOOL_TIMEOUT_SECONDS", "30")))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))

    def get_active_api_key(self) -> str:
        key_map = {
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
            "groq": self.groq_api_key,
        }
        return key_map.get(self.llm_provider, "")

    def get_active_model(self) -> str:
        model_map = {
            "openai": self.openai_model,
            "anthropic": self.anthropic_model,
            "groq": self.groq_model,
        }
        return model_map.get(self.llm_provider, self.openai_model)


settings = Settings()
