"""Phase 3: compare prompt strategies on the same cases with the same automated checks."""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from .config import Architecture, RuntimeMode, Settings, load_settings
from .evaluation import EvalCase, evaluate, load_cases
from .prompts import PROMPT_STRATEGIES

REQUIRED_SECTIONS = (
    "## Observations", "## Gaps and unknowns", "## Recommendations", "## Approvals", "## Limitations",
)


def summarize(report: dict[str, object]) -> dict[str, object]:
    rows = report["results"]  # type: ignore[index]
    total = len(rows)
    check_names = sorted({name for row in rows for name in row["checks"]})
    return {
        "runs": total,
        "pass_rate": report["pass_rate"],
        "check_pass_rates": {
            name: sum(row["checks"][name] for row in rows) / total for name in check_names
        },
        "section_format_rate": sum(
            all(section in row["run"]["answer"] for section in REQUIRED_SECTIONS) for row in rows
        ) / total,
        "avg_latency_seconds": round(sum(row["latency_seconds"] for row in rows) / total, 3),
        "total_tokens": sum(row["token_count"] for row in rows),
        "total_model_calls": sum(row["model_calls"] for row in rows),
    }


def compare(
    cases: list[EvalCase],
    strategies: tuple[str, ...] = PROMPT_STRATEGIES,
    mode: RuntimeMode = "live",
    architectures: tuple[Architecture, ...] = ("monolith", "multi_agent"),
    settings: Settings | None = None,
) -> dict[str, object]:
    base = settings or Settings()
    reports = {
        strategy: evaluate(cases, mode, architectures, replace(base, prompt_strategy=strategy))
        for strategy in strategies
    }
    return {
        "runtime_mode": mode,
        "summaries": {strategy: summarize(report) for strategy, report in reports.items()},
        "answers": {
            strategy: {
                f"{row['case_id']}/{row['architecture']}": row["run"]["answer"] for row in report["results"]
            }
            for strategy, report in reports.items()
        },
    }


def render_markdown(result: dict[str, object]) -> str:
    summaries: dict[str, dict[str, object]] = result["summaries"]  # type: ignore[assignment]
    lines = [
        f"# Prompt strategy comparison ({result['runtime_mode']} mode)",
        "",
        "| Strategy | Runs | All-checks pass | Citation presence | Section format | Avg latency (s) | Tokens | Model calls |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for strategy, item in summaries.items():
        rates = item["check_pass_rates"]
        lines.append(
            f"| {strategy} | {item['runs']} | {item['pass_rate']:.0%} | {rates['citation_presence']:.0%} "
            f"| {item['section_format_rate']:.0%} | {item['avg_latency_seconds']} "
            f"| {item['total_tokens']} | {item['total_model_calls']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare prompt strategies with the evaluation checks")
    parser.add_argument("--mode", choices=("offline", "live"), default="live")
    parser.add_argument("--strategies", nargs="+", choices=PROMPT_STRATEGIES, default=list(PROMPT_STRATEGIES))
    parser.add_argument("--architecture", choices=("both", "monolith", "multi_agent"), default="both")
    parser.add_argument("--cases", type=Path, help="Optional replacement JSONL dataset")
    parser.add_argument("--output", type=Path, help="Write full JSON, including every answer, here")
    parser.add_argument("--report", type=Path, help="Write the Markdown summary table here")
    args = parser.parse_args()
    architectures: tuple[Architecture, ...] = (
        ("monolith", "multi_agent") if args.architecture == "both" else (args.architecture,)
    )
    result = compare(load_cases(args.cases), tuple(args.strategies), args.mode, architectures, load_settings())
    markdown = render_markdown(result)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(markdown)
    print(markdown)


if __name__ == "__main__":
    main()
