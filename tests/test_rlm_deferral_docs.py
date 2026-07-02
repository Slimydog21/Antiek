"""RLM deferral documentation must track the implemented ratification gate."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFERRALS = ROOT / "docs" / "engineering_deferrals.md"


def test_d4_deferral_tracks_shipped_rlm_substrate_without_overclaiming_activation() -> None:
    text = DEFERRALS.read_text(encoding="utf-8")
    compact = " ".join(text.split())

    assert "## D4 — RLM-1 through RLM-5 implementations" in text
    assert "Engineering substrate shipped; activation deferred" in text
    assert "RLM-1 has a stub" not in text
    assert "RLM-2 through RLM-5 not started" not in text
    assert "orchestration/rlm/bridge.py" in text
    assert "orchestration/rlm/long_corpus.py" in text
    assert "orchestration/loop_one/rlm_orchestrator.py" in text
    assert "interfaces/research/environments/rlm_env.py" in text
    assert "tools/training/harvest.py" in text
    assert (
        "tests/test_rlm_bridge.py tests/test_rlm_bridge_event_emission.py "
        "tests/test_rlm_events.py tests/test_rlm_long_corpus_and_investigation.py"
    ) in compact
    assert "146 passed" in text
    assert "ANTIEK_RLM_RATIFIED=1" in text
    assert "operator ratification remains required before live activation" in compact
    assert "Loop 3/G8 remains required for any training-time harvest or hosted RL" in compact
