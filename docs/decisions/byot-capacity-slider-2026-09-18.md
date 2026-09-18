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
