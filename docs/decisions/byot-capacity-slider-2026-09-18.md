# Decision — BYOT capacity slider (Antiek-hosted agent compute)

**Date:** 2026-09-18 (Asia/Riyadh)
**Status:** DECISION + MVP shipped (schema + API + Settings panel). Enforcement soft/hard flag-gated; **no fake billing**.

## Doctrine (locked)

| Concern | Owner | Surface |
|---|---|---|
| **BYO Token** | User API keys / OAuth | Settings → Usage / BYOT ledger |
| **BYO Tools** | User connectors | Settings → Tools |
| **Agent compute (CPU)** | **Antiek-managed** | Settings → Agent compute capacity |
| **BYO CPU** | Optional power-user later | BYOC specs — **not** default |

Vision map pillar 3: monthly capacity slider + predictable bill; Antiek keeps research traces. **NO BYO CPU** as the default product path.

## MVP shape

- DuckDB SoT: \`owner_compute_capacity\` (tier, monthly ACU, used_status).
- \`GET/PUT /settings/compute-capacity\` — owner-scoped.
- Presets: starter=100, standard=500, power=2000 ACU/month; custom slider 0–10000 (store max 50000).
- \`used_status=unmetered\` until a real meter exists — UI must not invent spend.
- \`ANTIEK_COMPUTE_CAPACITY_ENFORCEMENT=off|soft|hard\` (default off). Hard does not yet block research start; evaluate() records \`would_hard_block\` for the next gate PR.

## Explicit non-goals

- No Stripe / invoice in this PR.
- No conflating ACU with BYOT token cents.
- No enabling BYO CPU / Daytona per-user by default.

## Next

Wire soft warn + hard refuse at investigation start when meter exists; map ACU → monthly price once legal/pricing Rank 0.1 lands.

## ACU meter (2026-09-18 follow-on)

**Heuristic (honest, not fake pricing):**

> **1 ACU = one investigation start**  
> (`POST /investigations` or `POST /books/{id}/spin-research`)

**Why not dispatch latency / role-call counts yet?** Those signals exist on
`dispatch.call` (`latency_ms`) but arrive *after* work begins and mix BYO Token
provider time with host CPU. The pre-commit soft-warn / hard-refuse gate needs a
decidable unit *before* the orchestrator spawns. Flat 1 ACU at start meters the
Antiek-hosted commit (orchestration, DuckDB writer, retrieval, event log).
Wall-time top-up on completion is a later refinement.

**Ledger:** `owner_compute_acu_ledger` keyed by `investigation_id` (idempotent
replays). `owner_compute_capacity.used_status` flips to `known`.

**Enforcement:**
- `off` — meter still records; no warn / refuse
- `soft` — warn body + `X-Antiek-Capacity-Warn` at ≥80% or over; never refuse
- `hard` — `429 compute_capacity_exhausted` when used ≥ monthly before start

BYO Token spend remains Settings → Usage. No dollars on ACU in this PR.
