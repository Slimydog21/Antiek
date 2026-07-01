"""Documentation checks for prompt-autoresearch operator workflow."""

from __future__ import annotations

from pathlib import Path


def test_prompt_autoresearch_readme_documents_activation_workflow():
    readme = Path("tools/prompt_autoresearch/README.md")

    text = readme.read_text(encoding="utf-8")

    assert "calibration_cli" in text
    assert "verdict_cli" in text
    assert "write_outcomes_json" in text
    assert "synthesizer-noop-outcomes.json" in text
    assert "synthesizer-outcomes.json" in text
    assert "What this does not prove" in text
