import gradio as gr

from complianceops.config import load_settings
from complianceops.domain import AssessmentRequest
from complianceops.runtime import AgentExecutionError
from complianceops.service import ComplianceService
from pydantic import ValidationError

settings = load_settings()
service = ComplianceService(settings)


def assess(
    audit_id: str,
    request: str,
    architecture: str,
    control_ids: list[str],
    propose_remediation: bool,
    draft_summary: bool,
):
    try:
        body = AssessmentRequest.model_validate({
            "audit_id": audit_id,
            "request": request,
            "architecture": architecture,
            "control_ids": control_ids,
            "propose_remediation": propose_remediation,
            "draft_summary": draft_summary,
        })
        result = service.assess(body)
    except (ValidationError, AgentExecutionError) as exc:
        raise gr.Error(str(exc)) from exc
    return result.answer, result.model_dump(), service.memory.inspect(body.audit_id)


with gr.Blocks(title="Enterprise Compliance Copilot", analytics_enabled=False) as demo:
    gr.Markdown(
        f"# Enterprise Compliance Evidence Copilot\n"
        f"Runtime: **{settings.runtime_mode}**. Synthetic data only; not certification or legal advice.\n"
        "Compare a monolithic workflow with capability-scoped specialists. Nothing is executed or published."
    )
    with gr.Row():
        audit_id = gr.Textbox(value="AUD-20261025", label="Audit ID")
        architecture = gr.Radio(["monolith", "multi_agent"], value=settings.default_architecture, label="Architecture")
    controls = gr.CheckboxGroup(["AC-01", "BC-01", "VR-01"], value=["AC-01", "BC-01", "VR-01"], label="Approved control scope")
    request = gr.Textbox(
        value="Assess evidence readiness, identify gaps and unknowns, propose next steps and draft an internal audit summary.",
        label="Auditor request (offline mode uses the scope and flags, not free-text interpretation)",
        lines=3,
    )
    with gr.Row():
        proposals = gr.Checkbox(value=True, label="Create approval-required proposals")
        summary = gr.Checkbox(value=True, label="Create unpublished internal draft")
    button = gr.Button("Assess evidence", variant="primary")
    answer = gr.Markdown()
    diagnostics = gr.JSON(label="Findings, artifacts and execution trace")
    memory = gr.JSON(label="Audit memory")
    button.click(assess, [audit_id, request, architecture, controls, proposals, summary], [answer, diagnostics, memory])


if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", share=False)
