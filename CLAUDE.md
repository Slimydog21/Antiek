# Antiek — agent onboarding

**You're picking up this codebase cold. Read this file before anything else.**

## What Antiek is

A research workstation + creation surface + interview-as-acquisition product
unified on one substrate. The canonical spec is `docs/master-product-spec.md`
(~3,000 lines). The substrate is DuckDB + typed event log; voice/style
discipline (§5) is non-negotiable; the IP-attribution + ad-economics
mechanism (§9) is the strategically consequential layer.

## Read these in order

1. **`docs/operator_gate_actions.md`** — current status of the 8 binding
   gates blocking activation. Updated 2026-05-23. The "Operator Activities"
   section at the bottom is the cross-session breadcrumb.
2. **`docs/agent-execution/HARD_TO_VARY.md`** — mandatory for all agent
   sessions before diagnosing Research/cascade bugs or claiming verification.
   Phase A→E protocol; forbidden patterns F1–F8.
3. **`docs/master-product-spec.md`** — the spec. §14 is the sprint
   sequence; §14.3 is the binding ordering discipline; §16 is the explicit
   REJECT list.
4. **`docs/sprint_track_reconciliation.md`** — explains the two parallel
   sprint sequences (master-spec 11→22 + UI-redesign 0→12).
5. **`docs/decisions/`** — one markdown per closed gate or binding
   decision. Quick browse here tells you what's been settled.

## Don't propose engineering until you read this

As of 2026-05-23 session-end, the **engineering scope of the spec is
essentially complete**. 2,703 tests passing. The bottleneck is operator
action on the 5 remaining gates. Before you suggest new engineering work:

- Check `docs/operator_gate_actions.md` "Operator Activities" section.
- Verify the bottleneck isn't already a known operator-bound item.
- If a real engineering gap exists, audit against the section
  `## Genuine remaining gaps, exhaustively` in the latest in-session
  audit (the v4 audit content lives in this README's git history;
  search for `phase2_execution_audit` files in `docs/`).

## Critical invariants — DO NOT VIOLATE

1. **DuckDB single-writer.** `--workers 1` on uvicorn, period. Per §16.
   The only-writer invariant is enforced at `runtime/db_lock.py` and the
   antiek.service systemd unit.
2. **Voice/style discipline.** Master-spec §5. Prose flows, no LLM-slop,
   no forced bullets, claim spans inline. Applies to prose AND UI.
3. **Substrate-as-source-of-truth.** Every claim cites chunks. Every chunk
   cites documents. Every document carries `ip_holder_id` (even null).
   Don't break the provenance chain.
4. **Sprint 18 legal gate.** Payouts gate strictly on retrieval-time
   gating in production + publisher opt-in. Per §9.0. Currently G1
   closed; G2 + G3 open. Don't propose money-routing changes that
   bypass.
5. **Single-operator until Sprint 22.** Compounding hasn't been
   demonstrated yet. Premature multi-user destroys the moat. G7 gates
   the multi-user pivot at ~Nov 2026 earliest.
6. **Single email provider.** Use what's configured in
   `ANTIEK_EMAIL_PROVIDER`. AgentMail is the current choice (per
   2026-05-23 verdict in `docs/operator_gate_actions.md`); custom-domain
   upgrade is deferred.

## What's running on prod

- `antiek.service` — FastAPI substrate at `https://api.antiek.ai`
- `antiek-continuous-research.service` — §7.3/§7.4 evidentiary-gap
  daemon (since 2026-05-23)
- Cloudflare Pages — frontend at `https://antiek.ai` (auto-builds from
  `main`)
- Cloudflare Tunnel — `api.antiek.ai` → Hetzner CCX23

Auth: magic-link via AgentMail. Per
`infrastructure/runbooks/magic-link-auth.md` and
`infrastructure/runbooks/agentmail-setup.md`.

## When you write code

