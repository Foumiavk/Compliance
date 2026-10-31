from __future__ import annotations

from .config import Settings
from .domain import AssessmentRequest
from .prompts import compose_prompt
from .runtime import (
    ExecutionStats,
    collect_evidence,
    draft_summary,
    invoke_live,
    offline_answer,
    plan_remediation,
    run_payload,
)
from .tools import ToolSession

SPECIALIST_ROLES = {
    "evidence_agent": "\nEstablish scope, ownership, freshness and evidence sufficiency. Report facts and unknowns.",
    "remediation_agent": "\nConsult playbooks and plan evidence collection or remediation. Never execute changes.",
    "reporting_agent": "\nPrepare an internal summary with evidence IDs and approvals. Never publish or attest.",
}
SUPERVISOR_ROLE = """
Synthesize the specialist reports against the raw tool records and deterministic findings.
If a report conflicts with a system-of-record finding, retain the finding and flag the conflict.
You have no tools or approval authority."""


def route_request(body: AssessmentRequest) -> list[str]:
    routes = ["evidence_agent"]
    if body.propose_remediation:
        routes.append("remediation_agent")
    if body.draft_summary:
        routes.append("reporting_agent")
    return routes


def run_multi_agent(
    body: AssessmentRequest, memory: dict[str, object], session: ToolSession, settings: Settings,
) -> tuple[str, list[str], ExecutionStats]:
    routes = route_request(body)
    reports: list[dict[str, str]] = []
    stats = ExecutionStats()
    for principal in routes:
        if principal == "evidence_agent":
            collect_evidence(principal, body, session)
        elif principal == "remediation_agent":
            plan_remediation(principal, body, session)
        else:
            draft_summary(principal, session)
        if settings.runtime_mode == "live":
            payload = run_payload(body, memory, session)
            payload["prior_specialist_reports"] = list(reports)
            report = invoke_live(
                principal, compose_prompt(settings.prompt_strategy, SPECIALIST_ROLES[principal], final_answer=False),
                payload, session, settings, stats,
            )
            reports.append({"agent": principal, "report": report})
    if settings.runtime_mode == "live":
        payload = run_payload(body, memory, session)
        payload["specialist_reports"] = reports
        answer = invoke_live(
            "supervisor", compose_prompt(settings.prompt_strategy, SUPERVISOR_ROLE),
            payload, session, settings, stats, supervisor=True,
        )
    else:
        answer = offline_answer(body, session)
    return answer, routes + ["supervisor"], stats
