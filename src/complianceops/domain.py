from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from .config import Architecture, RuntimeMode

AuditId = Annotated[str, StringConstraints(pattern=r"^AUD-[A-Za-z0-9-]{1,64}$")]
ControlId = Literal["AC-01", "BC-01", "VR-01"]
FindingStatus = Literal["supported", "gap", "insufficient_evidence"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AssessmentRequest(StrictModel):
    audit_id: AuditId
    request: str = Field(min_length=3, max_length=6000)
    control_ids: list[ControlId] = Field(min_length=1, max_length=3)
    architecture: Architecture | None = None
    propose_remediation: bool = True
    draft_summary: bool = True

    @field_validator("request")
    @classmethod
    def strip_request(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("request must contain at least three non-whitespace characters")
        return value

    @field_validator("control_ids")
    @classmethod
    def unique_controls(cls, value: list[ControlId]) -> list[ControlId]:
        if len(set(value)) != len(value):
            raise ValueError("control_ids must not contain duplicates")
        return value


class Control(StrictModel):
    control_id: ControlId
    title: str
    owner: str
    policy_id: str
    requirement: str
    max_age_days: int = Field(gt=0)
    scope: str


class Evidence(StrictModel):
    evidence_id: str
    control_id: ControlId
    title: str
    collected_on: str
    scope: str
    result: Literal["pass", "fail"]
    source: str
    content: str


class Finding(StrictModel):
    control_id: ControlId
    policy_id: str
    owner: str
    status: FindingStatus
    evidence_ids: list[str]
    rejected_evidence_ids: list[str]
    rationale: str
    next_step: str


class Proposal(StrictModel):
    proposal_id: str
    control_id: ControlId
    policy_id: str
    evidence_ids: list[str]
    owner: str
    recommendation: str
    status: Literal["awaiting_control_owner_approval"] = "awaiting_control_owner_approval"
    executed: Literal[False] = False


class SummaryDraft(StrictModel):
    draft_id: str
    audience: Literal["internal_audit"] = "internal_audit"
    content: str
    status: Literal["awaiting_compliance_lead_review"] = "awaiting_compliance_lead_review"
    published: Literal[False] = False


class ToolResult(StrictModel):
    agent: str
    tool: str
    result: dict[str, object]


class AssessmentResponse(StrictModel):
    audit_id: AuditId
    run_id: str
    architecture: Architecture
    runtime_mode: RuntimeMode
    answer: str
    route: list[str]
    findings: list[Finding]
    proposals: list[Proposal]
    draft: SummaryDraft | None
    tool_calls: list[str]
    tool_results: list[ToolResult]
    latency_seconds: float
    token_count: int
    model_calls: int
    fixture_as_of: str
    limitations: list[str]
