# The usability keystone — an executable definition of "usable"

**Date:** 2026-06-04
**Status:** INSTALLED (the probe IS the definition) + verify-live WIRED + live run OPERATOR-GATED
**Owner:** Antiek — Convergence SPR-08 (end-to-end usability keystone, the capstone)
**Surfaces:**
`tools/reachability/probes/usability_keystone.py` (the probe — the executable
embodiment of this definition);
`tools/reachability/probe_runner.py` (the `Probe.headline` field + headline-first
sort — the keystone is the top-line verdict);
`tests/test_usability_keystone.py` (the named-failing-leg self-test, 5 legs);
`infrastructure/ansible/playbooks/deploy.yml` (the REQUIRED verify-live task,
post-`/health`/-frontend) + `infrastructure/ansible/group_vars/all.yml`
(`antiek_keystone_verify_live`, default false — operator-gated);
`infrastructure/runbooks/usability-keystone-verify-live.md` (the live-run
checklist + credentials + rollback).
**Builds on (composes, does not duplicate):** `flywheel.py`, `compounding.py`,
`read.py`, `retrieval_gate.py` (the per-leg probes); the auth middleware
(`interfaces/research/api/app.py:1315-1340`, the bearer path, verified by
`secrets.compare_digest`); the §9 attribution shape
(`interfaces/research/api/app.py:266-312` ChunkResponse + `:2155-2257` the route;
`substrate/graph/schema.py:376-396` `ip_holders`, `:415-416` `documents.content_class`
+ `ip_holder_id`, `:89` `chunks.document_id`); the canonical launch entrypoint
(`interfaces/research/api/cascade_routes.py:577-583` approve, `:591-638` launch).

---

## The operational definition (VERBATIM — this is the Jobs-bar)

> **The product is usable iff a fresh test operator completes login → start a
> research → the research compounds (knowledge_reuse_count > 0) → read the result
> with §9 attribution intact, exercised end-to-end through the real `create_app()`
> factory and again post-deploy against real prod.**

`tools/reachability/probes/usability_keystone.py` **is** the executable embodiment
of that sentence. It is not a description of the bar — it is the bar, runnable. A
maintainer who wants to know what "usable" means runs the probe.

> **One honesty caveat on "read the result":** today the read leg reads a
> **seeded §9-attributed source document**, not this journey's own research output,
> because the launched cascade deposits *insights* (not §9-readable chunks) — there
> is no chunk of this journey's own product to read back yet. The read door and the
> §9 attribution shape are genuinely exercised; the read-back of *this journey's
> own* output is not. See **caveat 3** below; this is disclosed, not overclaimed.

---

## The five legs + their assertions

The keystone is the **CONJUNCTION** of five legs, each a distinct observable
OUTCOME, driven as ONE journey through the bare production factory. Stages run **in
order** and stop at the first failure; the runner prints exactly which leg failed
(e.g. `[BLOCKED] usability_keystone: compound — knowledge_reuse_count == 0 …`).

| # | Leg | Assertion (an OUTCOME, never a parameter/mock) | Source |
|---|---|---|---|
| 1 | **login** | A protected route returns **401 without** the bearer header and **200 with** it; the 401 carries `operator_auth_required`. The authenticated client is carried through every later leg. | `app.py:1315-1340` (bearer path, `secrets.compare_digest`) |
| 2 | **launch** | A research started via the canonical entrypoint (`POST /research/plans` → `/approve` → `/launch`), **authenticated**, polled to a **terminal** state within a bounded poll (reported as a `launch` finding if not — never a silent pass). **In-process:** poll the per-leaf event log to `investigation.completed`. **Live:** poll `GET /research/sessions/{session_id}` until every research's RunState is terminal (`done`/`stopped`/`failed`/`budget_halted`), and red a non-`done` terminal. | `cascade_routes.py:577-583, 591-638, 666` (status route); `events.py:83`; `protocol.py:55-56` (terminal RunStates) |
| 3 | **compound** | `knowledge_reuse_count > 0` from **this** investigation's per-investigation `knowledge.reused` event, **not** a global `/health` counter. **In-process:** `action_counts` scoped to the leaf iid on the temp events dir. **Live:** count `knowledge.reused` events from `GET /trajectory/{leaf}` for **this** leaf (the same per-investigation signal, over HTTP — **not** the frozen-at-boot `/health` global snapshot). | `events.py:180` `KNOWLEDGE_REUSED`; `host_local.py` (emit site); `app.py:1751` (`/trajectory`) |
| 4 | **read** | A real artifact comes back through `GET /chunks/{id}` — a real authenticated HTTP fetch through the production read surface; `document_id` + `chunk_id` resolve. **The artifact read is a SEEDED §9-attributed source document, NOT this journey's own research output** (see caveat 4 below). | `app.py:2155-2257` |
| 5 | **attribution** | On that same artifact: well-formed §9 attribution — `ip_holder_name`/`ip_holder_status` present on a servable source; `servable`/`servability` a well-formed pair (servable ⇒ servability null; withheld ⇒ a known label AND owner withheld with the body). **Metadata PRESENCE only — graph-only; no serving / payout is activated.** | `app.py:266-312, 2238-2257`; `schema.py:376-396, 415-416` |

