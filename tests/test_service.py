import pytest

from complianceops.config import Settings
from complianceops.domain import AssessmentRequest
from complianceops.memory import AuditMemoryStore
from complianceops.runtime import AgentExecutionError
from complianceops.service import ComplianceService


@pytest.fixture
def service(tmp_path):
    return ComplianceService(Settings(memory_db_path=str(tmp_path / "memory.db")))


def request(**kwargs):
    return AssessmentRequest.model_validate({
        "audit_id": "AUD-demo",
        "request": "Assess evidence and draft next steps.",
        "control_ids": ["AC-01", "BC-01", "VR-01"],
        **kwargs,
    })


@pytest.mark.parametrize("architecture", ["monolith", "multi_agent"])
def test_end_to_end_offline_and_persistence(service, architecture):
    run = service.assess(request(architecture=architecture))
    assert run.runtime_mode == "offline"
    assert run.token_count == run.model_calls == 0
    assert run.latency_seconds > 0
    assert {item.control_id for item in run.proposals} == {"AC-01", "VR-01"}
    assert run.draft.published is False
    persisted = AuditMemoryStore(service.settings.memory_db_path).get_run(run.audit_id, run.run_id)
    assert persisted == run
    assert len(service.memory.inspect(run.audit_id)["timeline"]) == 2


def test_audit_memory_and_run_lookup_are_isolated(service):
    run = service.assess(request(audit_id="AUD-first"))
    assert service.memory.inspect("AUD-second")["timeline"] == []
    assert service.memory.get_run("AUD-second", run.run_id) is None
    service.assess(request(audit_id="AUD-second"))
    service.memory.clear("AUD-first")
    assert service.memory.get_run("AUD-first", run.run_id) is None
    assert service.memory.inspect("AUD-second")["run_count"] == 1


def test_prompt_history_is_bounded_but_runs_are_durable(tmp_path):
    store = AuditMemoryStore(tmp_path / "bounded.db", max_events=2)
    for i in range(5):
        store.add_event("AUD-demo", "user", str(i))
    assert [item["content"] for item in store.inspect("AUD-demo")["timeline"]] == ["3", "4"]


def test_default_architecture_is_used(tmp_path):
    service = ComplianceService(Settings(
        memory_db_path=str(tmp_path / "default.db"), default_architecture="multi_agent",
    ))
    assert service.assess(request()).architecture == "multi_agent"


def test_failed_live_run_is_not_saved(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    service = ComplianceService(Settings(runtime_mode="live", memory_db_path=str(tmp_path / "live.db")))
    with pytest.raises(AgentExecutionError, match="OPENAI_API_KEY"):
        service.assess(request())
    snapshot = service.memory.inspect("AUD-demo")
    assert snapshot["run_count"] == 0
    assert snapshot["timeline"][-1]["actor"] == "error"


@pytest.mark.parametrize("architecture", ["monolith", "multi_agent"])
def test_live_orchestration_passes_raw_records_and_scoped_tools(tmp_path, monkeypatch, architecture):
    from complianceops import multi_agent, runtime

    calls = []

    def fake_live(principal, prompt, payload, session, settings, stats, *, supervisor=False):
        assert payload["authoritative_findings"]
        assert payload["tool_records"]
        assert "untrusted_prior_memory" in payload
        if supervisor:
            assert principal == "supervisor"
            assert len(payload["specialist_reports"]) == 3
        else:
            assert session.build_tools(principal)
        calls.append(principal)
        stats.model_calls += 1
        stats.token_count += 10
        return runtime.offline_answer(request(), session)

    monkeypatch.setattr(runtime, "invoke_live", fake_live)
    monkeypatch.setattr(multi_agent, "invoke_live", fake_live)
    service = ComplianceService(Settings(runtime_mode="live", memory_db_path=str(tmp_path / "live.db")))
    run = service.assess(request(architecture=architecture))
    assert calls == run.route
    assert run.model_calls == (1 if architecture == "monolith" else 4)
    assert run.token_count == 10 * len(calls)
