import pytest


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    """Keep a developer's real .env and LangSmith settings out of the test run."""
    from complianceops import config

    monkeypatch.setattr(config, "load_dotenv", lambda *args, **kwargs: False)
    for name in (
        "LANGSMITH_TRACING", "LANGSMITH_API_KEY", "LANGSMITH_PROJECT", "LANGSMITH_ENDPOINT",
        "LANGCHAIN_TRACING_V2", "LANGCHAIN_API_KEY", "LANGCHAIN_PROJECT", "PROMPT_STRATEGY",
        "RUNTIME_MODE", "DEFAULT_ARCHITECTURE",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