REACHABLE only when **all five** hold. The probe boots via the bare
`create_app()` factory — **NO** `retrieval_substrate=` injection, **NO**
`register_providers=False`, **NO** stubbed providers (grep the probe + the AST
self-test prove it). That injection is the exact blind spot the compounding
benchmark had (`compounding/benchmark/harness.py:344` injects the substrate prod
never injects) and is the disease this whole gate exists to kill.

---

## STEELMAN: "a `/health`-only smoke test would have been enough"

The strongest version of the objection: *prod already has a post-deploy `/health`
assertion (`deploy.yml`) that checks the service is up, providers are registered,
and (when re-armed) the flywheel is live. `/health` is one cheap GET; the keystone
is five legs and a real research launch. Why pay for the keystone when a richer
`/health` field — say, `journey_ok: true` — would carry the same signal at a
fraction of the cost? Smoke tests that boot the whole journey are flaky, slow, and
duplicate coverage the per-brick probes already give.*

**Answer — from this codebase's own history, not from principle.** The flywheel
**shipped DEAD in prod while `/health` and every brick were green.** `/health`
reported `knowledge_reuse_count=0` on live prod (the cascade built the runner with
`retrieval_substrate=None`) while every unit test, every contract test, and the
compounding benchmark all passed — the benchmark passed *because* its harness
injected the substrate prod never injected. A `/health` read alone:

1. **misses three legs entirely.** `/health` does not exercise **login** (auth
   enforcement), **read** (the chunk HTTP surface), or **attribution** (§9 shape).
   A product where login is broken, or the reader returns nothing, or attribution
   is malformed, is **not usable** — and `/health` is silent on all three.
2. **a global count can be true while THIS user's research compounded nothing.**
   `knowledge_reuse_count` on `/health` is a process-global counter mutated by
   every run on the box. It can read `> 0` from yesterday's activity while the
   research **this** journey just launched reused nothing. The keystone asserts the
   *user's own* investigation's per-investigation `knowledge.reused` event — the
   only signal that means "the journey compounded."
3. **a `journey_ok` field would just move the lie inside `/health`.** For `/health`
   to honestly report `journey_ok`, *something* must drive login → launch →
   compound → read → attribution and observe each outcome. That something is the
   keystone. Folding it into `/health` does not remove the work; it hides the
   five-leg conjunction behind a boolean a future refactor can quietly stub —
   re-creating the exact "green field, dead feature" failure. Keeping the keystone
   a standalone, source-visible probe that *names the failing leg* is what makes
   the lie impossible.

The objection is right that the keystone is more expensive than a GET. It is wrong
that the signals are equivalent: the dead-flywheel incident is the existence proof
that a green `/health` and green bricks coexist with a broken journey. The keystone
is the cheapest thing that **could have caught it**, because it is the only gate
that asserts the conjunction the user actually lives.

---

## Caveats — each a NAMED closest-real-path, with WHY it is honest (NOT a stub)

The #1 cheat this spec exists to kill is stubbing a leg so the conjunction goes
green — that recreates the harness blind spot. Where a leg cannot be exercised
*exactly* in-process, the probe uses the **closest REAL path** and records the
caveat here. None of these is a faked outcome.

1. **login via BEARER, not the magic-link/AgentMail email round-trip.**
   *Closest real path:* the bearer-token path runs through the **same**
   `_operator_auth_middleware` a browser's cookie path flows through, and is
   verified by `secrets.compare_digest` against a **non-empty** token — a real
   401→200 transition, not a parameter flip or a hand-minted bypass.
   *Why honest:* the magic-link email leg needs AgentMail + a live inbox
   (networked, operator-gated); it cannot run in an in-process probe. Bearer is the
   closest *real* auth decision the middleware makes. *What it does NOT cover:* the
   email delivery + callback exchange (covered by the magic-link auth tests +
   `infrastructure/runbooks/magic-link-auth.md`).

2. **read via the BACKEND chunk fetch, not a headless SPA render.**
   *Closest real path:* `GET /chunks/{id}` is a real HTTP fetch through the
   production route — the bytes really do (or do not) leave the backend, gated by
   the real §9 retrieval gate.
   *Why honest:* a full render of the Vite/React reading SPA needs
   Playwright/chromium, not available in CI — `read.py:47-58` documents this same
   downgrade for the read probe. *What it does NOT cover:* the React render itself
   (BookReader painting Attribution + TocPanel without a runtime throw) — covered
   by the vitest suite `apps/reading/src/modes/Reading/Reading.test.tsx`.

