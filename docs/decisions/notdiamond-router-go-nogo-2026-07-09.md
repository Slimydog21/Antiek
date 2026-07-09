# NotDiamond-as-router — go/no-go (2026-07-09)

**Verdict: CONDITIONAL GO (advisory wedge only) — NO-GO as authoritative dispatch router.**

**Checked against:** `origin/main@c4d93c1119f66302fbcf0046ce5aa46a33ecd91c`  
**Branch evidence:** `notdiamond/integration` (2 commits: `f1f98a2d` SPR-01 adapter, `bf12fa3d` SPR-02 nd_* schema v28)  
**Staleness:** ~244 commits behind `origin/main` at check time — rebase required before land.  
**integrations.toml:** `[notdiamond]` remains **Tier 0** (spec only; no production import on main).

## Evidence (machine-checked)

| Claim | Evidence |
|---|---|
| No NotDiamond runtime on main | `rg -n notdiamond --type py` on `origin/main` → only `integrations.toml` tier-0 entry; no `runtime/notdiamond/` |
| Wave-1 exists off-main | `notdiamond/integration` adds `runtime/notdiamond/{adapter,types,__init__}.py`, `substrate/dispatch/nd_attribution.py`, event schema `nd_*` fields, tests |
| Spec posture | `~/specs/antiek-notdiamond/` — 8 sprints / 4 waves; advisory-only; never authoritative; off §16.1 REJECT list for custom ND as sole dispatch |
| Existing dispatch | `substrate/dispatch/config.yaml` + router already own role→provider routing (GLM-5.2 footprint live); verify-tier fallback owns failure |
| Hatch | `ant-nd-wave1` status wave1-GREEN on integration branch; operator PR pending; Waves 2–4 dep-blocked on DRW SPR-02 |

## Decision

### GO — implement/land Wave-1 advisory wedge (after rebase)

**Why useful:**
1. **Measured recommendation layer** without displacing Antiek’s hard-won dispatch single-writer + latency locks.
2. **Attribution schema (`nd_*`)** makes “would ND have picked differently?” auditable against real role calls — the only way to know if ND beats the §14.4 baseline later.
3. **Matches operator ask** for model quality per task *as evidence*, not as a silent router swap.

**Conditions (non-negotiable):**
- Advisory only: ND recommends; `substrate.dispatch` decides.
- No production import until `integrations.toml` voucher + tier promotion after land + dogfood.
- Rebase `notdiamond/integration` onto current main (schema version drift: wave used EVENT_SCHEMA_VERSION 27→28; main has moved further — re-derive version bump).
- Zero callers of `record_nd_decision` required at land (staging ContextVar is fine).
- Latency lock on synthesis path must remain structurally untouched (wave1 claim: 194.85µs lock preserved — re-measure post-rebase).

### NO-GO — NotDiamond as *the* router / custom trained ND / authoritative model selection

**Why not:**
1. **§14.4 / master-spec baseline** is the in-house dispatch config + verify-tier fallback. Promoting ND past advisory without beating that baseline is explicitly out of scope for residual infinite cycles.
2. **Operator model footprint is already explicit** (GLM-5.2 / DeepSeek / MiMo direct endpoints). An external multi-model router fights the current “known footprint” ops model until Antiek-bench has weekly task evidence.
3. **Antiek-bench is unshipped** — without recursive task benchmarks from real usage, ND routing quality is unmeasured theater.
4. **Spend + key surface**: ND as hot-path router adds vendor lock + failure mode for every role call; advisory shadow avoids that.

## Spec delta (only because GO for advisory)

No new htmlspec required for Wave-1 — existing `~/specs/antiek-notdiamond/` is implement-ready for SPR-01+02. Required execution notes for the next agent:

1. Rebase `notdiamond/integration` → fresh PR to main (operator merge).
2. Re-resolve `EVENT_SCHEMA_VERSION` against main tip; keep `nd_*` fields nullable.
3. Do **not** start Wave-2 (advisory routing in DRW) until: Wave-1 on main + Antiek-bench v0 task labels exist + shadow comparison harness green.
4. Antiek-bench (separate residual) should emit per-role outcome labels that ND shadow can score against.

## Relation to this cycle’s code residual

This cycle ships **model budget projection + decision-tree math** (`substrate.research_workstation.model_budget`) so the UI can show usage-vs-limit and prompt cost projection **without** ND. That substrate is complementary: budget honesty is load-bearing even when the driver model is manually selected.

## One-line summary

**Use NotDiamond as an optional advisory measurement wedge (land Wave-1 after rebase); do not make it the authoritative router until Antiek-bench + shadow metrics beat the in-house baseline.**
