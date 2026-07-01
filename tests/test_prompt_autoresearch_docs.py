"""Documentation checks for prompt-autoresearch operator workflow."""

from __future__ import annotations

from pathlib import Path


def test_prompt_autoresearch_readme_documents_activation_workflow():
    readme = Path("tools/prompt_autoresearch/README.md")

    text = readme.read_text(encoding="utf-8")

    assert "calibration_cli" in text
    assert "readiness_cli" in text
    assert "verdict_cli" in text
    assert "write_outcomes_json" in text
    assert "synthesizer-noop-outcomes.json" in text
    assert "synthesizer-outcomes.json" in text
    assert "synthesizer-program-review.md" in text
    assert "What this does not prove" in text


def test_operator_gate_docs_start_with_readiness_audit():
    for rel in ("docs/OPERATOR_ACTIONS.md", "docs/operator_gate_actions.md"):
        text = Path(rel).read_text(encoding="utf-8")

        assert "tools.prompt_autoresearch.readiness_cli" in text
        assert "tools.prompt_autoresearch.calibration_cli" in text
        assert "synthesizer-program-review.md" in text
        assert text.index("tools.prompt_autoresearch.readiness_cli") < text.index(
            "tools.prompt_autoresearch.calibration_cli"
        )
        assert text.index("synthesizer-program-review.md") < text.index(
            "tools.prompt_autoresearch.calibration_cli"
        )
