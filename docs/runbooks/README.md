# Antiek runbooks — internals intuition at the seams

**Sprint:** SPR-07 (DDIA-execution) · **Anchor:** Philosophy P6
(internals intuition is mandatory at the seams; optional in the middle)

Read the runbook that matches the symptom you're seeing. Each runbook
follows the same shape (Symptom · Likely cause · Quick diagnostics ·
Root-cause path · Mitigation · Reference) so a panicked engineer can
scan quickly.

Runbooks live next to the code they explain. They are checked into git
because they survive refactors and rot with audit-able timestamps; code
comments rot silently. The staleness policy (Owner + Last verified
at the top of each file) lets a future operator see what's overdue.

## Symptom index

| Symptom | Open |
|---|---|
| Concurrent DuckDB writes hang / WriteLockTimeout fires unexpectedly | [db_lock_contention.md](db_lock_contention.md) |
| `is_locked()` reports a lock that's no longer there | [db_lock_contention.md](db_lock_contention.md) |
| `Catalog Error: Table with name write_log does not exist` in stderr | [duckdb_checkpoint_wal.md](duckdb_checkpoint_wal.md) |
| Dispatch verify-tier fallback didn't fire when primary went down | [dispatch_fallback_chain.md](dispatch_fallback_chain.md) |
| Hermes bridge returned 503 → dispatch raised non-retryable error | [dispatch_fallback_chain.md](dispatch_fallback_chain.md) |
| Anthropic returned `cache_read_input_tokens` but burn report shows zero cached | [provider_usage_normalization.md](provider_usage_normalization.md) |
| `prompt_tokens_details.cached_tokens` ignored in OpenAI-compat usage | [provider_usage_normalization.md](provider_usage_normalization.md) |
| Embedding queries are slow or wrong (cosine sim looks off) | [embedding_pipeline.md](embedding_pipeline.md) |
| Some chunks have `embedding IS NULL` after ingest | [embedding_pipeline.md](embedding_pipeline.md) |
| Event log diverges from DuckDB-derived graph state | [event_log_replay.md](event_log_replay.md) |
| Graph state looks stale; events.jsonl has rows that didn't materialize | [event_log_replay.md](event_log_replay.md) |
| Continuous-research daemon stuck; antiek-continuous-research.service won't progress | [continuous_research_daemon.md](continuous_research_daemon.md) |
| Cloudflare Tunnel → api.antiek.ai returns 502 / 526 / 530 | [cloudflare_tunnel.md](cloudflare_tunnel.md) |
| `cf-tunnel-error` in logs, intermittent connectivity from frontend | [cloudflare_tunnel.md](cloudflare_tunnel.md) |
| Magic-link email arrives but token validation fails | [magic_link_auth.md](magic_link_auth.md) |
| Login click → 401; the token query param looked fine | [magic_link_auth.md](magic_link_auth.md) |

## What's NOT in a runbook (and why)

The boundary between "runbook this" and "don't runbook" matches P6:

- **TLS termination at Cloudflare.** The abstraction is solid;
  engineers do not need to learn handshake internals.
- **Python `json` module internals.** Stdlib JSON behavior is
  well-understood; runbook would be filler.
- **DuckDB's parquet reader internals above the storage engine.**
  Antiek doesn't tune parquet reads; the abstraction holds.

If a future symptom appears that would need one of the above, expand
the runbook set — but only with operator review per P6.

## Staleness policy

Every runbook has an `Owner` and `Last verified` line at the top. The
policy:

- **0–6 months:** trusted. No action needed.
- **6–12 months:** banner the file with a "verify" callout; the next
  engineer who lands changes nearby is expected to confirm.
- **12+ months:** trigger an audit (operator action). The runbook
  may still be correct, but the failure modes have likely shifted.

Today the policy is documentary, not enforced. A future
`scripts/check_runbook_staleness.py` could surface stale runbooks via
the operator dashboard.

## Adding a runbook

A new seam justifies a new runbook when:

1. Engineers (or agents) have hit a pathological behavior at that
   seam more than once.
2. The fix requires internals knowledge the surrounding code does not
   make obvious.
3. The vendor (or upstream) documentation is incomplete, contradictory,
   or paywalled.

Use `_template.md` as the skeleton. Cross-reference from the symptom
index above.
