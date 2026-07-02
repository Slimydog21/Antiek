# §14.4 dispatch fidelity — the synthesizer Opus pin is REAL, FIXED, and now REACHABILITY-GUARDED

**Date:** 2026-06-04
**Status:** VERIFIED + GUARD INSTALLED (no routing change — verify-and-guard only)
**Owner:** Antiek — Convergence SPR-05 (dispatch fidelity)
**Surfaces:**
`interfaces/research/api/synthesizer.py:192-278` (`_research_tier_override`, the
window guard) + `synthesizer.py:281-303` (`_dispatch_once`);
`substrate/dispatch/config.yaml:64-89` (`tiers.synthesis` Opus pin + Hermes
fallback) + `config.yaml:91-105` (`tiers.verify` Hermes-primary + cross-family
fallback); `substrate/dispatch/research_tier.py` (the SEPARATE research lane);
`substrate/schemas/events.py:2113` (`research_tier: ... | None = None`);
`tools/reachability/probes/dispatch.py` (the new reachability probe);
`tests/test_dispatch_synthesis_pin.py` (the unit regression guard, untouched).

## The finding (VERIFIED, not assumed)

The §14.4 *silent default-tier model displacement* was a real defect: the
synthesizer (the human-read research artifact) silently routed to **DeepSeek**
instead of the declared **Opus** the instant `DEEPSEEK_API_KEY` existed. The
mechanism: the start-event `research_tier` field used to default to the string
`"deep"` (`== DEFAULT_RESEARCH_TIER`), which is **byte-indistinguishable** from
an operator-EXPLICIT `"deep"`. The synthesizer consumed that schema-default
`"deep"` as if it were an operator choice and routed synthesis onto the `"deep"`
research provider (DeepSeek). The only prior guard was provider-absence — which
evaporates the moment the key is present (the literal "turn the AI on" deploy).

**This is ALREADY FIXED on this branch (commit `b551f44`). SPR-05 did NOT
re-fix it.** Verified mechanically, not trusted from the brief:

1. **Schema default flipped to honest-absent.** `events.py:2113`:
   `research_tier: Literal["fast", "deep"] | None = None`. A default
   investigation now records `None`, not `"deep"`, so "no choice" is
   distinguishable from "chose deep".
2. **The synthesizer is pinned to Opus for the §14.4 measurement window.**
   `_research_tier_override` (`synthesizer.py:192-278`) reads the recorded tier
   and returns `(None, None)` for **EVERY** recorded value — `None`, schema-
   default, explicit `"deep"`, explicit `"fast"`, or a legacy pre-field row —
   leaving the config primary untouched. `_dispatch_once` (`synthesizer.py:284`)
   passes those `(None, None)` overrides to `dispatch(...)`, so the call resolves
   to the config pin: `openrouter / anthropic/claude-opus-4.7`
   (`config.yaml:81-82`).
3. **The research-RUNNER lane is correctly SEPARATE.**
   `resolve_research_tier("deep")` → `deepseek / deepseek-v4-pro`,
   `resolve_research_tier("fast")` → `xiaomi / mimo-v2.5-pro`
   (`research_tier.py:78-104`). The tier choice still does real work — it routes
   the reasoning-heavy RESEARCH work — it simply does not touch the synthesis
   VOICE while the pin holds.
4. **Silent swaps are now impossible.** Every dispatch emits a
   `DispatchCall(provider, model, tier, fallback_chain_index)` event
   (`router.py:295-326`, `events.py:741-761`), so a displacement would be a
   recorded, queryable fact, not a silent one.

**Mechanical verification this session:** `tests/test_dispatch_synthesis_pin.py`
+ `tests/test_research_tier_dispatch.py` → **27 passed**. The pin guard is cited
at `synthesizer.py:192-278`; the sunset sketch at `synthesizer.py:251-256` +
`270-276`.

## Fairness — steelman of keeping the silent downgrade (and why it loses)

**Steelman.** DeepSeek is dramatically cheaper than Opus. If a default
investigation produces a "good enough" synthesis on DeepSeek, defaulting to the
cheap provider is the cost-rational choice; the operator can always opt UP. The
fast/deep distinction is *most felt* at synthesis, so routing the synthesis
voice by the chosen tier is arguably where the choice matters most.

