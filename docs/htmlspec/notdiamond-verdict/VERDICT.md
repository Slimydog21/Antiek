# NotDiamond usefulness verdict (campaign 2026-07-09)

## Decision

| Mode | Verdict | Why |
|---|---|---|
| **Advisory router** (recommend tier/model; human or call-site may ignore) | **GO** (measured wedge only) | Aligns with existing `preference_hints` pattern and draft `antiek-notdiamond` Wave-1 sprints; does not violate §16 authority rules if dispatch remains Hermes-primary and ND never owns the call. |
| **Authoritative dispatch** (ND chooses and executes provider) | **NO-GO / REJECT** | Violates Antiek §16 REJECT list and plan non-goal: third party must not be authoritative dispatch provider. |
| **Custom-router training / continuous retrain** | **NO-GO until G8 / Loop-3 unlock** | Spec already gates this (sprint-08 custom-router runbook); operator unlock required. |

## Investigation grounding

1. **`integrations.toml`** — `[notdiamond]` is draft: “ND advisory layer above dispatch; 8 sprints / 4 waves; not yet wired.” Package named, justification cites measured advisory only.
2. **Existing draft htmlspec** — `~/Antiek/specs/antiek-notdiamond/` sprints 01–08: adapter → event log → advisory routing → role candidates → observability → chaos kill-switch → training CSV → custom-router runbook. Wave-1 adapter branches exist historically (`ant-nd/spr01-adapter`, `caffen/notdiamond-wave1-main`) but are not required for this campaign’s spine.
3. **In-tree analog already ships** — `substrate/dispatch/preference_hints.py` produces **advisory** tier recommendations from DP preference learning; router does not consume it; callers may. NotDiamond would be a second advisory source with the same shape.
4. **Measured-wedge constraint** — Plan + resume docs: only advisory measured-wedge work is in bounds without operator unlock; custom training is G8/Loop-3 gated.
5. **vs hand dispatch** — Hand/operator selection via `substrate/model_control` (this campaign) + `model_override` on `dispatch()` already covers explicit control. ND’s value is multi-model auto-suggest when the operator does **not** want to pick — complementary, not a replacement for the decision-tree tab.

## When ND is useful

- High volume of heterogeneous roles (distill vs synthesize vs wrestle) where static tier maps underperform.
- Operator wants a kill-switched external suggestion stream logged as events (auditability) without giving up budget/control plane.

## When ND is not worth it (yet)

- Single preferred model workflow (professional researcher with a known driver).
- Before Antiek-bench has task-class scores — routing without task labels is noise.
- If the only available integration is cloud authority over keys — conflicts with BYOK/settings model.

## Executable path if operator unlocks Wave-1

Reuse `~/Antiek/specs/antiek-notdiamond/` sprints 01–03 (adapter, event log, advisory routing). Wire recommendations into `model_control` as **suggested_model_id** only; never bypass `select_driver` / budget projection. Kill-switch env `ANTIEK_NOTDIAMOND=0` default off.

## Non-goals restated

- No silent ND-owned dispatch.
- No training CSV promotion without G8.
- No dual runtime.

## Measured shadow implementation (2026-07-10)

ABLW Sprint 3 implements the measured wedge at
`substrate/antiek_bench/live/nd_shadow.py`. It is double-gated by explicit
configuration and `ANTIEK_NOTDIAMOND`, always requests `hash_content=true`,
accepts exactly the two benchmark candidates, and records recommendations in a
separate privacy-bounded journal. The module has no dispatch or model-selection
imports and exposes no dispatch-shaped output. Recommendations are evidence for
the weekly verdict only; they cannot alter calls, scores, budgets, or the
operator's selected driver. Custom-router training remains blocked on G8.
