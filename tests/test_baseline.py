import pytest

from complianceops.baseline import FALLBACK, SAMPLE_INTERACTIONS, BaselineAgent, render_interaction_log


@pytest.fixture(scope="module")
def agent():
    return BaselineAgent()


@pytest.mark.parametrize("question,controls,intent", [
    ("What is the status of the access review?", ["AC-01"], "status"),
    ("What should we do next about the backup restoration test?", ["BC-01"], "next_steps"),
    ("What evidence do we have for the vendor review?", ["VR-01"], "evidence"),
    ("Status of VR-01 and BC-01", ["BC-01", "VR-01"], "status"),
])
def test_baseline_handles_keyword_questions_with_catalog_facts(agent, question, controls, intent):
    result = agent.answer(question)
    assert result.control_ids == controls
    assert result.intent == intent
    for control_id in controls:
        finding = agent.catalog.assess(control_id)
        assert f"{control_id} ({finding.policy_id})" in result.answer
        assert finding.status in result.answer


def test_baseline_limitation_vocabulary_miss_falls_back(agent):
    result = agent.answer("Are our subcontractors' security attestations up to date?")
    assert result.control_ids == [] and result.answer == FALLBACK


def test_baseline_limitation_ignores_negation(agent):
    result = agent.answer("Tell me about backups, but leave out the vendor review.")
    assert result.control_ids == ["BC-01", "VR-01"]


def test_baseline_limitation_cannot_prioritize(agent):
    assert agent.answer("Which control should we fix first, and why?").answer == FALLBACK


def test_interaction_log_covers_every_sample_with_real_output(agent):
    log = render_interaction_log(agent)
    assert log.count("## Interaction") == len(SAMPLE_INTERACTIONS) >= 5
    assert log.count("LIMITATION") >= 2
    assert agent.answer(SAMPLE_INTERACTIONS[0][0]).answer in log