**Why it loses — during the window.** §14.4 is a **measurement window**: its
whole purpose is to decide, on real traffic, whether a cheaper synthesis
provider matches Opus closely enough to flip primary on cost grounds (the
verdict criterion is "verifier-pass-rate within 5pp", `config.yaml:71-73`). A
measurement taken over a **mixed** Opus/DeepSeek (or Opus/MiMo) voice answers no
question — you cannot compare "cheaper-vs-Opus" if the corpus you measure is
already half-cheaper. The window therefore needs **uncorrupted Opus traffic** on
the human-read artifact, which is exactly what the pin guarantees. The
cost-rational downgrade is the right *outcome to evaluate*, not a thing to
silently assume true before the evaluation runs.

**Why observability + the pin beat silence.** The defect's harm was not "used a
cheaper model" — it was that the substitution was **silent and
indistinguishable** from an operator choice, so neither the operator nor the
§14.4 verdict could see it happening. The fix attacks the silence on two axes:
(1) the `DispatchCall` event makes every routing decision an auditable fact
(`fallback_chain_index` records whether the primary or a fallback served), and
(2) the pin makes the window's traffic deterministic and known. A logged,
deterministic Opus call is defensible; a silent, key-triggered DeepSeek swap is
not.

## Milestone 3 — the Hermes fallback is a LEGITIMATE failover, NOT the §14.4 defect

The §14.4 defect must not be confused with the cross-family **fallback chains**
in `config.yaml`, which are preserved untouched by SPR-05:

| tier | primary | fallback | what it is |
|---|---|---|---|
| `synthesis` | `openrouter / anthropic/claude-opus-4.7` | `hermes / grok-4.3` | Opus pin (window); Grok is the provider-outage failover |
| `verify` | `hermes / grok-4.3` | `openrouter / deepseek/deepseek-v4-pro` | Hermes-primary cross-family verification with a mandatory fallback |

These fallbacks are **provider-outage failover**, and they are categorically
different from the §14.4 silent swap on two dimensions:

* **Trigger.** A fallback fires only when the *primary provider fails* (raises a
  retryable `ProviderError` — outage, unregistered, rate-limited;
  `router.py:441-449`). The §14.4 defect fired on a *healthy* primary, triggered
  by the mere *presence of a key*, with no failure anywhere.
* **Observability.** A fallback is **logged** via `fallback_chain_index` on the
  `DispatchCall` event (`0` = primary served, `1` = first fallback, …). The
  §14.4 defect was a **silent** schema-default tier change with no such marker —
  the call looked, on every recorded surface, like a normal primary dispatch.

The verifier MUST keep a fallback (`config.yaml:99-105`): the verifier is the
role most directly responsible for catching substrate-quality regressions, and a
bridge outage with no fallback would brick every verifier call — an
architectural invariant guarded by `tests/test_dispatch_fallback_chain.py`.
**SPR-05 does not touch `config.yaml`, `research_tier.py`, or the pin logic in
`synthesizer.py` — it verifies and guards only.**

## The guard SPR-05 installs — `tools/reachability/probes/dispatch.py`

The unit regression guard (`test_dispatch_synthesis_pin.py`) asserts the pin
RESOLVES correctly against the real config. It is non-vacuous and load-bearing.
But — exactly like the compounding flywheel that shipped DEAD behind green unit
tests (the SPR-01 keystone failure) — a correct unit test does not prove the pin
is **REACHED from the real product boot**. The new probe is the missing
reachability gate:

* boots the app through the **production `create_app()` factory** (proving the
  app boots with the pin in the tree);
* installs **recording-stub providers** for the real synthesis chain
  (`openrouter`, `hermes`) + `deepseek` — the sanctioned no-paid-calls technique
  the §14.4 unit guard itself uses (`test_dispatch_synthesis_pin.py:55-108`):
  the stubs replace ONLY the network edge, never the routing path under test;
* sets `DEEPSEEK_API_KEY` (reproduces the exact "turn the AI on" deploy);
* emits a **DEFAULT-tier** investigation start (`research_tier` omitted → `None`)
  into an isolated temp event dir;
* drives the **REAL** `synthesizer._dispatch_once` against the **REAL**
  `config.yaml`;
