"""Opt-in retrieval for the existing basic agent; no credentials in YAML."""

from typing import Literal
from pydantic import BaseModel, Field, model_validator


class RAGConfig(BaseModel):
    enabled: bool = False
    backend: Literal["lexical", "mem0"] = "lexical"
    directory: str = "chat_history/rag"
    top_k: int = Field(5, ge=1, le=20)
    max_context_chars: int = Field(4000, ge=128, le=24000)
    recent_messages: int = Field(20, ge=2, le=200)
    recent_chars: int = Field(12000, ge=128, le=100000)
    timeout_seconds: float = Field(2.0, gt=0, le=30)
    mem0_settings_file: str | None = None
    api_key_env: str = "GEMINI_API_KEY"

    @model_validator(mode="after")
    def require_mem0_settings(self):
        if self.enabled and self.backend == "mem0" and not self.mem0_settings_file:
            raise ValueError("mem0 backend requires mem0_settings_file")
        return self
