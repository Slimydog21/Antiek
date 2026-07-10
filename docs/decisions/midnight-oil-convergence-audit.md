# Midnight Oil dispatch subsystem — convergence audit & keep/close partition

**Status:** PROPOSED — decision record + authoritative partition. Author: Opus 4.8
executor (/infinite), 2026-07-10. Grounded in an exhaustive 85-stage
effect-binding audit (8-analyst workflow `wf_dd3fc5c0-2af`, verbatim-evidence
required, 0 misclassifications) + a diff-based PR→stage mapping.

## What Midnight Oil is (and why it is not ceremony)

The "Midnight Oil" swarm built a real `substrate/midnight_oil/` subsystem: a
**two-phase-commit dispatch protocol for cost-bounded autonomous research.** A
*plan* phase mints reference-chained artifacts (`launch_packet → approval_receipt
→ runner_handoff → applied_run_receipt`), each `@model_validator` enforcing that
**no side effect happens until dispatch** — verbatim invariants like
`runner_handoff must not reserve budget`, `must not include provider calls`,
`must not mutate graph`, `applied_run_receipt must be planned_not_dispatched`,
`receipt chain must not already be dispatched`. An *apply* phase then runs staged
gates that each bind a **distinct external effect** (budget reservation → provider
route → retrieval → graph mutation → final artifact → activation). This is
§16/§9.0/single-writer-disciplined "plan before you spend or mutate" design, and
it is genuinely hard-to-vary.

An earlier read (inherited from a sibling's "ceremony runaway" label) dismissed
the whole set. That was wrong. So was a follow-up "empty-stub tail" hypothesis —
validator density holds constant at ~0.47 `model_validator`/class and 1,668
`ValueError` invariants across the chain. The pattern is real throughout.

## The real failure mode: accretion without a convergence gate

The swarm applied its (good) pattern with **no domain-novelty criterion**. Head
stages introduce *new invariant kinds* that bind new effects; tail stages only
lengthen the reference chain — O(n) `X_receipt must reference Y_receipt`
assertions around acknowledgements-of-acknowledgements that bind no new effect.

## The audit (85 stages, one crisp test)

Test: *does the stage introduce ≥1 invariant that binds a NEW external effect
(budget/provider/retrieval/graph/artifact/notification/billing/persistence/worker-lease),
or is every invariant reference-chain plumbing over prior receipts?*

- **28 KEEP** (bind a distinct real effect) / **57 CLOSE** (reference-chain-only).
- **Convergence stage:** `MidnightOilOperatorArchiveHandoffPackagePlanRequest` —
  the last stage binding a new effect. Every stage after it is the self-similar
  `…DeliveryReport…Reconciliation/Attestation/Seal/Handoff` chain.
- **Anti-lazy catch (3 stages kept despite plumbing-flavored names):**
  `NotificationDeliveryApply` (real email delivery), `RetentionBillingReconciliation`
  (durable billing ledger write), `ArchiveHandoffPackage` (archive artifact
  produce/persist). A name-based pass would have wrongly dropped real billing +
  email effects.

## Scope reconciliation (2026-07-10)

A sibling's remedy **already closed the recursion tail** (#565–#699, closed
15:30–15:33Z) — independent convergent validation: the sibling's title-based
cleanup and this effect-binding audit agree on what is closeable. This record
therefore partitions only the **still-open** head.

## Authoritative partition of the OPEN Midnight Oil PRs

Diff-based (each `Add …plan` PR's diff introduces exactly one stage class, joined
to the audit verdict). Each plan PR `#n` has a paired `Wire … UI` PR `#n+1` that
inherits the same verdict.

**KEEP — bind a distinct real effect (belong in the distilled spine):**

| PR | stage / artifact | effect |
|----|------------------|--------|
| #484,#523,#524,#525,#526,#527 | preflight, budget-ceiling, launch_packet, approval_receipt, runner_handoff, applied_run_receipt | foundational two-phase-commit artifacts |
| #530 | DispatchRequest | dispatch / worker lease |
| #534 | BudgetReservation | budget reservation / spend |
| #536 | ProviderRoute | provider / LLM call |
| #538 | Retrieval | corpus / web retrieval |
| #540 | GraphMutation | substrate graph write |
| #542 | FinalArtifact | artifact produce / persist |
| #544 | LiveRunActivationSettings | live-run activation enablement |
| #549 | RunnerControlPlan | control-plane gate binding all side effects |
| #557 | GraphAdapter | durable retrieval-provenance (source-receipt) write |
| #563 | ControlLedgerAdapter | durable control-ledger / operator-enablement write |

**CLOSE — contract adds no new effect-guard (reference-chain-only):**

| PR | stage | note |
|----|-------|------|
| #551,#553,#555,#559,#561 | Budget/Provider/Retrieval/FinalArtifact/OperatorDispatch adapter plans | adapter *contracts* with no executor and reference-only invariants — add nothing without the executor code |
| #528 | DryRun | see nuance below |
| #532 | ActivationChecklist | see nuance below |
| #547 | RunnerReadiness | see nuance below |

**Two nuances (do not read CLOSE as "worthless"):**

1. **Adapter split is real.** `GraphAdapter` (#557) and `ControlLedgerAdapter`
   (#563) bind genuine durable writes → KEEP. The other five adapters
   (budget/provider/retrieval/final-artifact/operator-dispatch) are contract-only
   plumbing → CLOSE. Same "adapter" word, different substance — verified by
   invariant content, not name.
2. **DryRun / ActivationChecklist / RunnerReadiness are CLOSE at the *contract*
   level** (their invariants only re-assert the prior chain) but may carry
   operator-UX value as read-only preview/readiness surfaces. Recommendation:
   close the standalone contract PRs; if the preview/readiness UX is wanted, fold
   it into the distillation PR as a read-only view over the kept gates — not as a
   separate effect-free contract.

**KEEP ≠ merge-as-is.** All 16 keep-plan PRs (+ their UI pairs) mutate the same 7
files and mutually conflict. They should be **consolidated into one distilled
spine PR** (the 28 effect-binding stages), which supersedes them — not merged
individually.

**Separate (not in this partition):** #465 (research↔reading spine campaign,
sibling-owned, actively co-driven — do not touch), #438 (original umbrella),
#702/#706 (deterministic mock-swarm tooling — evaluate on its own merits).

## Recommended sequence

1. **Distill** the 28 effect-binding stages into one clean, green spine PR
   (supersedes the 16 keep-plan PRs + pairs).
2. **Close** the 8 contract-only plan PRs (#528, #532, #547, #551, #553, #555,
   #559, #561) + their UI pairs, referencing this record — **operator-ratified,
   not unilateral.**
3. **Cross-feed** the swarm's `source_policy entries must be unique` validator
   into #485 (closes the set-semantics finding from that PR's review).
4. **Add a swarm convergence gate:** before emitting stage N+1, require it to bind
   an effect not already bound by stages 1..N; constant validator-per-class
   density is a runnable detector for accretion-without-convergence.

## Reconsider-if

- If an executor implementation lands behind the five contract-only adapters,
  they move from CLOSE to KEEP (they would then bind real effects).
- If the operator wants the dry-run/checklist/readiness UX, those fold into the
  spine as read-only views rather than being reborn as standalone contracts.
