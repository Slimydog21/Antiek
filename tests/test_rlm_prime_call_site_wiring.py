"""The RLM bridge's one live call site must actually supply a Prime backend.

WHY THIS FILE EXISTS
────────────────────
Eight RLM sites accept a ``prime_backend`` parameter. Before this wiring, **no
non-test code anywhere constructed one**, so ``_bridge_executor(None)`` returned
"dispatch" unconditionally. Every unit test passed, because every unit test passed a
backend in by hand.

That is the defect this file pins, and it is a defect about an ARGUMENT NOT BEING
PASSED, so the honest test is one that reads the call site. A behavioural test here
would need a DuckDB fixture and a document.loaded event to reach four lines of glue,
and would still not fail if someone deleted the keyword, because the deletion restores
the silently-inert default.

WHAT THIS PROVES, AND WHAT IT DOES NOT
──────────────────────────────────────
Proves: the live ``document.loaded`` call site passes ``prime_backend`` with a value
that is not the literal ``None``, and that ``PrimeAgentRLMBackend.run()`` honours
ANTIEK_PRIME_AGENT_RLM_ENABLED in both directions.

Does NOT prove that any Prime process is spawned from this path. READ THIS BEFORE
TREATING THE LANE AS ACTIVATION-READY, BECAUSE IT IS NOT: supplying the backend threads
an object through, it does not make the flags an execution switch. ``_bridge_executor``
(bridge.py:107-110) uses the object only as a truthiness token to return the string
"prime_agent", and that string is consumed twice and only twice, as ``root_executor=``
at bridge.py:174 and as the ``prime_goal_brief`` condition at bridge.py:177. bridge.py
contains no ``.run(`` and no ``.run_session(``. The only non-test
``prime_backend.run_session(...)`` in the repo is rlm_investigation.py:220, inside
``run_rlm_investigation``, which has no non-test caller. So with both flags set and a
real binary installed, document.loaded creates a differently labelled session and
spawns nothing. Re-verified against origin/main 9cd7692a on 2026-09-21.

``tests/test_rlm_bridge.py::test_above_threshold_ratified_prime_backend_switches_root_executor``
covers exactly what its name says: the root_executor LABEL switches. Neither test, nor
both together, proves invocation. The missing piece is production code that calls the
backend after ``create_session``, tracked as SPR-01 Task 3 in the antiek-v1-connect
spec, whose done-bar is a witness-file spawn count greater than zero.

The substrate itself is real and carefully built. The gap is reachability, not quality.
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
    """The flag switches the FACTORY's enabled bit, and only the documented spellings.

    Scope warning: this is about ``PrimeAgentRLMBackend.run()``, a method no production
    code on the document.loaded path ever calls. The flag does not switch on a Prime
    process anywhere. See the module docstring.
    """
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
