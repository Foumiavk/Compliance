from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from dotenv import load_dotenv

from .prompts import DEFAULT_PROMPT_STRATEGY, PROMPT_STRATEGIES, PromptStrategy

Architecture = Literal["monolith", "multi_agent"]
RuntimeMode = Literal["offline", "live"]
DEFAULT_LANGSMITH_PROJECT = "compliance-evidence-copilot"


@dataclass(frozen=True)
class Settings:
    runtime_mode: RuntimeMode = "offline"
    model: str = "gpt-4o-mini"
    api_base: str | None = None
    memory_db_path: str = "data/complianceops.db"
    memory_max_events: int = 20
    default_architecture: Architecture = "monolith"
    model_timeout_seconds: float = 60
    agent_recursion_limit: int = 30
    log_level: str = "INFO"
    prompt_strategy: PromptStrategy = DEFAULT_PROMPT_STRATEGY
    langsmith_tracing: bool = False
    langsmith_project: str = DEFAULT_LANGSMITH_PROJECT

    def __post_init__(self) -> None:
        if self.runtime_mode not in ("offline", "live"):
            raise ValueError("RUNTIME_MODE must be offline or live")
        if self.prompt_strategy not in PROMPT_STRATEGIES:
            raise ValueError(f"PROMPT_STRATEGY must be one of: {', '.join(PROMPT_STRATEGIES)}")
        if self.default_architecture not in ("monolith", "multi_agent"):
            raise ValueError("DEFAULT_ARCHITECTURE must be monolith or multi_agent")
        if self.memory_max_events < 1 or self.model_timeout_seconds <= 0 or self.agent_recursion_limit < 2:
            raise ValueError("Memory, timeout and recursion limits must be positive (recursion >= 2)")


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def load_settings() -> Settings:
    load_dotenv()
    # LANGSMITH_TRACING is the current name; LANGCHAIN_TRACING_V2 is the legacy alias.
    tracing = _env_flag("LANGSMITH_TRACING") or _env_flag("LANGCHAIN_TRACING_V2")
    if tracing and not (os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")):
        raise ValueError("LangSmith tracing requires LANGSMITH_API_KEY; disable LANGSMITH_TRACING or set the key")
    project = os.getenv("LANGSMITH_PROJECT") or os.getenv("LANGCHAIN_PROJECT") or DEFAULT_LANGSMITH_PROJECT
    os.environ.setdefault("LANGSMITH_PROJECT", project)
    mode = os.getenv("RUNTIME_MODE", "offline")
    architecture = os.getenv("DEFAULT_ARCHITECTURE", "monolith")
    if mode not in ("offline", "live"):
        raise ValueError("RUNTIME_MODE must be offline or live")
    if architecture not in ("monolith", "multi_agent"):
        raise ValueError("DEFAULT_ARCHITECTURE must be monolith or multi_agent")
    return Settings(
        runtime_mode=mode,
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        api_base=os.getenv("OPENAI_API_BASE") or None,
        memory_db_path=os.getenv("MEMORY_DB_PATH", "data/complianceops.db"),
        memory_max_events=int(os.getenv("MEMORY_MAX_EVENTS", "20")),
        default_architecture=architecture,
        model_timeout_seconds=float(os.getenv("MODEL_TIMEOUT_SECONDS", "60")),
        agent_recursion_limit=int(os.getenv("AGENT_RECURSION_LIMIT", "30")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        prompt_strategy=os.getenv("PROMPT_STRATEGY", DEFAULT_PROMPT_STRATEGY),
        langsmith_tracing=tracing,
        langsmith_project=project,
    )
