# Antiek Infrastructure Scalability Roadmap — 2026-08-12

**Status**: operator-brief response (v1). Author: Prime Agent forensic/sharpen session.
**Audience**: the operator ("I am connected to Hetzner now but I am completely
unknowledgeable of what it would take to scale my infra as I onboard people").
**Scope**: where Antiek runs today, what breaks at what user count, what the
sandbox question (Daytona) actually is, and the staged path to multi-tenant —
without violating master-spec §16 / §13.4 (no multi-user before Sprint 22;
single-writer DuckDB; substrate is the moat).

---

## 1. Where Antiek runs today (verified 2026-08-12)

- **One Hetzner VM** `antiek-prod-fsn1` (167.235.202.98, CX-style 4 vCPU / 15 GiB
  RAM / 150 GB disk, ~10% used) — Ubuntu 24.04, UFW 22-only, Cloudflare Tunnel
  ingress, Caddy → uvicorn (1 worker, DuckDB single-writer) + static SPA.
- **State**: single `antiek.duckdb` (~950 MB) + event log + state dir (1.1 GB).
- **Backups**: nightly EXPORT→R2 (v2 script with flock + verify gate, restored 2026-08-12).
- **Remote execution**: `runtime/remote_exec/` seam with `provider.py` protocol;
  Daytona adapter (`daytona.py`) and default-off Prime adapter (`prime_exec.py`);
  factory falls back to host-local when remote-exec is disabled/unavailable.

## 2. The honest capacity envelope of the current box

| Load | Behavior |
|---|---|
| Operator solo | Fine. 1 uvicorn worker, 15 GiB RAM, DuckDB single-writer. |
| ~5–25 concurrent light users | Fine if research runs stay serialized through the single writer; CPU becomes the first constraint (research fan-out is CPU-heavy: pdf/OCR/embedding). |
| >25–100 concurrent users | Needs worker processes or a job queue; DuckDB single-writer serializes writes (the documented invariant — §16). Read path can scale (secondary indexes), write path cannot. |
| ~100–500 users | Master-spec §13.6 Stage 0→1 threshold: per-user DuckDB files + DuckLake catalog + Postgres catalog. This is a *designed migration*, not a config flip. |
| >1,000–5,000 | Stage 1→2: DuckLake + per-user files; encrypted at rest per graph. |
| >5,000 | Stage 3: Postgres sharded by user_id (Notion pattern); DuckDB analytics-only. |

**Rule (from §13.6):** do not re-architect before ~100–500 concurrent users with
non-trivial write rates. The operator is at 1 user. The correct move is to build
the *seams* now (owner_user_id on every row; retrieval adapter seam; remote-exec
provider seam — all already in place) and the *scale* later.

## 3. "Do the agents need CPUs / sandboxes like Daytona?" — the actual question

Two different workloads get conflated:

1. **Inference** (LLM calls) — already remote (BYOT providers). No infra.
2. **Tool execution** (Python analysis, DuckDB queries, PDF/OCR, web fetch,
   Processing sketches, data-vendor pulls) — runs on the host today.

For the operator solo: the host is fine (4 vCPU is enough for one user's runs).
For onboarding users: you do NOT need to buy sandboxes per user. What you need:

- **Isolation for untrusted content** (scraped HTML, PDFs, uploaded files) —
  the Daytona spec's admission criteria (docs/daytona_integration_spec.md,
  WP-A3 failure class, untrusted-content isolation, tool-execution target).
- **CPU headroom for research fan-out** — either bigger VMs (vertical) or a
  job-worker fleet (horizontal) once queued runs exist.

**Verdict: keep the Daytona-style remote-exec seam (already built), enable it
per-workload, not per-user.** The `runtime/remote_exec` provider seam means the
Daytona adapter can be swapped for Modal/Fly machines/EC2 without code changes.

## 4. The staged plan

### Stage 0 (now, operator solo — already true)
- Single Hetzner VM; remote-exec disabled (host-local runs); BYOT providers;
  nightly R2 backups; Cloudflare edge.

### Stage 0.5 (first friends — <10 users, next weeks)
- Ship the multi-user auth + per-user row scoping that main already carries
  (`owner_user_id` on rows; account memory; passkeys). Keep ONE DuckDB with
  per-user scoping (master-spec §13.1 permits this for the first cohort).
- Add a **job queue** (Postgres + worker processes, or keep the single-writer
  with a serialized executor) before any heavy fan-out lands.
- **Enable Daytona (or Modal) for untrusted-content ingestion only** — the
  highest-risk surface (uploads → anydoc → HTML). The remote-exec seam exists;
  wire `ANTIEK_REMOTE_EXEC_ENABLED=1` + Daytona API key, scoped to
  acquisition/ingest workflows.
- **Vertical CPU headroom**: the current box has 4 vCPU; at <10 users, 8 vCPU /
  32 GiB Hetzner (CCX33-class, ~€40-60/mo) is the cheapest correct answer.
  Re-evaluate at >10 users.

### Stage 1 (Sprint 18–22 per master spec — ~100–500 users)
- DuckDB-per-user + DuckLake shared substrate + Postgres catalog (§13.2/§13.6).
- Per-graph encryption keys (KMS), DP plumbing (§13.3/§13.10).
- Turbopuffer wedge 1 (hybrid search) with sharding configured at first write
  (see docs/specs/turbopuffer-sharding-2026-08-12.md).
- Publisher/creator payouts infra (Stripe Connect).

### Stage 2+ (Sprint 22+)
- Two-graph architecture (personal + collective + shared substrate);
  cross-user federation; Daytona/Modal fleets for research fan-out; Postgres
  sharded by user_id.

## 5. Answers to the operator's literal questions

1. **"Do I need to build the agents in sandboxes like Daytona?"**
   Not for the agent *core* — the substrate is host-owned state (single-writer
   DuckDB; a remote sandbox cannot hold the flock — Daytona spec §2). Sandboxes
   are for *untrusted tool execution and content ingestion*. The seam is built;
   enabling it is a config + API key, workload-scoped.
2. **"Can I just run the agents locally on my CPUs and download files?"**
   Yes — that is the current design (host-local runner). It is not scalable,
   which is why the remote-exec seam exists. The seam is the answer; it is
   already provider-swappable (Daytona today, Modal/Fly/EC2 later).
3. **"What does it take to scale as I onboard people?"**
   (a) user scoping in the schema (done), (b) auth (done — passkeys + magic
   link + account memory), (c) a job queue before fan-out, (d) vertical VM
   growth first (<10 users), (e) the designed Stage 0→1 migration at
   100–500 users (§13.6), (f) backups + monitoring before each step (backup
   pipeline restored 2026-08-12; health probe + alerting still need fixing).
4. **"Is there a whitelabel marketplace?"**
   Covered in docs/specs/publisher-ecosystem-2026-08-12.md — v1 answer:
   Stripe Checkout self-hosted on antiek.ai/store (0 platform fee beyond
   Stripe 2.9%+$0.30); Payhip Pro / Lemon Squeezy when volume justifies.

## 6. Immediate infra actions (ranked, operator-decision)

1. Fix `antiek-health-probe` (dead since May 18) and the alert webhook
   (dead webhook.site) — monitoring precedes onboarding.
2. Apply the 17 pending apt updates + reboot (kernel since Aug 6).
3. Install fail2ban before exposing anything beyond port 22.
4. Wire Daytona/Modal only for untrusted-content ingestion when the first
   non-operator user appears.
5. Keep the canonical `~/Antiek/platform` deploy-source hazard fixed before
   the next deploy (templates must come from main, not the stale tree).
