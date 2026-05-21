# `acquisition/search/exa/` — Wedge 1 of the Exa & Browserbase integration

**Spec**: [`docs/integration_exa_browserbase.md`](../../../docs/integration_exa_browserbase.md) §6.
**Status**: shipped Sprint 17 against a placeholder legal gate. The real Sprint 18 gate must land before any non-operator user can exercise this surface.

## What this module does

Discovery layer — proposes URLs from Exa's neural search index. **Does not write to the graph.** Promotion to ingestion is operator-mediated and routes through `acquisition/urls/adapter.ingest_url`.

```
discover(query, investigation_id)            ← Exa /search → typed DiscoveryProposed list + events
find_similar(url, investigation_id)          ← Exa /findSimilar → same shape
promote_discovery(proposal, investigation_id) ← legal_gate → ingest_url → DiscoverySelected event
reject_discovery(proposal, investigation_id)  ← operator-side dismissal
```

## Environment

| Variable | Required | Default | Notes |
|---|---|---|---|
| `EXA_API_KEY` | yes | — | Never aliased to other services' keys; silent misrouting is worse than loud failure. |
| `EXA_BASE_URL` | no | `https://api.exa.ai` | Override for staging / mock servers. |
| `EXA_DAILY_BUDGET_USD` | no | `5.0` | Hard-stop cap. Triggers `DiscoveryBudgetExceeded`; no silent fallback. |
| `ANTIEK_LEGAL_GATE_PLACEHOLDER_ACKED` | **yes**, until Sprint 18 | unset | Without this set to `1`, `default_legal_gate()` raises. The placeholder allows every URL; acknowledging it is the operator's affirmative consent that the real Sprint 18 registry has not yet shipped. |
| `ANTIEK_DUCKDB_PATH` | no | `~/.antiek/graph.duckdb` | Substrate DB. The 24h discovery cache lives here. |
| `ANTIEK_HOME` | no | `~/.antiek` | Budget sidecars live under `<ANTIEK_HOME>/budgets/`. |

## Legal-gate sequencing caveat

The spec at §6.9 binds: *"Wedge 1 cannot ship before the Sprint 18 retrieval-time legal gate is in production."*

This module ships **before** Sprint 18 against a `PermissiveLegalGate` placeholder at `substrate/legal_gate/`. The architectural seam is correct — every `promote_discovery(...)` call routes through `legal_gate.check_url(...)` — but the placeholder allows every URL. Sprint 18 replaces the placeholder with `SqlWhereLegalGate` consulting the Bartz / Hachette / AG MDL banned-corpus registry; callers don't change.

Until the real gate lands, **don't promote URLs from banned-corpus domains.** The acknowledgment flag (`ANTIEK_LEGAL_GATE_PLACEHOLDER_ACKED=1`) is your affirmative consent that you understand this.

## Source-tier suggestion

`suggest_tier(url, category=...)` heuristic, per spec §6.6:

| Tier | Source class | Examples |
|---|---|---|
| 1 | Primary | NEVER auto-assigned. Operator-only via `source_tier=1` override. |
| 2 | Research | arXiv, `*.gov`, `*.edu`, `*.ac.uk`, doi.org, ssrn.com, biorxiv.org. Also `category="research paper"`. |
| 3 | Curated news | NYT, WSJ, FT, Bloomberg, Reuters, Economist, Atlantic, New Yorker, WaPo, AP. Edit `_CURATED_NEWS_TIER_3` in `adapter.py` directly. |
| 4 | General web | Default for everything else. |

No automatic learning of "what's a good source." Tier assignments are substrate decisions, not search-API decisions.

## 24h cache (`discovery_cache` table)

Per spec §6.5. Same `(query, investigation_id, num_results, category, include_domains, exclude_domains, start/end_published_date)` tuple within 24h short-circuits to the cached proposals. **No event re-emission on a cache hit** — the audit trail recorded what was considered on the first call.

- Tunable per-call: `discover(..., use_cache=False, cache_ttl_seconds=N)`.
- The cache fails open: a missing substrate DB falls through to a live Exa call.
- Manual purge: `python -c "from acquisition.search.exa.cache import purge_expired; from substrate.graph import default_db_path; print(purge_expired(db_path=default_db_path()))"`.

## Cost discipline

Per-call cost is recorded in two places:

1. **`DiscoveryProposedPayload.cost_usd_estimate`** — into the event log for trajectory audit.
2. **`~/.antiek/budgets/exa_<utc-date>.json`** — daily roll-up sidecar consumed by `runtime/weekly_report.py` (§7 "Acquisition cost (discovery layer)" section).

Cost estimates are back-of-envelope (~$0.005/search, ~$0.001/findSimilar at 2026-Q1 pricing). Exa's invoiced cost is authoritative. **Re-verify pricing quarterly.**

## Budget cap

`EXA_DAILY_BUDGET_USD` (default $5) hard-stops on the next call after the threshold. `discover(...)` raises `DiscoveryBudgetExceeded`. Per-call override:

```python
discover(..., daily_budget_usd=20.0)  # operator decision to exceed today's cap
```

There is no silent fallback to a different provider. The operator sees the failure and explicitly relaxes the cap if intended.

## What this module deliberately does NOT do

- Does NOT call Exa's `/contents`. That's Wedge 3 (PHASE 2).
- Does NOT call Exa's `/answer`. That endpoint is REJECTED per spec §12.5 (collapses the trajectory).
- Does NOT auto-ingest. Every promotion is operator-mediated via `promote_discovery(...)`.
- Does NOT bypass the legal gate. The placeholder allows everything; the real Sprint 18 gate refuses.
- Does NOT learn the curated news list. Operator edits `_CURATED_NEWS_TIER_3` directly.
- Does NOT support multi-provider fan-out (one Exa-only adapter today). Spec §17.5 defers this until a second provider lands.

## Testing

```
python -m pytest tests/test_acquisition_search_exa.py -q
```

39 tests cover: legal-gate placeholder acknowledgment, tier heuristic (15 cases), ExaClient retry / error handling against `httpx.MockTransport`, discover happy path / budget reservation / budget exceeded / budget override, promote_discovery (ingested / rejected_by_legal_gate / fetch_failed / tier override), reject_discovery, find_similar, discovery_id stability.

Cache + weekly-report integration: see `tests/test_acquisition_search_exa_cache.py` and `tests/test_weekly_report_acquisition_section.py`.
