"""RLM bridge tests — long-doc escalation entry point.

Covers the matrix: (below threshold | above threshold) × (ratified |
not ratified) plus the size-estimator edge cases. See
``orchestration/rlm/bridge.py``.
"""

from __future__ import annotations

from orchestration.rlm.bridge import (
    RLM_BYTES_PER_TOKEN_ESTIMATE,
    estimate_tokens_from_bytes,
    is_ratified,
    maybe_escalate_to_rlm,
)
from orchestration.rlm.prime_agent_backend import PrimeAgentRLMBackend

# ── Token estimator ──────────────────────────────────────────────────


def test_estimate_tokens_zero_for_invalid_size():
    assert estimate_tokens_from_bytes(0) == 0
    assert estimate_tokens_from_bytes(-1) == 0


def test_estimate_tokens_matches_constant():
    # 1 MiB doc → 1 MiB / 4 = 262 144 tokens — well over the 64K threshold.
    one_mib = 1_048_576
    expected = one_mib // RLM_BYTES_PER_TOKEN_ESTIMATE
    assert estimate_tokens_from_bytes(one_mib) == expected


# ── Ratification gate ────────────────────────────────────────────────


def test_is_ratified_reads_env_var(monkeypatch):
    monkeypatch.delenv("ANTIEK_RLM_RATIFIED", raising=False)
    assert is_ratified() is False
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")
    assert is_ratified() is True
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "yes")
    # only literal "1" ratifies — anything else is treated as not-set.
    assert is_ratified() is False


# ── Decision matrix ─────────────────────────────────────────────────


def test_below_threshold_skips_rlm(monkeypatch):
    monkeypatch.delenv("ANTIEK_RLM_RATIFIED", raising=False)
    d = maybe_escalate_to_rlm(
        document_id="doc-small",
        investigation_id="inv-1",
        estimated_tokens=1_000,
    )
    assert d.above_threshold is False
    assert d.escalated is False
    assert d.session_id is None
    assert d.reason == "below_threshold"


def test_above_threshold_unratified_defers(monkeypatch):
    monkeypatch.delenv("ANTIEK_RLM_RATIFIED", raising=False)
    d = maybe_escalate_to_rlm(
        document_id="doc-long-1",
        investigation_id="inv-1",
        estimated_tokens=128_000,
    )
    assert d.above_threshold is True
    assert d.ratified is False
    assert d.escalated is False
    assert d.session_id is None
    assert d.reason == "deferred_pending_ratification"


def test_above_threshold_ratified_escalates(monkeypatch):
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")
    d = maybe_escalate_to_rlm(
        document_id="doc-long-2",
        investigation_id="inv-1",
        estimated_tokens=128_000,
    )
    assert d.above_threshold is True
    assert d.ratified is True
    assert d.escalated is True
    assert d.session_id is not None
    assert d.session_id.startswith("rlm-")
    assert d.reason.startswith("escalated_to_rlm")


def test_decision_carries_inputs_back(monkeypatch):
    monkeypatch.delenv("ANTIEK_RLM_RATIFIED", raising=False)
    d = maybe_escalate_to_rlm(
        document_id="doc-X",
        investigation_id="inv-9",
        estimated_tokens=70_000,
        threshold_tokens=64_000,
    )
    assert d.document_id == "doc-X"
    assert d.investigation_id == "inv-9"
    assert d.estimated_tokens == 70_000
    assert d.threshold_tokens == 64_000


def test_threshold_override_respected(monkeypatch):
    """Caller-supplied threshold takes precedence over the default."""
    monkeypatch.delenv("ANTIEK_RLM_RATIFIED", raising=False)
    # Same token count, different thresholds → different verdicts.
    below = maybe_escalate_to_rlm(
        document_id="d",
        investigation_id="i",
        estimated_tokens=50_000,
        threshold_tokens=64_000,
    )
    above = maybe_escalate_to_rlm(
        document_id="d",
        investigation_id="i",
        estimated_tokens=50_000,
        threshold_tokens=32_000,
    )
    assert below.above_threshold is False
    assert above.above_threshold is True



def test_above_threshold_ratified_prime_backend_switches_root_executor(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")
    monkeypatch.setenv("ANTIEK_PRIME_AGENT_RLM_ENABLED", "1")
    backend = PrimeAgentRLMBackend(enabled=True, cwd=tmp_path)

    captured = {}

    class _SessionStub:
        class _State:
            session_id = "rlm-stub"

        state = _State()

    def _fake_create_session(**kwargs):
        captured.update(kwargs)
        return _SessionStub()

    monkeypatch.setattr("orchestration.rlm.bridge.create_session", _fake_create_session)

    d = maybe_escalate_to_rlm(
        document_id="doc-long-prime",
        investigation_id="inv-prime",
        estimated_tokens=128_000,
        prime_backend=backend,
    )

    assert d.escalated is True
    assert d.session_id == "rlm-stub"
    assert captured["root_executor"] == "prime_agent"
    assert captured["prime_goal_brief"] is not None
