# Usability Keystone — Verify-Live Against Real Prod

**Audience**: you (the operator), running the end-to-end usability keystone
against live `https://api.antiek.ai` as a **post-deploy** step.

**Time**: ~5 minutes once you have the two live credentials below.

> **SPR-08 did NOT run this live.** This runbook is the *checklist*. SPR-08 (the
> Antiek Convergence capstone) built the conjunction probe
> (`tools/reachability/probes/usability_keystone.py`), wired the
> base-URL-parameterized verify-live task into `deploy.yml`, and PROVED the probe
> can go RED in-process — but it executed **no live run**, minted **no prod
> credential**, and POSTed **no research to prod**. The live run is
> **operator-gated** and is your post-deploy step (mirrors SPR-06's operator-gated
> prod measurement). This document makes the live run *evidenced*, not *asserted*.

---

## What the keystone asserts

The keystone is the **CONJUNCTION** of the five legs that every other reachability
probe asserts only in isolation — driven as ONE journey:

| Leg | Live assertion (a feature OUTCOME, over the prod HTTP surface) |
|---|---|
| **login** | A protected route returns **401 without** a bearer token and **200 with** it — the real `_operator_auth_middleware` bearer path (`app.py:1315-1340`, `secrets.compare_digest`). |
| **launch** | A research started via the canonical entrypoint (`POST /research/plans` → `/approve` → `/launch`) is **polled** via `GET /research/sessions/{session_id}` until every research reaches a **terminal** RunState (`done`/`stopped`/`failed`/`budget_halted`); a non-`done` terminal reds. A research that never reaches terminal within the bounded deadline is a `launch` **finding** — not a silent pass. This is a **real live poll**, not accept-on-launch. |
| **compound** | **≥ 1 prior unit actually reused** for **this** investigation — the sum of `len(reused_unit_ids)` across `GET /trajectory/{leaf}`'s `knowledge.reused` events, **not** the count of those events (the event fires unconditionally once a retrieval substrate is wired, so an empty graph emits `reused_unit_ids: []`) and **not** the process-global `/health knowledge_reuse_count` snapshot (frozen at boot). Point the launch at a topic the prod graph already covers so a healthy flywheel injects a prior unit (non-empty `reused_unit_ids`). |
| **read** | A real artifact comes back through `GET /chunks/{id}` (a real HTTP fetch through the production read surface). **The chunk read is a SEEDED §9-attributed source document you supply (`ANTIEK_PROBE_READ_CHUNK_ID`), NOT this journey's own research output** — see "What the read leg does and does NOT cover" below. |
| **attribution** | The artifact carries well-formed §9 attribution: `document_id` + `ip_holder_name`/`ip_holder_status` present, `servable`/`servability` a well-formed pair. **Metadata presence only — no serving / payout is activated (G2/G3 stay closed).** |

The **same probe** runs two ways, parameterized by `ANTIEK_PROBE_BASE_URL`:

* **In-process (pre-merge gate)** — boots `create_app()`; the CI/merge gate. No
  base URL set. This is what blocks merges.
* **Live (post-deploy, THIS runbook)** — `ANTIEK_PROBE_BASE_URL=https://api.antiek.ai`;
  `httpx` against the live API. **Same routes, same assertions, same credential
  path — no leg is skipped or weakened live.** Launch polls the live status route
  to terminal; compound counts the live trajectory's per-investigation
  `knowledge.reused`. No forked second implementation.

### What the read leg does and does NOT cover

The read + attribution legs fetch the **separately-seeded** servable chunk you pass
in `ANTIEK_PROBE_READ_CHUNK_ID` — **not** the research the launch leg just ran. The
launched demo cascade deposits **insights**, not a §9-readable **chunk**, so there
is no chunk of *this journey's own product* to read back. **What survives:** a dead
read surface (route moved / 404) and a stripped/malformed §9 attribution still RED
the read/attribution legs — the read door and the attribution shape are genuinely
exercised. **What it does NOT cover:** read-back of *this journey's own* research
output. This is disclosed, not overclaimed; see caveat 3 in
`docs/decisions/usability-keystone.md`.

### Why a live keystone, not just `/health`

`/health` showed `knowledge_reuse_count=0` on live prod while **every brick was
green** — that is the dead-flywheel history this whole gate exists to kill. A
`/health` read alone misses the login / read / attribution legs entirely, and a
global counter can be true while **this** user's research compounded nothing. The
keystone exercises the journey, end to end, as the user lives it. See
`docs/decisions/usability-keystone.md`.

---

## Scope boundary — why this is operator-gated

Running it live:

1. **Writes a real research to the PROD graph** (the launch leg POSTs a real plan).
2. **Needs PROD operator credentials** — a real bearer token + a real readable
   chunk id.
3. **Prod is HELD** pending §9.0 on an unmerged branch.

So the deploy task is **OFF by default** (`antiek_keystone_verify_live: false` in
`group_vars/all.yml`) and the live run is **your** post-deploy step. The deploy
task is nonetheless **REQUIRED** — it never silently skips: when not armed it
**fails the verify** with a reminder (or records an explicit acknowledged deferral),
so the live keystone can never be silently forgotten.

