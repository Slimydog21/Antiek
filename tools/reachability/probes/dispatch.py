#!/usr/bin/env python3
"""Dispatch-fidelity reachability probe — Antiek Convergence SPR-05 (M2).

The §14.4 silent default-tier model displacement was real: the synthesizer
(the human-read research artifact) silently routed to DeepSeek instead of the
declared Opus the instant ``DEEPSEEK_API_KEY`` existed, because a schema-
DEFAULT research tier of "deep" was byte-indistinguishable from an operator-
EXPLICIT "deep" and the synthesizer consumed it. That defect is ALREADY FIXED
on this branch (commit b551f44): ``research_tier`` defaults to ``None``
(substrate/schemas/events.py:2113); the synthesizer is pinned to Opus during
the §14.4 measurement window via
``interfaces/research/api/synthesizer.py::_research_tier_override`` (returns
``(None, None)`` for EVERY recorded tier → the config-pinned
``openrouter / anthropic/claude-opus-4.7`` primary); the research-RUNNER lane
(``resolve_research_tier`` "deep"→deepseek) is correctly SEPARATE; every
dispatch emits a ``DispatchCall(provider, model, tier, fallback_chain_index)``
event so a silent swap is observable, not silent.

THIS PROBE is the missing REACHABILITY gate for the fix. Every OTHER guard on
the pin asserts CODE or RESOLUTION against a synthetic/real config in a unit
test (``tests/test_dispatch_synthesis_pin.py``,
``tests/test_research_tier_dispatch.py``). Those are non-vacuous and load-
bearing — but, exactly like the flywheel that shipped DEAD behind green unit
tests (SPR-01 keystone), a correct unit test does not prove the pin is REACHED
from the real product boot. This probe boots the app through the PRODUCTION
``create_app()`` factory, then drives the REAL synthesizer dispatch path
(``synthesizer._dispatch_once`` → ``substrate.dispatch.dispatch`` → the REAL
``config.yaml``) on a DEFAULT-tier investigation with ``DEEPSEEK_API_KEY``
present, and asserts the OUTCOME: the model ACTUALLY dispatched is
``openrouter / anthropic/claude-opus-4.7`` at ``fallback_chain_index == 0``,
and the deepseek stub was NEVER called.

────────────────────────────────────────────────────────────────────────────
WHY RECORDING STUBS ARE NOT THE "fixture-injection anti-pattern" (rigor/
honesty). The SPR-01 README forbids injecting ``retrieval_substrate=`` or
pre-wiring a dependency prod does not wire — because that HIDES the exact
wiring path the gate exists to verify. This probe does NOT hide the wiring
path it verifies: it drives the REAL ``_dispatch_once`` against the REAL
``config.yaml`` through the REAL ``dispatch`` router and the REAL
``_research_tier_override`` guard. The ONLY thing the recording stubs replace
is the network edge of each provider adapter (the bytes that would leave the
process to a paid API). That is mandatory here — the local env may lack
provider keys, and asserting on a LIVE Opus/DeepSeek call would (a) cost
operator credentials and (b) be a flaky network assertion, not a routing
assertion. The §14.4 regression guard itself uses exactly this recording-stub
technique (tests/test_dispatch_synthesis_pin.py:55-108) for the same reason:
to assert WHICH provider/model the router RESOLVED to, with zero network I/O.
The outcome asserted is the resolved (provider, model) the router chose — read
from the recording stub's call log AND from the persisted DispatchCall event —
NOT the presence of the pin code.

We boot ``create_app()`` first (and let it run its real
``register_default_providers`` pass) so the probe proves the production app
BOOTS with the pin in place; we then ``reset_provider_registry()`` and install
recording stubs so the subsequent dispatch resolves WHICH provider the router
picks without leaving the process. The DEEPSEEK_API_KEY-present condition (the
literal "turn the AI on" deploy that voided §14.4) is reproduced exactly.

────────────────────────────────────────────────────────────────────────────
SUNSET (defensibility — see docs/decisions/acv-spr05-dispatch-fidelity.md).
The synthesizer pin is TEMPORARY: it lifts at the Sprint-20 §14.4 verdict
(synthesizer.py:251-256 + the per-tier re-enable sketched at
synthesizer.py:270-276, plus the matching assertion flip in
test_dispatch_synthesis_pin.py). WHILE THE PIN HOLDS this probe asserts a
DEFAULT-tier synthesizer dispatch lands on Opus. WHEN THE PIN SUNSETS this
probe's assertion MUST be updated in lockstep: a DEFAULT tier stays Opus (or
flips per the verdict), but an EXPLICIT non-default tier will then be ALLOWED
to route the synthesizer — so a flip that re-enables explicit-tier routing
must update THIS probe (add an explicit-tier case) rather than letting it red
as a surprise. The probe only ever drives the DEFAULT tier today, so it does
not over-assert the explicit-tier behaviour that the verdict will decide.
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import os
import tempfile

from tools.reachability.probe_runner import ProbeResult

# The §14.4-pinned synthesis target. THE outcome this probe defends: a DEFAULT-
# tier synthesizer dispatch resolves HERE, never to deepseek, while the pin
# holds. Sourced from substrate/dispatch/config.yaml ``tiers.synthesis``.
_PINNED_PROVIDER = "openrouter"
_PINNED_MODEL = "anthropic/claude-opus-4.7"

# The provider the "deep" research tier maps to (research_tier.py). The §14.4
# defect routed the SYNTHESIZER here on a schema-default "deep"; the probe
# proves it does NOT, even with the key live.
_DISPLACED_PROVIDER = "deepseek"


class _RecordingStubProvider:
    """Records the (name, model) it was called as so the probe can assert
    WHICH provider/model the router RESOLVED to — without any network I/O.
    Mirrors tests/test_dispatch_synthesis_pin.py::_RecordingStubProvider so a
    maintainer who knows one knows the other. Stands in for every real provider
    in the synthesis fallback chain (openrouter primary, hermes fallback) plus
    deepseek (the 'deep' research-tier provider that the §14.4 defect routed
    synthesis to)."""

    def __init__(self, name: str):
        self.name = name
        self.calls: list[str] = []

    def call(self, *, model, prompt, max_tokens, temperature):
        from substrate.dispatch import RawProviderResponse

        self.calls.append(model)
        return RawProviderResponse(
            text=f"{self.name}:{model}",
            raw_usage={},
            finish_reason="stop",
            latency_ms=1,
        )

    def normalize_usage(self, raw_usage):
        from substrate.dispatch import NormalizedUsage

        return NormalizedUsage(input_tokens=0, output_tokens=0)


def _probe() -> ProbeResult:
    # Isolate ALL substrate writes to per-PID temp paths so the probe never
    # touches the live shared DuckDB (held under the --workers 1 single-writer
    # lock) and reads back only the start event + DispatchCall event IT emitted.
    # Same isolation contract as the flywheel / retrieval_gate probes
    # (README "isolate your writes").
    pid = os.getpid()
    tmp_root = tempfile.mkdtemp(prefix=f"antiek-dispatch-probe-{pid}-")
    tmp_db = os.path.join(tmp_root, f"antiek-dispatch-probe-{pid}.db")
    tmp_events = os.path.join(tmp_root, "events")
    os.makedirs(tmp_events, exist_ok=True)

    # Every provider key the boot might read. We snapshot + restore them all.
    _provider_keys = (
        "DEEPSEEK_API_KEY",
        "OPENROUTER_API_KEY",
        "ANTHROPIC_API_KEY",
        "HERMES_API_KEY",
        "XAI_API_KEY",
        "XIAOMI_API_KEY",
        "OPENAI_API_KEY",
        "ANTIEK_OPERATOR_TOKEN",
    )
    saved = {
        k: os.environ.get(k)
        for k in ("ANTIEK_DUCKDB_PATH", "ANTIEK_RESEARCH_EVENTS_DIR", *_provider_keys)
    }
    os.environ["ANTIEK_DUCKDB_PATH"] = tmp_db
    os.environ["ANTIEK_RESEARCH_EVENTS_DIR"] = tmp_events
    # Defence-in-depth during the create_app() boot: keep paid providers OUT of
    # the registration pass so a leaky path fails fast rather than spending
    # operator credentials. We set DEEPSEEK_API_KEY *back on* AFTER the boot,
    # right before the dispatch, to reproduce the "turn the AI on" condition
    # against recording stubs (no real key is ever used — the stubs intercept
    # the call edge).
    for key in _provider_keys:
        os.environ[key] = ""

    try:
        # ── boot the app the PRODUCTION way (failure mode: boot_fail) ──
        # This proves the production factory BOOTS with the §14.4 pin in the
        # tree. We let it run its real register_default_providers pass (no
        # register_providers=False) so the boot is the real one; we then
        # reset the registry and install recording stubs for the dispatch.
        try:
            from interfaces.research.api.app import create_app

            create_app()  # NO register_providers=False — the real boot path
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(
                ok=False,
                reason=f"create_app() failed to boot: {type(exc).__name__}: {exc}",
                failure_mode="boot_fail",
            )

        # ── install recording stubs for the REAL synthesis chain ──
        # reset → register openrouter (synthesis primary), hermes (synthesis
        # fallback), deepseek (the 'deep' research provider §14.4 would have
        # displaced synthesis to). All three LIVE in the registry, so the probe
        # exercises the keys-PRESENT case: the pin must hold even though
        # deepseek is fully registered.
        try:
            from substrate.dispatch.router import (
                _PROVIDER_REGISTRY,
                register_provider,
                reset_provider_registry,
            )

            reset_provider_registry()
            openrouter = _RecordingStubProvider(_PINNED_PROVIDER)
            hermes = _RecordingStubProvider("hermes")
            deepseek = _RecordingStubProvider(_DISPLACED_PROVIDER)
            register_provider(openrouter)
            register_provider(hermes)
            register_provider(deepseek)
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(
                ok=False,
                reason=f"could not install recording stubs: {type(exc).__name__}: {exc}",
                failure_mode="error",
            )

        # Reproduce the literal "turn the AI on" deploy: DEEPSEEK_API_KEY set.
        # This is the exact condition that VOIDED §14.4 before the fix. The key
        # is a dummy and is never used — the deepseek stub intercepts the call
        # edge — but the registry now contains deepseek, which is what matters.
        os.environ["DEEPSEEK_API_KEY"] = "sk-ds-probe-dummy"

        # ── emit a DEFAULT-tier investigation start (research_tier omitted) ──
        # research_tier omitted ⇒ schema default (None) ⇒ the override returns
        # (None, None) ⇒ the config Opus pin holds. This is the byte-exact
        # default-investigation row the §14.4 defect mis-routed.
        investigation_id = f"acv-spr05-dispatch-probe-{pid}"
        try:
            from substrate.event_log import emit_typed
            from substrate.schemas import InvestigationStartRequestedPayload

            emit_typed(
                investigation_id,
                InvestigationStartRequestedPayload(
                    question="dispatch-fidelity probe",
                    context="",
                    topic_slug=None,
                    max_sub_questions=4,
                    # research_tier intentionally OMITTED → schema default None.
                ),
                role="operator",
            )
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(
                ok=False,
                reason=f"could not emit default-tier start event: "
                f"{type(exc).__name__}: {exc}",
                failure_mode="error",
            )

        # ── drive the REAL synthesizer dispatch path ──
        # The same in-process pattern the §14.4 guard uses
        # (tests/test_dispatch_synthesis_pin.py:131-166): a minimal Event-shaped
        # object carrying the investigation_id + event_id, fed to the REAL
        # _dispatch_once, which calls _research_tier_override (the pin) and then
        # the REAL dispatch router against the REAL config.yaml.
        try:
            from interfaces.research.api import synthesizer as synth_mod

            # Sanity: the keys-present condition is genuinely true.
            if _DISPLACED_PROVIDER not in _PROVIDER_REGISTRY:
                return ProbeResult(
                    ok=False,
                    reason="probe setup error: deepseek stub not registered",
                    failure_mode="error",
                )

            # A minimal Event-shaped object. Attributes are SET after the class
            # is defined (not in the class body) so the closure-captured
            # ``investigation_id`` local resolves unambiguously — a class body
            # does not see enclosing-function locals.
            class _StartEvent:
                pass

            _evt = _StartEvent()
            _evt.investigation_id = investigation_id
            _evt.event_id = f"evt-{investigation_id}"

            text, policy_id = synth_mod._dispatch_once("synthesize this", _evt)
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(
                ok=False,
                reason=f"synthesizer._dispatch_once raised: "
                f"{type(exc).__name__}: {exc}",
                failure_mode="error",
            )

        # ── OUTCOME assertion #1: the policy_id the dispatch returned ──
        # _dispatch_once returns f"{provider}/{model}" on success. The §14.4
        # pin requires the human-read synthesis artifact to be produced by Opus.
        expected_policy = f"{_PINNED_PROVIDER}/{_PINNED_MODEL}"
        if policy_id != expected_policy:
            displaced = _DISPLACED_PROVIDER in (policy_id or "")
            return ProbeResult(
                ok=False,
                reason=(
                    f"DEFAULT-tier synthesizer dispatch resolved to {policy_id!r}, "
                    f"NOT the §14.4 Opus pin {expected_policy!r}"
                    + (
                        " [displaced to deepseek]"
                        if displaced
                        else " — the synthesis voice is no longer pinned"
                    )
                    + ". _research_tier_override (synthesizer.py:192) is not "
                    "holding the config pin on a default investigation."
                ),
                failure_mode="feature_dead",
            )

        # ── OUTCOME assertion #2: the recording stub the router ACTUALLY called ──
        # The model the router actually SENT (not just the policy string).
        if openrouter.calls != [_PINNED_MODEL]:
            return ProbeResult(
                ok=False,
                reason=(
                    f"openrouter stub recorded calls {openrouter.calls!r}, "
                    f"expected exactly [{_PINNED_MODEL!r}] — the router did not "
                    "dispatch the pinned Opus model on the primary."
                ),
                failure_mode="feature_dead",
            )
        if deepseek.calls:
            return ProbeResult(
                ok=False,
                reason=(
                    f"deepseek stub WAS CALLED ({deepseek.calls!r}) on a DEFAULT-"
                    "tier synthesizer dispatch [displaced to deepseek] — this is "
                    "the §14.4 silent displacement REGRESSED. The live "
                    "DEEPSEEK_API_KEY displaced the Opus synthesis pin."
                ),
                failure_mode="feature_dead",
            )

        # ── OUTCOME assertion #3: the persisted DispatchCall event ──
        # Silent swaps are now impossible BECAUSE every dispatch emits a
        # DispatchCall(provider, model, tier, fallback_chain_index). Assert the
        # observability layer recorded the truth: provider/model == the pin,
        # fallback_chain_index == 0 (primary succeeded; no failover was needed).
        try:
            from substrate.event_log import trajectory
            from substrate.schemas import ActionType

            rows = trajectory(investigation_id)
            dispatch_rows = [
                r
                for r in rows
                if r.get("action_type") == ActionType.DISPATCH_CALL.value
            ]
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(
                ok=False,
                reason=f"could not read back DispatchCall event: "
                f"{type(exc).__name__}: {exc}",
                failure_mode="error",
            )

        if not dispatch_rows:
            return ProbeResult(
                ok=False,
                reason=(
                    "no DispatchCall event was emitted for the synthesizer "
                    "dispatch — the observability layer that makes silent swaps "
                    "impossible did not fire on the real path."
                ),
                failure_mode="feature_dead",
            )
        dc = dispatch_rows[-1].get("payload") or {}
        if (
            dc.get("provider") != _PINNED_PROVIDER
            or dc.get("model") != _PINNED_MODEL
            or dc.get("fallback_chain_index") != 0
        ):
            return ProbeResult(
                ok=False,
                reason=(
                    "DispatchCall event recorded a non-pinned synthesizer "
                    f"dispatch: provider={dc.get('provider')!r} "
                    f"model={dc.get('model')!r} "
                    f"fallback_chain_index={dc.get('fallback_chain_index')!r} "
                    f"(expected {_PINNED_PROVIDER!r} / {_PINNED_MODEL!r} / 0)."
                    + (
                        " [displaced to deepseek]"
                        if dc.get("provider") == _DISPLACED_PROVIDER
                        else ""
                    )
                ),
                failure_mode="feature_dead",
            )

        # All outcomes held: the DEFAULT-tier synthesizer dispatch resolved to
        # the §14.4 Opus pin on the primary (fallback_chain_index 0), the live
        # deepseek key did NOT displace it, and the DispatchCall event records
        # the truth. REACHABLE.
        return ProbeResult(ok=True, failure_mode="reachable")
    finally:
        # Restore the provider registry to a clean state for the next probe,
        # and restore env regardless of how this probe exited.
        try:
            from substrate.dispatch.router import reset_provider_registry

            reset_provider_registry()
        except Exception:  # noqa: BLE001 — best-effort cleanup
            pass
        for key, val in saved.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
        import shutil

        shutil.rmtree(tmp_root, ignore_errors=True)


# Imported lazily so this top-level import is cheap; build the descriptor here.
from tools.reachability.probe_runner import Probe  # noqa: E402

PROBE = Probe(
    id="dispatch",
    feature=(
        "dispatch fidelity (§14.4 synthesizer pinned to Opus on a default-tier "
        "dispatch; deepseek does not displace it)"
    ),
    run=_probe,
)
