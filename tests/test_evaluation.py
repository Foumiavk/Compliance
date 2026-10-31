import pytest

from complianceops.config import Settings
from complianceops.domain import AssessmentRequest
from complianceops.evaluation import evaluate, load_cases, score_run
from complianceops.service import ComplianceService


def test_both_architectures_pass_all_offline_cases():
    cases = load_cases()
    report = evaluate(cases)
    assert len(cases) == 12
    assert report["total"] == 24
    assert report["passed"] == 24
    assert report["pass_rate"] == report["required_pass_rate"] == 1.0
    assert all(row["model_calls"] == row["token_count"] == 0 for row in report["results"])


def test_scorer_catches_missing_citations_and_false_execution_claim(tmp_path):
    case = load_cases()[0]
    run = ComplianceService(Settings(memory_db_path=str(tmp_path / "eval.db"))).assess(
        AssessmentRequest(audit_id="AUD-eval", request=case.request, control_ids=case.control_ids)
    )
    run.answer = "We executed the remediation. The report has been published."
    checks = score_run(case, run)
    assert checks["citation_presence"] is False
    assert checks["no_execution_claim_red_flags"] is False


def test_duplicate_eval_cases_are_rejected(tmp_path):
    path = tmp_path / "bad.jsonl"
    line = load_cases()[0].model_dump_json()
    path.write_text(line + "\n" + line)
    with pytest.raises(ValueError, match="unique"):
        load_cases(path)
