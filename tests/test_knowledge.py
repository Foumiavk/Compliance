from datetime import timedelta

import pytest

from complianceops.knowledge import Catalog


@pytest.mark.parametrize("control_id,expected", [
    ("AC-01", "insufficient_evidence"),
    ("BC-01", "supported"),
    ("VR-01", "insufficient_evidence"),
])
def test_default_findings(control_id, expected):
    assert Catalog().assess(control_id).status == expected


def test_stale_and_wrong_scope_are_rejected():
    finding = Catalog().assess("AC-01")
    assert finding.evidence_ids == []
    assert set(finding.rejected_evidence_ids) == {"EV-ACCESS-2026Q2", "EV-ACCESS-STAGING"}
    assert "does not prove control failure" in finding.rationale


@pytest.mark.parametrize("age,expected", [
    (-1, "insufficient_evidence"), (0, "supported"), (90, "supported"), (91, "insufficient_evidence"),
])
def test_freshness_boundaries(age, expected):
    catalog = Catalog()
    record = catalog.list_evidence("BC-01")[0]
    record.collected_on = str(catalog.as_of - timedelta(days=age))
    catalog.evidence = [record]
    assert catalog.assess("BC-01").status == expected


def test_failure_takes_precedence_over_passing_evidence():
    catalog = Catalog()
    failed = catalog.list_evidence("BC-01")[0]
    failed.result = "fail"
    failed.evidence_id = "EV-CONFLICT"
    catalog.evidence.append(failed)
    finding = catalog.assess("BC-01")
    assert finding.status == "gap"
    assert set(finding.evidence_ids) == {"EV-RESTORE-20261010", "EV-CONFLICT"}


def test_search_only_returns_matching_playbooks():
    catalog = Catalog()
    assert catalog.search_playbooks("AC-01")[0]["playbook_id"] == "PB-ACCESS-01"
    assert catalog.search_playbooks("zzzxxyy") == []
    with pytest.raises(ValueError, match="positive"):
        catalog.search_playbooks("access", limit=0)


def test_catalog_returns_copies():
    catalog = Catalog()
    catalog.get_control("BC-01").scope = "staging"
    catalog.list_evidence("BC-01")[0].result = "fail"
    assert catalog.assess("BC-01").status == "supported"
