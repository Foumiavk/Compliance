import runpy
from pathlib import Path

import gradio as gr
import pytest


@pytest.fixture
def ui(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNTIME_MODE", "offline")
    monkeypatch.setenv("MEMORY_DB_PATH", str(tmp_path / "ui.db"))
    return runpy.run_path(str(Path(__file__).resolve().parents[1] / "app.py"))


def test_ui_uses_shared_workflow(ui):
    answer, diagnostics, memory = ui["assess"](
        "AUD-ui", "Assess evidence.", "multi_agent", ["AC-01", "BC-01"], True, True,
    )
    assert "AC-01" in answer and "BC-01" in answer
    assert diagnostics["architecture"] == "multi_agent"
    assert diagnostics["draft"]["published"] is False
    assert memory["run_count"] == 1
    assert ui["demo"].analytics_enabled is False


def test_ui_surfaces_invalid_input(ui):
    with pytest.raises(gr.Error, match="validation"):
        ui["assess"]("invalid", "Assess evidence.", "monolith", [], False, False)
