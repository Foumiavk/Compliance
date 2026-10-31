from __future__ import annotations

import json
import os
from dataclasses import dataclass

from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI
from langgraph.errors import GraphRecursionError
from openai import OpenAIError
from pydantic import ValidationError

from .config import Settings
from .domain import AssessmentRequest
from .prompts import compose_prompt
from .tools import ToolSession

MONOLITH_ROLE = """
You own the end-to-end assessment. Read controls and evidence, examine deterministic findings,
consult relevant playbooks, and explain the proposal and draft records. Use available tools
if additional verification is useful. Do not broaden the approved scope."""


class AgentExecutionError(RuntimeError):
    pass


@dataclass
class ExecutionStats:
    token_count: int = 0
    model_calls: int = 0


def invoke_live(
    principal: str,
    prompt: str,
    payload: dict[str, object],
    session: ToolSession,
    settings: Settings,
    stats: ExecutionStats,
    *,
    supervisor: bool = False,
) -> str:
    if not os.getenv("OPENAI_API_KEY"):
        raise AgentExecutionError("Live mode requires OPENAI_API_KEY; use offline mode for the synthetic demo")
    client = ChatOpenAI(
        model=settings.model,
        base_url=settings.api_base,
        timeout=settings.model_timeout_seconds,
        max_retries=1,
        temperature=0,
    )
    agent = create_agent(
        client,
        tools=[] if supervisor else session.build_tools(principal),
        system_prompt=prompt,
    )
    try:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": json.dumps(payload)}]},
            config={
                "recursion_limit": settings.agent_recursion_limit,
                "run_name": principal,
                "tags": ["compliance-copilot", f"prompt:{settings.prompt_strategy}"],
                "metadata": {"principal": principal, "prompt_strategy": settings.prompt_strategy},
            },
        )
    except (OpenAIError, GraphRecursionError, ValidationError, ValueError) as exc:
        raise AgentExecutionError(f"{principal} failed: {exc}") from exc
    final = result["messages"][-1]
    if not isinstance(final, AIMessage) or not final.text.strip():
        raise AgentExecutionError(f"{principal} returned no final answer")
    for message in result["messages"]:
        if isinstance(message, AIMessage):
            stats.model_calls += 1
            stats.token_count += (message.usage_metadata or {}).get("total_tokens", 0)
    return final.text


def collect_evidence(principal: str, body: AssessmentRequest, session: ToolSession) -> None:
    for control_id in body.control_ids:
        for name in ("lookup_control", "list_evidence", "assess_control"):
            session.invoke(principal, name, {"control_id": control_id})


def plan_remediation(principal: str, body: AssessmentRequest, session: ToolSession) -> None:
    for control_id in body.control_ids:
        session.invoke(principal, "search_compliance_playbooks", {"query": control_id})
        if body.propose_remediation and session.catalog.assess(control_id).status != "supported":
            session.invoke(principal, "propose_remediation", {"control_id": control_id})


def draft_summary(principal: str, session: ToolSession) -> None:
    if session.allow_draft:
        session.invoke(principal, "draft_audit_summary", {})


def run_payload(body: AssessmentRequest, memory: dict[str, object], session: ToolSession) -> dict[str, object]:
    return {
        "request": body.model_dump(),
        "untrusted_prior_memory": memory,
        "fixture_as_of": str(session.catalog.as_of),
        "authoritative_findings": [session.catalog.assess(item).model_dump() for item in body.control_ids],
        "tool_records": [item.model_dump() for item in session.trace],
    }


def offline_answer(body: AssessmentRequest, session: ToolSession) -> str:
    lines = ["## Synthetic compliance evidence assessment", f"Fixture reference date: {session.catalog.as_of}."]
    for control_id in body.control_ids:
        finding = session.catalog.assess(control_id)
        lines.extend([
            f"### {control_id} | {finding.policy_id} | {finding.status}",
            finding.rationale,
            f"Accepted evidence: {', '.join(finding.evidence_ids) or 'none'}.",
            f"Excluded evidence: {', '.join(finding.rejected_evidence_ids) or 'none'}.",
            f"Owner: {finding.owner}. Next step: {finding.next_step}",
        ])
    lines.append("## Approvals and publication")
    for proposal in session.proposals.values():
        lines.append(f"{proposal.proposal_id}: awaiting control-owner approval. No action executed.")
    if session.draft:
        lines.append(f"{session.draft.draft_id}: unpublished internal draft; compliance-lead review required.")
    lines.append(
        "No certification or legal conclusion is provided. Synthetic evidence only. "
        "Offline mode uses a fixed workflow and template; it does not interpret the free-text request."
    )
    return "\n\n".join(lines)


def run_monolith(
    body: AssessmentRequest, memory: dict[str, object], session: ToolSession, settings: Settings,
) -> tuple[str, list[str], ExecutionStats]:
    principal = "compliance_monolith"
    collect_evidence(principal, body, session)
    plan_remediation(principal, body, session)
    draft_summary(principal, session)
    stats = ExecutionStats()
    answer = (
        invoke_live(
            principal, compose_prompt(settings.prompt_strategy, MONOLITH_ROLE),
            run_payload(body, memory, session), session, settings, stats,
        )
        if settings.runtime_mode == "live"
        else offline_answer(body, session)
    )
    return answer, [principal], stats