---

## The two live credentials

| Env var | What | Where it comes from |
|---|---|---|
| `ANTIEK_PROBE_OPERATOR_TOKEN` | The prod operator **bearer token** the login + later legs present. | The value of `ANTIEK_OPERATOR_TOKEN` in the prod secrets file (`{{ antiek_secrets_file }}` on the box). **Read-only — do not rotate it for the probe.** |
| `ANTIEK_PROBE_READ_CHUNK_ID` | A **real servable prod chunk id** the read+attribution leg fetches. | Any `chunk_id` of a `public_domain` (or otherwise servable) document already in the prod graph. Find one with: `GET /chunks/search` or pull a `chunk_id` from a completed investigation's artifact. It must be **servable** so the attribution leg sees a populated owner. |

The probe **never writes the prod graph** for the read leg (§16 single-writer): you
supply an existing readable chunk id; the probe only `GET`s it.

---

## Run it — two ways

### A. Through the deploy play (ARMED)

```bash
cd infrastructure/ansible
ANTIEK_PROBE_OPERATOR_TOKEN='<prod operator bearer>' \
ANTIEK_PROBE_READ_CHUNK_ID='<a real servable prod chunk id>' \
ansible-playbook playbooks/deploy.yml \
  --tags verify,keystone \
  -e antiek_keystone_verify_live=true
```

A non-zero exit (any broken leg) **fails the play** and names the leg.

### B. By hand (the same probe, same parameterization)

```bash
# from the repo root, with the test interpreter / prod venv
ANTIEK_PROBE_BASE_URL='https://api.antiek.ai' \
ANTIEK_PROBE_OPERATOR_TOKEN='<prod operator bearer>' \
ANTIEK_PROBE_READ_CHUNK_ID='<a real servable prod chunk id>' \
python -m tools.reachability.probe_runner --only usability_keystone
```

**Expected green:**

```
[REACHABLE] usability keystone (login → launch → compound → read → §9 attribution, …)
```
exit `0`.

If you took the acknowledged-deferral path during deploy
(`-e antiek_keystone_verify_live=skip_acknowledged`), run **B** by hand before
declaring the deploy done.

---

## Reading a RED

The probe stops at the **first** failing leg and names it. Examples:

* `login — … WITHOUT a bearer token returned 200, expected 401` → auth is **not
  enforced** on prod (a protected route is open). Stop — do not proceed.
* `launch — no research in session 'session-<root>' reached a terminal state within
  8s via GET /research/sessions (states=…)` → a research started but never completed
  on prod (a runner/dispatch problem). This is a bounded-poll **finding** from the
  live status route, not a silent pass. (A terminal-but-`failed`/`budget_halted`
  state reds with `reached terminal state '<state>' (not 'done')`.)
* `compound — 0 prior units reused for investigation <id>` → **THE
  dead-flywheel defect on the live box**: the research ran and the
  `knowledge.reused` hook fired, but its `reused_unit_ids` was **empty** — **zero**
  prior knowledge was actually reused (summed from `GET /trajectory/<leaf>`). Either
  the flywheel is dead (the launch omitted the retrieval substrate) or the launch
  topic was not covered by the prod graph. This is the exact prod failure the whole
  convergence spec exists to catch — and it is a REAL live RED, reproducible against
  prod (no longer a documented-but-unreachable example).
* `read — GET /chunks/<id> 404'd` → the chunk id you supplied is absent; pick a
  real servable one.
* `attribution — servable artifact has NO ip_holder_name` → §9 attribution is
  missing on a servable prod source.

---

## Rollback / abort

The live keystone is **read-mostly**: the only write it makes is the **launch**
leg's real research (a small demo-loop cascade on a throwaway problem). To undo:

1. **It is self-contained** — the launched research is a normal investigation in
   the prod graph under a `session-…-leaf-…` id with a `keystone` / `__keystone_probe__`
   marker. It does **not** serve, attribute-for-payout, or touch money (no §9
   serving / Stripe path is in the probe — grep `usability_keystone.py` for
   `payout`/`stripe`/`serve` → none).
2. If you must remove the probe's research from the graph, delete its
   per-investigation event log + graph nodes by the `session-…-leaf-…`
   investigation id (the normal "drop an investigation" operator op). There is no
   special cleanup — it is an ordinary research record.
3. To **abort mid-run**: Ctrl-C the playbook / probe. The launch leg's background
   fan-out on the box completes on its own (it is a bounded demo loop); no partial
   state needs repair (§16 single-writer — each research appends only to its own
   per-investigation log).

**Never** weaken a leg to make the keystone pass (e.g. clearing
`ANTIEK_OPERATOR_TOKEN` to skip the login leg). A green keystone that skipped a leg
**is** the dead-flywheel disease reborn. If a leg legitimately cannot run live,
record it as a named caveat in `docs/decisions/usability-keystone.md` — do not stub
it.