3. **the read leg reads a SEEDED §9-attributed source document, NOT this
   journey's own research output.**
   *What it actually reads:* a **separately-seeded** servable public-domain
   document (in-process: `_seed_read_artifact`; live: a real prod
   `ANTIEK_PROBE_READ_CHUNK_ID`) — **not** a chunk of the research the launch leg
   just ran.
   *Why this is the honest best-available:* the launched demo cascade deposits
   **insights**, not a §9-readable **chunk**; there is no chunk of this journey's
   own product to read back. Asserting "read the result" against this journey's
   own output is not yet possible without inventing a chunk the cascade does not
   produce — which would be a stub.
   *What protective value SURVIVES:* a **dead read surface** (route moved /
   renamed / 404) and a **stripped or malformed §9 attribution** still RED the
   read/attribution legs — the read door and the attribution shape are genuinely
   exercised end-to-end through the production route. *What it does NOT cover:*
   read-back of **this journey's own** research output (that the specific research
   just launched produced a readable, attributed artifact). When the cascade
   deposits §9-readable chunks, promote the read leg to fetch one of **this**
   investigation's chunks (see *Reconsider-if* below). The verbatim definition's
   "read **the result**" must be read **with this caveat beside it**.

4. **the LIVE run against `api.antiek.ai` is OPERATOR-GATED — not executed by
   this sprint, but it asserts the SAME five legs as in-process (no forked second
   implementation, no leg skipped or weakened live).**
   *Closest real path:* the **same** probe, parameterized by
   `ANTIEK_PROBE_BASE_URL`, runs against live prod via `httpx` with the identical
   routes + assertions. **Live mode asserts every leg over the prod HTTP surface:**
   login (bearer 401→200), **launch** (poll `GET /research/sessions/{id}` to a
   terminal RunState — a REAL bounded poll, not accept-on-launch), **compound**
   (count `GET /trajectory/{leaf}` `knowledge.reused > 0` for **this** leaf — the
   per-investigation signal, not the frozen `/health` global), read + attribution
   (`GET /chunks/{id}` against a real prod chunk id). The in-process mode is the
   pre-merge gate; the live mode is the operator's post-deploy step.
   *Why honest / why gated:* a live run **writes a real research to the prod
   graph**, **needs prod credentials**, and **prod is HELD pending §9.0** on an
   unmerged branch. So SPR-08 BUILDS the live capability, WIRES it into `deploy.yml`
   as a REQUIRED (never-silently-skipped) task, and PROVES the probe can go RED
   **in-process** (forcing the compound leg's real surface to 0 → `[BLOCKED]
   usability_keystone: compound — knowledge_reuse_count == 0 …`, runner exit 1;
   the live launch + compound legs are additionally proven RED-capable by mocked-
   HTTP self-tests, no network) — but does **not** hit `api.antiek.ai`, mint a prod
   credential, or POST a research to prod. The live run is the operator's step
   (`infrastructure/runbooks/usability-keystone-verify-live.md`), mirroring SPR-06's
   operator-gated prod measurement. **A live dead flywheel REDS the live keystone**
   — the dead-flywheel incident cannot be reborn at this gate.

---

## What this sprint deliberately did NOT do (scope)

* **No new features.** The keystone COMPOSES the existing legs. A missing leg is an
  upstream finding, not something this sprint builds.
* **No write/speak extension.** The keystone today is the **Read/Research** journey
  (login → launch → compound → read → attribution). The Write and Speak workflows
  are **explicitly out of today's definition** (see *Reconsider-if* below).
* **No §9 serving or payout.** The attribution leg asserts metadata **presence**
  only (graph-only). No Stripe / `payout.py` / `stripe_connect` / `serve.py`
  trigger is touched; G2/G3 stay closed (grep the probe → no such path).
* **No §16 violation.** The probe writes only to per-PID temp paths through the
  same `connect_write` host lock the funnel uses — no second graph writer.

---

## Reconsider-if (when "usable" should be re-defined)

* **Write / Speak join the keystone.** When the Write (`docs/.../write`) or Speak
  (`specs/speak/`) workflows ship a user-facing journey, "usable" should grow a
  Write leg (author → save → read-back) and/or a Speak leg (invite → interview →
  transcript). Add them as **new legs in the same conjunction probe** (do not fork
  a second keystone), and update this definition's verbatim sentence in lockstep.
  Until then they are out of definition — naming them here keeps that boundary
  explicit.
* **The magic-link email leg becomes testable in CI.** If an AgentMail test inbox
  is wired into CI, promote the login leg from bearer to the real email round-trip
  (caveat 1) and update this record.
* **A headless SPA render harness lands in CI.** If Playwright/chromium becomes
  available, promote the read leg from the backend chunk fetch to a real headless
  render of `/read/:documentId` (caveat 2) and update this record + `read.py`.
* **The cascade deposits §9-readable chunks for its own output.** Today the read
  leg reads a *separately-seeded* source document, not this journey's own research
  output, because the demo cascade deposits insights (not §9-readable chunks) —
  caveat 3. When a launched research produces a readable, attributed chunk of its
  OWN output, promote the read leg to fetch one of **this** investigation's chunks
  (closing the "read-back of this journey's own product" gap) and update caveat 3 +
  the leg table + the runbook in lockstep.
* **The live run's operator gate lifts.** When §9.0 closes and prod is no longer
  held, the live keystone can move from operator-gated to a standing post-deploy
  blocker (flip `antiek_keystone_verify_live` to true by default) — update this
  record + `group_vars/all.yml` + the runbook together.
