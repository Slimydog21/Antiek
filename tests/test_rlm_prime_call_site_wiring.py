"""The RLM bridge's one live call site supplies a Prime backend — and only that.

WHY THIS FILE EXISTS
────────────────────
Eight RLM sites accept a ``prime_backend`` parameter. Until this wiring, **no
non-test code anywhere constructed one**, so ``_bridge_executor(None)`` returned
"dispatch" unconditionally. Every unit test passed, because every unit test passed a
backend in by hand.

That is the defect this file pins, and it is a defect about an ARGUMENT NOT BEING
PASSED — so the honest test is one that reads the call site. A behavioural test here
would need a DuckDB fixture and a document.loaded event to reach four lines of glue,
and would still not fail if someone deleted the keyword, because the deletion restores
the silently-inert default.

WHAT THIS PROVES, AND WHAT IT DOES NOT
──────────────────────────────────────
Proves: the live ``document.loaded`` call site passes ``prime_backend`` with a value
that is not the literal ``None``, and that the factory honours the documented flag in
both directions.

Does NOT prove — and an earlier version of this docstring wrongly claimed — that the
wiring closes the Prime lane's unreachability gap. It does not. ``_bridge_executor``
consumes the backend as a truthiness token to select the label
``root_executor="prime_agent"``; the bridge never calls ``.run()`` or
``.run_session()`` on it and nothing iterates the session it creates. With both flags
set and a binary installed, ``document.loaded`` spawns no Prime process. The wiring
changed a label, not an execution path.
``tests/test_rlm_bridge.py::test_above_threshold_ratified_prime_backend_switches_root_executor``
pins exactly that label selection and nothing more. Real execution from this call site
is SPR-01 Task 3, whose proof is a spawn count read from a witness file, not a label.
"""

from __future__ import annotations

import ast
from pathlib import Path

from orchestration.rlm.prime_agent_backend import (
    PrimeAgentRequest,
    PrimeAgentTerminalState,
    prime_agent_backend_from_environment,
)


def _request() -> PrimeAgentRequest:
    return PrimeAgentRequest(
        prompt="probe",
        workflow="call-site-wiring-test",
        request_id="call-site-wiring-probe",
    )

_WRESTLING = Path(__file__).resolve().parents[1] / "interfaces/research/api/wrestling.py"


def _escalate_calls() -> list[ast.Call]:
    tree = ast.parse(_WRESTLING.read_text())
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "maybe_escalate_to_rlm"
    ]


def test_the_live_call_site_supplies_a_prime_backend() -> None:
    calls = _escalate_calls()
    assert calls, "maybe_escalate_to_rlm is no longer called from wrestling.py"

    for call in calls:
        keywords = {kw.arg for kw in call.keywords}
        assert "prime_backend" in keywords, (
            "wrestling.py calls maybe_escalate_to_rlm without prime_backend — "
            "_bridge_executor(None) then returns 'dispatch' unconditionally and the "
            "Prime lane is unreachable again, silently."
        )
        supplied = next(kw.value for kw in call.keywords if kw.arg == "prime_backend")
        assert not (isinstance(supplied, ast.Constant) and supplied.value is None), (
            "prime_backend is passed as a literal None, which is the same as not "
            "passing it at all."
        )


def test_the_factory_is_off_by_default_so_wiring_changes_nothing() -> None:
    """Supplying the backend must not by itself enable anything.

    Asserted behaviourally rather than on a private attribute: with the flag unset,
    ``run()`` returns the DISABLED terminal state and spawns nothing. That is what
    makes this wiring safe to land before ratification.
    """
    backend = prime_agent_backend_from_environment(environ={})
    outcome = backend.run(_request())
    assert outcome.receipt.state is PrimeAgentTerminalState.DISABLED


def test_the_factory_honours_the_documented_flag() -> None:
    """The flag is the switch, and only the documented truthy spellings flip it."""
    for falsy in ("", "0", "no", "off", "maybe"):
        backend = prime_agent_backend_from_environment(
            environ={"ANTIEK_PRIME_AGENT_RLM_ENABLED": falsy}
        )
        assert backend.run(_request()).receipt.state is PrimeAgentTerminalState.DISABLED, (
            f"{falsy!r} must not enable the backend"
        )

    for truthy in ("1", "true", "yes", "TRUE"):
        backend = prime_agent_backend_from_environment(
            environ={"ANTIEK_PRIME_AGENT_RLM_ENABLED": truthy}
        )
        # Enabled means it stops returning DISABLED. It will still fail for other
        # reasons here (no binary configured in this environment), and that is fine —
        # the assertion is about the flag being read, not about Prime running.
        assert backend.run(_request()).receipt.state is not PrimeAgentTerminalState.DISABLED, (
            f"{truthy!r} should enable the backend"
        )