* asserts the **OUTCOME** on three independent reads: the returned `policy_id`,
  the openrouter stub's recorded call (`== anthropic/claude-opus-4.7`), and the
  persisted `DispatchCall` event (`provider==openrouter`,
  `model==anthropic/claude-opus-4.7`, `fallback_chain_index==0`) — and that the
  **deepseek stub was NEVER called**.

This is outcome-asserting (the model ACTUALLY dispatched), not code-presence.
**Teeth proven this session:** neutering the pin (a scratch edit making
`_research_tier_override` resolve the recorded-or-default tier) flips the probe
to `[BLOCKED] … resolved to 'deepseek/deepseek-v4-pro' … [displaced to deepseek]`
(exit 1); restoring the tree returns it to `[REACHABLE]` (exit 0). The full
runner (`python -m tools.reachability.probe_runner`: flywheel + read +
retrieval_gate + dispatch) stays all-green, exit 0.

## SUNSET — the landmine a future maintainer MUST defuse correctly

**The synthesizer pin is TEMPORARY.** It exists only for the §14.4 measurement
window (2026-05-19 → the Sprint-20 verdict). At the verdict (or window
auto-revert), the pin lifts. This is an **operator-ratified edit, not a silent
one**, and it lands in TWO+1 places that MUST move together:

1. **The guard** (`synthesizer.py:270-276`): re-enable the per-tier override for
   an **explicit, non-default** tier whose provider is live — the sketch is
   already written in the comment:
   ```python
   if _recorded and _recorded != DEFAULT_RESEARCH_TIER:
       t = resolve_research_tier(_recorded)
       if t.provider in _PROVIDER_REGISTRY:
           return t.provider, t.model
   ```
2. **The unit guard** (`test_dispatch_synthesis_pin.py`): flip the matching
   assertions (`test_explicit_deep_also_stays_pinned_to_opus`,
   `test_explicit_fast_also_stays_pinned_to_opus`) from "explicit tier stays
   Opus" to "explicit non-default tier routes; default stays Opus or flips per
   the verdict".
3. **⚠ THE REACHABILITY PROBE** (`tools/reachability/probes/dispatch.py`) — the
   part a maintainer is most likely to forget. The probe **only drives the
   DEFAULT tier today**, so it does NOT over-assert the explicit-tier behaviour
   the verdict will decide — but its DEFAULT-tier assertion will need
   re-evaluation:
   * If the verdict keeps DEFAULT on Opus → the probe's DEFAULT-tier assertion
     stays as-is, and a NEW explicit-tier case should be ADDED to the probe
     (assert an explicit non-default tier now routes to its provider) so the
     re-enabled path is itself reachability-guarded.
   * If the verdict flips DEFAULT off Opus → the probe's `_PINNED_PROVIDER` /
     `_PINNED_MODEL` constants and the `[displaced to deepseek]` framing must be
     updated to the new default; the probe should then assert the NEW default
     routes and that the OLD default is no longer silently in effect.

   The probe's module docstring (the SUNSET section) records this requirement
   inline so it travels with the file. **Do not let the probe red as a surprise
   when the pin sunsets — it is a deliberate, decision-noted update.**

## Reconsider-if

* The Sprint-20 §14.4 verdict is recorded (the trigger to sunset — see above).
* `config.yaml` `tiers.synthesis` primary is changed off Opus (the pin's reason
  expired): the probe constants + this note must be updated in the same change.
* A second human-read artifact role is added (today only `synthesizer` is the
  human-facing voice; a new such role would want its own pin + probe coverage).

## Verified vs assumed

* **VERIFIED:** the pin holds (27 tests pass); the guard at
  `synthesizer.py:192-278`; the config pin at `config.yaml:81-82`; the separate
  research lane at `research_tier.py:78-104`; the probe REACHABLE + the full
  runner green (exit 0); the probe's teeth (neuter → BLOCKED [displaced to
  deepseek] → restore → REACHABLE).
* **ASSUMED (not re-litigated here):** the original `b551f44` claim that the
  pre-fix code failed this exact assertion — taken from the SPR-01 handoff +
  the `test_dispatch_synthesis_pin.py` docstring (lines 12-18), which states the
  test FAILS on pre-fix code. SPR-05 proved the *current* probe's teeth on a
  scratch neuter of the *current* guard (equivalent displacement), not a
  checkout of the pre-`b551f44` tree.
