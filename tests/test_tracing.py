import os
from unittest.mock import MagicMock

import pytest
from langsmith import tracing_context

from complianceops.config import DEFAULT_LANGSMITH_PROJECT, Settings, load_settings
from complianceops.domain import AssessmentRequest
from complianceops.service import ComplianceService


def test_tracing_is_off_by_default():
    settings = load_settings()
    assert settings.langsmith_tracing is False
    assert settings.langsmith_project == DEFAULT_LANGSMITH_PROJECT


def test_tracing_without_api_key_is_an_explicit_error(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    with pytest.raises(ValueError, match="LANGSMITH_API_KEY"):
        load_settings()


@pytest.mark.parametrize("flag", ["LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2"])
def test_tracing_enabled_with_key_and_custom_project(monkeypatch, flag):
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv(flag, "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-only")
    monkeypatch.setenv("LANGSMITH_PROJECT", "my-project")
    settings = load_settings()
    assert settings.langsmith_tracing is True
    assert settings.langsmith_project == "my-project"
    assert os.environ["LANGSMITH_PROJECT"] == "my-project"


def run_assessment(tmp_path, **settings):
    service = ComplianceService(Settings(memory_db_path=str(tmp_path / "t.db"), **settings))
    return service.assess(AssessmentRequest(
        audit_id="AUD-trace", request="Assess access evidence", control_ids=["AC-01"],
    ))


def test_assessment_emits_one_root_trace_with_metadata_and_summary_outputs(tmp_path):
    client = MagicMock()
    with tracing_context(enabled=True, client=client):
        run = run_assessment(tmp_path)
    created = {call.kwargs["name"]: call.kwargs for call in client.create_run.call_args_list}
    assert created["compliance_assessment"]["run_type"] == "chain"
    root_update = next(
        call.kwargs for call in client.update_run.call_args_list if call.kwargs.get("tags")
    )
    assert {"compliance-copilot", "monolith", "offline"} <= set(root_update["tags"])
    metadata = root_update["extra"]["metadata"]
    assert metadata["audit_id"] == "AUD-trace" and metadata["prompt_strategy"] == "few_shot"
    assert root_update["outputs"]["run_id"] == run.run_id
    assert root_update["outputs"]["findings"] == {"AC-01": "insufficient_evidence"}


def test_no_trace_is_sent_when_tracing_is_disabled(tmp_path):
    client = MagicMock()
    with tracing_context(enabled=False, client=client):
        run_assessment(tmp_path)
    client.create_run.assert_not_called()
