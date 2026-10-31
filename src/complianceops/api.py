from __future__ import annotations

import logging
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Path, Response
from fastapi.responses import RedirectResponse

from .config import load_settings
from .domain import AssessmentRequest, AssessmentResponse
from .runtime import AgentExecutionError
from .service import ComplianceService


@lru_cache
def get_service() -> ComplianceService:
    settings = load_settings()
    logging.basicConfig(level=settings.log_level)
    return ComplianceService(settings)


Service = Annotated[ComplianceService, Depends(get_service)]
AuditPath = Annotated[str, Path(pattern=r"^AUD-[A-Za-z0-9-]{1,64}$")]


def create_app() -> FastAPI:
    app = FastAPI(
        title="Enterprise Compliance Evidence Copilot",
        version="1.0.0",
        description="Local teaching demo with synthetic data. Not an authenticated production service.",
    )

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/docs")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/controls")
    def controls(service: Service) -> dict[str, object]:
        return {
            "fixture_as_of": str(service.catalog.as_of),
            "controls": [item.model_dump() for item in service.catalog.controls.values()],
        }

    @app.post("/v1/assessments", response_model=AssessmentResponse)
    def assess(body: AssessmentRequest, service: Service) -> AssessmentResponse:
        try:
            return service.assess(body)
        except AgentExecutionError as exc:
            raise HTTPException(
                status_code=502,
                detail="Model execution failed. Check server logs and credentials; no completed assessment was saved.",
            ) from exc

    @app.get("/v1/audits/{audit_id}/memory")
    def memory(audit_id: AuditPath, service: Service) -> dict[str, object]:
        return service.memory.inspect(audit_id)

    @app.get("/v1/audits/{audit_id}/runs/{run_id}", response_model=AssessmentResponse)
    def get_run(audit_id: AuditPath, run_id: str, service: Service) -> AssessmentResponse:
        run = service.memory.get_run(audit_id, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found in this audit")
        return run

    @app.delete("/v1/audits/{audit_id}/memory", status_code=204)
    def clear_memory(audit_id: AuditPath, service: Service) -> Response:
        service.memory.clear(audit_id)
        return Response(status_code=204)

    return app


app = create_app()
