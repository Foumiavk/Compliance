from complianceops import runtime
from complianceops.evaluation import load_cases
from complianceops.prompt_compare import REQUIRED_SECTIONS, compare, render_markdown, summarize
from complianceops.prompts import PROMPT_STRATEGIES


def test_compare_runs_every_strategy_with_the_same_checks_and_cases():
    cases = load_cases()[:2]
    result = compare(cases, PROMPT_STRATEGIES, mode="offline")
    assert list(result["summaries"]) == list(PROMPT_STRATEGIES)
    for summary in result["summaries"].values():
        assert summary["runs"] == 4
        assert summary["pass_rate"] == 1.0
        assert summary["check_pass_rates"]["citation_presence"] == 1.0
    assert all(len(answers) == 4 for answers in result["answers"].values())


def test_section_format_rate_detects_missing_headings():
    good = {"answer": "\n".join(REQUIRED_SECTIONS)}
    bad = {"answer": "## Observations only"}
    report = {"pass_rate": 1.0, "results": [
        {"checks": {"a": True}, "run": good, "latency_seconds": 1, "token_count": 5, "model_calls": 1},
        {"checks": {"a": True}, "run": bad, "latency_seconds": 3, "token_count": 5, "model_calls": 1},
    ]}
    summary = summarize(report)
    assert summary["section_format_rate"] == 0.5
    assert summary["avg_latency_seconds"] == 2 and summary["total_tokens"] == 10


def test_markdown_report_lists_each_strategy():
    result = compare(load_cases()[:1], ("minimal", "structured"), mode="offline")
    table = render_markdown(result)
    assert "| minimal |" in table and "| structured |" in table


def test_each_strategy_reaches_the_live_prompt(monkeypatch):
    prompts: dict[str, set[str]] = {}

    def fake_live(principal, prompt, payload, session, settings, stats, *, supervisor=False):
        prompts.setdefault(settings.prompt_strategy, set()).add(prompt)
        stats.model_calls += 1
        return "stub answer"

    monkeypatch.setattr(runtime, "invoke_live", fake_live)
    result = compare(load_cases()[:1], ("minimal", "few_shot"), mode="live", architectures=("monolith",))
    assert set(prompts) == {"minimal", "few_shot"}
    assert prompts["minimal"] != prompts["few_shot"]
    assert result["summaries"]["minimal"]["total_model_calls"] == 1
    assert result["summaries"]["minimal"]["section_format_rate"] == 0
