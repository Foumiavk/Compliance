import pytest

from complianceops import multi_agent, runtime
from complianceops.config import Settings, load_settings
from complianceops.domain import AssessmentRequest
from complianceops.knowledge import Catalog
from complianceops.prompts import (
    DEFAULT_PROMPT_STRATEGY,
    OUTPUT_FORMAT,
    PROMPT_STRATEGIES,
    SAFETY_PROMPT,
    WORKED_EXAMPLE,
    compose_prompt,
)
from complianceops.tools import ToolSession

ROLE = "\nRole text."


def test_strategy_prompts_differ_in_the_intended_way():
    minimal = compose_prompt("minimal", ROLE)
    guardrailed = compose_prompt("guardrailed", ROLE)
    structured = compose_prompt("structured", ROLE)
    few_shot = compose_prompt("few_shot", ROLE)
    assert SAFETY_PROMPT not in minimal and ROLE not in minimal
    assert guardrailed == SAFETY_PROMPT + ROLE
    assert structured == guardrailed + OUTPUT_FORMAT
    assert few_shot == structured + WORKED_EXAMPLE


def test_intermediate_reports_never_get_the_final_answer_contract():
    for strategy in ("guardrailed", "structured", "few_shot"):
        assert compose_prompt(strategy, ROLE, final_answer=False) == SAFETY_PROMPT + ROLE


def test_unknown_strategy_is_rejected():
    with pytest.raises(ValueError, match="PROMPT_STRATEGY"):
        compose_prompt("creative", ROLE)
    with pytest.raises(ValueError, match="PROMPT_STRATEGY"):
        Settings(prompt_strategy="creative")


def test_default_strategy_is_valid_and_loaded_from_environment(monkeypatch):
    assert DEFAULT_PROMPT_STRATEGY in PROMPT_STRATEGIES
    assert load_settings().prompt_strategy == DEFAULT_PROMPT_STRATEGY
    monkeypatch.setenv("PROMPT_STRATEGY", "few_shot")
    assert load_settings().prompt_strategy == "few_shot"
    monkeypatch.setenv("PROMPT_STRATEGY", "bogus")
    with pytest.raises(ValueError, match="PROMPT_STRATEGY"):
        load_settings()


@pytest.mark.parametrize("architecture", ["monolith", "multi_agent"])
def test_live_runs_use_the_configured_strategy_for_final_answers(monkeypatch, tmp_path, architecture):
    seen: dict[str, str] = {}

    def fake_live(principal, prompt, payload, session, settings, stats, *, supervisor=False):
        seen[principal] = prompt
        return "ok"

    monkeypatch.setattr(runtime, "invoke_live", fake_live)
    monkeypatch.setattr(multi_agent, "invoke_live", fake_live)
    body = AssessmentRequest(audit_id="AUD-p", request="Assess it", control_ids=["AC-01"])
    session = ToolSession(Catalog(), body.control_ids, True, True)
    settings = Settings(runtime_mode="live", prompt_strategy="few_shot", memory_db_path=str(tmp_path / "p.db"))
    runner = runtime.run_monolith if architecture == "monolith" else multi_agent.run_multi_agent
    runner(body, {}, session, settings)
    final = "compliance_monolith" if architecture == "monolith" else "supervisor"
    assert WORKED_EXAMPLE in seen[final]
    for principal, prompt in seen.items():
        if principal != final:
            assert OUTPUT_FORMAT not in prompt
