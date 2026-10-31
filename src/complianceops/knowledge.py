from __future__ import annotations

import json
import re
from datetime import date
from importlib.resources import files

from .domain import Control, ControlId, Evidence, Finding


class Catalog:
    """Synthetic, versioned systems of record; never populated from model output."""

    def __init__(self) -> None:
        payload = json.loads(files("complianceops").joinpath("fixtures/catalog.json").read_text())
        self.as_of = date.fromisoformat(payload["as_of"])
        self.controls = {
            control.control_id: control
            for control in (Control.model_validate(row) for row in payload["controls"])
        }
        self.evidence = [Evidence.model_validate(row) for row in payload["evidence"]]
        self.playbooks: list[dict[str, str]] = payload["playbooks"]

    def get_control(self, control_id: ControlId) -> Control:
        if control_id not in self.controls:
            raise ValueError(f"Unknown control: {control_id}")
        return self.controls[control_id].model_copy(deep=True)

    def list_evidence(self, control_id: ControlId) -> list[Evidence]:
        self.get_control(control_id)
        return [item.model_copy(deep=True) for item in self.evidence if item.control_id == control_id]

    def search_playbooks(self, query: str, limit: int = 3) -> list[dict[str, str]]:
        if limit < 1:
            raise ValueError("limit must be positive")
        tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
        ranked = sorted(
            (
                (len(tokens & set(re.findall(r"[a-z0-9]+", " ".join(item.values()).lower()))), item)
                for item in self.playbooks
            ),
            key=lambda pair: pair[0],
            reverse=True,
        )
        return [dict(item) for score, item in ranked[:limit] if score > 0]

    def assess(self, control_id: ControlId) -> Finding:
        control = self.get_control(control_id)
        evidence = self.list_evidence(control_id)
        accepted: list[Evidence] = []
        rejected: list[str] = []
        for item in evidence:
            age = (self.as_of - date.fromisoformat(item.collected_on)).days
            if item.scope == control.scope and 0 <= age <= control.max_age_days:
                accepted.append(item)
            else:
                rejected.append(item.evidence_id)
        playbook = next(item for item in self.playbooks if item["control_id"] == control_id)
        if not accepted:
            status = "insufficient_evidence"
            rationale = (
                f"No current, in-scope evidence as of {self.as_of}. "
                f"Evidence must match {control.scope} and be no older than {control.max_age_days} days. "
                "Missing, stale or out-of-scope evidence does not prove control failure."
            )
        elif any(item.result == "fail" for item in accepted):
            status = "gap"
            rationale = "At least one current, in-scope record reports failure; conflicting records require review."
        else:
            status = "supported"
            rationale = "Current, in-scope synthetic evidence supports this illustrative control, not certification."
        return Finding(
            control_id=control_id,
            policy_id=control.policy_id,
            owner=control.owner,
            status=status,
            evidence_ids=[item.evidence_id for item in accepted],
            rejected_evidence_ids=rejected,
            rationale=rationale,
            next_step=(
                f"Retain evidence and follow the next review schedule ({playbook['playbook_id']})."
                if status == "supported"
                else f"{playbook['playbook_id']}: {playbook['content']}"
            ),
        )