- Tests live in `tests/`. Run `./.venv/bin/python -m pytest tests/ -q`.
- Frontend at `apps/reading/`. TS strict; run `npx tsc -b` to check.
- Don't add files to mainline branches; the operator's parallel-stream
  tooling commits in big batches, so collisions are common. Commit
  what's yours; let the parallel stream commit theirs.
- The §16 REJECT list is canonical: no Daytona/Modal/Pulumi/etc, no
  PostHog vendor tone, no ε > 10 on DP claims, no premature scaling.

<!-- BEGIN: s16-research-fanout-exemption (unified SPR-02; operator-ratified 2026-05-25) -->
- **§16 exemption — research fan-out only.** The operator ratified one
  scoped carve-out on 2026-05-25: *research-runner fan-out* (and only that)
  may execute on an external provider via `runtime/remote_exec/`, so a DRW
  cascade can run N sub-question researches genuinely concurrently off-host
  rather than capped at the host VM. Daytona is the one implementation
  behind the `RemoteExecProvider` interface. Everything else in the §16
  REJECT line above is **unchanged**: dispatch stays Hermes-primary (no
  Daytona/Modal/Prime as a dispatch provider for non-research inference);
  the DuckDB single-writer invariant is untouched (remote researches append
  only to their own per-investigation event logs — the serialized host
  funnel through `runtime/db_lock` remains the sole graph writer); ε > 10
  on DP claims and premature scaling stay rejected. Host-local
  (`HostLocalRunner`) is the automatic fallback when remote-exec is disabled
  or the provider is unavailable. Rationale + reconsider-if:
  `docs/decisions/s16-research-fanout-exemption.md`.
<!-- END: s16-research-fanout-exemption -->

<!-- BEGIN: agent-failure-regression (managed by SPR-E2 of antiek-hashimoto-engineering) -->
- **Agent-failure regression library.** Every observed agent failure
  (a production path that produced wrong/surprising output) gets a YAML
  fixture at `tests/regression/agent_failures/<slug>.yaml` BEFORE the
  fix lands. The fixture must fail (or be GAP-marked) until the
  mitigation ships. See `tests/regression/agent_failures/README.md`
  for the onboarding flow. Programmatic failure logging via
  `orchestration.agent_failure_log.record()` (JSONL append-only at
  `~/.antiek/agent_failures.jsonl`, daily rotation). Five fixtures
  currently in the library — all GAP-marked, documenting the Phase A
  loky-semaphore failure + four arxiv-ingestion failures + the
  Phase 8 SkillPatchGate's standing shadow-mode condition.
<!-- END: agent-failure-regression -->

<!-- BEGIN: craft-signature (managed by SPR-E7 of antiek-hashimoto-engineering) -->
- **Craft signature: inline-rubric latency.** `substrate.synthesis_rubric.scorer.score_synthesis`
  p95 must stay within 10% of the locked baseline (194.85 μs at git
  `640a31c`, 2026-05-24). CI fails on regression via
  `python -m benchmarks.rubric_latency --check-regression`. Every other
  perf dimension is explicitly "good enough" — see `docs/craft_signature.md`
  for the policy + the locked numbers. To re-mint the baseline after a
  deliberate perf change: `python -m benchmarks.rubric_latency --update-baseline`
  (operator-only; do not run in CI).
<!-- END: craft-signature -->

## What changed in the 2026-05-23 session

| Commit | What |
|---|---|
| `7450ef1` | Inline rubric scoring after Phase 6 — closes §14.4 gap |
| `13f4f2f` | Continuous-research daemon systemd + `__main__` |
| `38b13be` | Dispatch verdict self-grade fallback |
| `eeaf084` | TZ-aware window comparison in verdict |
| `bc4022e` | Verdict reads `emitted_at` + G4 closure note |
| `d7b9296` | Dispatch verdict + G5 follow-up documented |
| `417fa1f` | AgentMail custom-domain deferral |
| `00d5cac` | AgentMail provider |

Three gates closed (G1, G4, G5). Two services now running on prod
(`antiek`, `antiek-continuous-research`). 2,703 tests, 100% green.
