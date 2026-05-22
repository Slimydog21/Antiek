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
| 3 | Curated news | NYT, WSJ, FT, Bloomberg, Reuters, Economist, Atlantic, New Yorker, WaPo, AP. Edit `CURATED_NEWS_TIER_3` in `substrate/constants.py` (substrate-level decision per spec §6.6). |
| 4 | General web | Default for everything else. |

No automatic learning of "what's a good source." Tier assignments are substrate decisions, not search-API decisions.

## Provider-specific payload bag (`provider_specific`)

Per spec §14.7 (and the Deviation B closure on 2026-05-22), Exa-shaped data on a `DiscoveryProposedPayload` lives under the `provider_specific: dict[str, Any]` overflow bag, NOT as top-level payload fields. The top-level fields (`url`, `title`, `query`, `relevance_score`, `suggested_tier`, etc.) stay **provider-agnostic** — adding a new provider (SerpAPI, Tavily, Perplexity) doesn't bump the schema.

Current usage (Exa is the only provider in Wedge 1):

```python
# Operator-facing DiscoveryProposed dataclass — both surfaces available
p.provider_response_id          # convenience top-level mirror
p.provider_specific["response_id"]  # canonical write location
```

What goes in `provider_specific`:

- `response_id` — Exa's per-result id (the canonical write target).
- Future Exa-specific data — `autoprompt_string`, `subpages`, `exa_filter`, etc. join here as the adapter learns to pass them through.

**Backward-compat read order** (used by `_hydrate_proposed` for cached rows):

1. `provider_specific["response_id"]` if present (canonical, new emitters).
2. Top-level `provider_response_id` as fallback (v6-v8 events).
3. `None` if neither.

The `provider_response_id` top-level field on the payload is now an Optional-None default for new emissions — kept on the schema for v6-v8 read compatibility.

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
- Does NOT learn the curated news list. Operator edits `substrate.constants.CURATED_NEWS_TIER_3` directly.
- Does NOT support multi-provider fan-out (one Exa-only adapter today). Spec §17.5 defers this until a second provider lands.

## Retention CLI (`retention rollup` / `retention summary`)

Per spec §14.1, discovery events older than 30 days roll up into the `discovery_summary` DuckDB table; the source JSONL files are then truncated. Operator surfaces:

```
# Read-only preview — what would be rolled up at the current retention threshold
python -m acquisition.search.exa retention rollup --dry-run

# Real rollup — writes to discovery_summary, truncates source JSONL
python -m acquisition.search.exa retention rollup [--retention-days 30]

# Inspect the recent summary rows
python -m acquisition.search.exa retention summary [--days 7] [--json]
```

The rollup is conservative — files containing even one event newer than the cutoff are kept whole. Idempotent via `ON CONFLICT DO UPDATE` so re-running against the same window doesn't double-count.

## Testing

```
python -m pytest tests/test_acquisition_search_exa.py -q
```

Tests cover: legal-gate placeholder acknowledgment, tier heuristic, ExaClient retry / error handling against `httpx.MockTransport`, discover happy path / budget reservation / budget exceeded / budget override, promote_discovery (ingested / rejected_by_legal_gate / fetch_failed / tier override), reject_discovery, find_similar, discovery_id stability + cross-query distinction (Deviation A).

End-to-end integration test for spec §6.10 (discover → promote → real ingest_url → real DuckDB writes, with idempotent re-run via url_alias short-circuit): see `tests/test_exa_full_flow_integration.py`.

Cache, weekly-report, legal-gate, Wedge 2, Wedge 3 primitive, CLIs, spec gaps, spec deviations: see the corresponding `tests/test_acquisition_search_exa_*.py`, `tests/test_acquisition_urls_browserbase.py`, `tests/test_legal_gate.py`, `tests/test_clis_exa_and_legal_gate.py`, `tests/test_spec_gaps.py`, `tests/test_spec_deviations.py`.
