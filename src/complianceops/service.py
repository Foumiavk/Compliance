from __future__ import annotations

import logging
import time
import uuid

from langsmith import traceable
from langsmith.run_helpers import get_current_run_tree

from .config import Settings
from .domain import AssessmentRequest, AssessmentResponse
from .knowledge import Catalog
from .memory import AuditMemoryStore
from .multi_agent import run_multi_agent
from .runtime import AgentExecutionError, run_monolith
from .tools import ToolSession

logger = logging.getLogger(__name__)


def _trace_inputs(inputs: dict[str, object]) -> dict[str, object]:
    body = inputs["body"]
    return {"assessment_request": body.model_dump() if isinstance(body, AssessmentRequest) else str(body)}


def _trace_outputs(output: object) -> dict[str, object]:
    if not isinstance(output, AssessmentResponse):
        return {"output": str(output)}
    return {
        "run_id": output.run_id,
        "architecture": output.architecture,
        "answer": output.answer,
        "findings": {item.control_id: item.status for item in output.findings},
        "proposal_ids": [item.proposal_id for item in output.proposals],
        "tool_calls": output.tool_calls,
        "model_calls": output.model_calls,
        "token_count": output.token_count,
    }


class ComplianceService:
    def __init__(
        self,
        settings: Settings,
        memory: AuditMemoryStore | None = None,
        catalog: Catalog | None = None,
    ) -> None:
        self.settings = settings
        self.memory = memory if memory is not None else AuditMemoryStore(
            settings.memory_db_path, settings.memory_max_events,
        )
        self.catalog = catalog if catalog is not None else Catalog()

    @traceable(
        name="compliance_assessment", run_type="chain",
        process_inputs=_trace_inputs, process_outputs=_trace_outputs,
    )
    def assess(self, body: AssessmentRequest) -> AssessmentResponse:
        started = time.perf_counter()
        selected = body.architecture or self.settings.default_architecture
        trace = get_current_run_tree()
        if trace is not None:
            trace.add_tags(["compliance-copilot", selected, self.settings.runtime_mode])
            trace.add_metadata({
                "audit_id": body.audit_id,
                "architecture": selected,
                "runtime_mode": self.settings.runtime_mode,
                "prompt_strategy": self.settings.prompt_strategy,
            })
        previous = self.memory.inspect(body.audit_id)
        self.memory.add_event(body.audit_id, "user", body.model_dump_json())
        session = ToolSession(self.catalog, body.control_ids, body.propose_remediation, body.draft_summary)
        runner = run_monolith if selected == "monolith" else run_multi_agent
        try:
            answer, route, stats = runner(body, previous, session, self.settings)
        except AgentExecutionError:
            logger.exception("Assessment model execution failed for audit %s", body.audit_id)
            self.memory.add_event(body.audit_id, "error", "Model execution failed; no completed run was saved.")
            raise
        run = AssessmentResponse(
            audit_id=body.audit_id,
            run_id=f"RUN-{uuid.uuid4().hex}",
            architecture=selected,
            runtime_mode=self.settings.runtime_mode,
            answer=answer,
            route=route,
            findings=[self.catalog.assess(item) for item in body.control_ids],
            proposals=list(session.proposals.values()),
            draft=session.draft,
            tool_calls=[item.tool for item in session.trace],
            tool_results=session.trace,
            latency_seconds=round(time.perf_counter() - started, 6),
            token_count=stats.token_count,
            model_calls=stats.model_calls,
            fixture_as_of=str(self.catalog.as_of),
            limitations=[
                "Synthetic internal controls and evidence only; not legal advice, certification or a full framework mapping.",
                "Fixture freshness is evaluated at the frozen fixture date, not the current wall clock.",
                "Findings and artifact fields are deterministic; live narrative is model-generated and needs human review.",
                "No execution, approval or publication capability exists.",
            ],
        )
        self.memory.save_run(run)
        return run
