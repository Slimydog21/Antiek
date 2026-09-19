# Spatiotemporal Composability — Antiek spec

**Status:** DRAFT v0.2 — 2026-08-13. v0.2 incorporates the full adversarial review (`/Users/slimydog/DeepSeek-spatiotemporal-paper/spec-review-grok.md`, grok-4.6, different lineage): verdict ACCEPT-WITH-FIXES, 47 findings, mandatory fixes F1–F5 all applied (citation repairs incl. Thm 66/73 hypotheses + Def. 39/47/49/50/69 corrections; Antiek pin repairs incl. the `app.py:6772/6784` overflow honesty note, `substrate/dispatch/*` Lineup anchors, branch-labeled Link Monster, budget-key split, adapter counts; mapping repairs incl. §5.5 rewrite without transaction/version claims, arXiv cursor as durable coeffect with commit policy, broker-vs-bounce contract, latency inside health-key operations, notify as side channel, HMR private-state loss, SSRF as policy not sandbox, frame-telemetry withhold-the-payout choice, interleaved-fiber independence tests; obligations Def. 43/47/69 stated; §5.4/§6/§7 phase labels; HMR endpoint moved to P2).
**Source paper:** *A Programming Paradigm for Spatiotemporal Composability* — Yifan Shi, Wei Zhang, Tianyi Cui (Peking University + DeepSeek-AI), preprint draft of August 13, 2026, https://github.com/cordiverse/paper (PDF + markdown extraction at `/Users/slimydog/DeepSeek-spatiotemporal-paper/paper.md`).
**Reference implementation:** Cordis v4, https://github.com/cordiverse/cordis (TypeScript monorepo: `core`, `loader`, `hmr`, `group`, `include`, `timer`, `utils`; case study: Koishi, 4000+ community plugins).
**Reading method:** full paper ingested first-hand (277 KB extraction, all 8 sections, 105+ references); two independent subagent dossiers cross-checked (deepseek-v4-pro engineering dossier — complete numbered statement inventory, per-file Cordis architecture, novel-vs-known analysis; grok-4.6 adversarial reading — transferable-mechanism list, misreading hazards, limitations). Dossiers live at `/Users/slimydog/DeepSeek-spatiotemporal-paper/{dossier-deepseek.md,reading-grok.md}`.
**Companion artifacts:** Cordis source cloned at `/Users/slimydog/DeepSeek-spatiotemporal-paper/cordis/`.
**Posture:** spec only — no production code was changed. Where the paper's claims are weaker than they appear, this spec says so (see §10 and the hazard notes inline).

---

## 1. Vision

Antiek's product promise is *"own your mind"*: the user pours their full digital footprint into Antiek, crafts their graph, and manages the algorithms that run on it — with maximum transparency and control. Today that promise is carried by a research flywheel (continuous-research daemon, loops, gap detection, arXiv sync), an LLM Action Lineup (dispatch roles, provider routing, model binding), ingestion machinery (Link Monster, acquisition adapters), a DuckDB graph substrate (documents/chunks/nodes/edges + `write_log`), an ad framework (frame telemetry, anti-gaming), and a React reading app. The system already composes many long-lived, stateful components at runtime — and it already pays the price of doing so without a compositional discipline: the continuous-research daemon has been dead since 2026-07-16; the arXiv sync fails and strands its checkpoint; the knowledge-event recovery thread logged a `WriteLockTimeout` + `OverflowError` pair on prod (2026-08-13 04:37:08Z, traceback pinned to `app.py:6784` — a frame whose mechanism is **not yet proven**; today's `origin/main` has a *capped* backoff `min(0.05 * (2 ** (transient_failures - 1)), 0.5)` at `app.py:6772`, so the overflow's exact source is an open forensic question); a deploy restart triggered a DuckDB connection-config incident; a provider swap (bridge) fails a 5-minute health probe ~16% of runs with no working alert.

This spec applies the DeepSeek/PKU paper's paradigm to make that composition *safe by construction* instead of *safe by vigilance*:

- **Temporal composability (the paper's revertible effects, §3.1):** every context mutation carries an inverse the runtime tracks; unloading a component recovers the environment exactly (up to an observational equivalence). Antiek meaning: *unload a research loop, an adapter, an algorithm — and its graph writes, event registrations, and resource allocations revert in place, without a restart.*
- **Spatial composability (the paper's reactive coeffects, §3.2):** components declare what they need; the runtime resolves it and reactivates/deactivates them when the environment changes. Antiek meaning: *the Lineup, the flywheel, and the ingestion adapters declare their providers (models, keys, stores); when a provider appears, disappears, or changes identity, only the affected dependents reload — nobody 500s, nobody restarts.*
- **The context type (Γ∞, §3.3):** state + accumulator + dependency table as one first-class entity. Antiek meaning: *one "context" per running system — the DuckDB graph is the state projection, the inverse log is the accumulator projection, the provider registry is the coeffect projection.*

### 1.1 Design principles (derived from the paper, applied to Antiek)

1. **Every write goes through one primitive.** In Cordis every context mutation reduces to `ctx.effect` (§5.1.1). In Antiek, every graph/event/provider mutation should reduce to one tracked primitive (`acr.effect`). Untracked writes are outside the system boundary (§6.1) and forfeit recovery.
2. **Authors write inverses only for atomic effects; composites derive.** A component's teardown is *derived* from its loading by reverse composition (§3.1, Thm 16) — no hand-written `deactivate()` that can drift from `activate()`.
3. **Dependencies are declared, resolved, and reactive — never looked up ad hoc.** `inject` is a capability request; access outside it raises (§5.1.4). Antiek's health probe, router, and flywheel all become dependents of declared providers instead of probing with hard-coded timeouts.
4. **Provider identity, not value, drives reload** (§4.2, Def. 46; hazard 5 in the grok dossier). Replacing a model behind `lineup.provider` bounces dependents even if the new model answers identically; in-place mutation does not.
5. **Commuting work goes in effects; order-sensitive work goes in coeffects** (§3.3.2). Route tables, listener sets, registrations = commutative keys (any revert order). Prompt-building, cascade stage order, middleware chains = ordered (accumulator LIFO inside a component; declared dependency across components).
6. **The boundary is honest.** External emissions (an email sent, a payment charged, a file pushed to R2) are either withheld until commitment or compensated (§6.1). The spec says which Antiek operations are inside the boundary (revertible) and which are outside (compensable or withheld).
7. **Failure is per-fiber and recover-then-record** (§4.3.4, L-Raise): a failing transition recovers its partial effects, records the error on the fiber, and does not re-enter from an error outcome. One bad loop iteration must never take down the daemon, and never retry with an unbounded exponent.
8. **No restart as a composition mechanism.** Restarts are the coarse-grained workaround the paper critiques (§1.2.3). Antiek's deploy/restart incidents (pass 7–10 forensic reports) are the exact cost it names.

## 2. The paper in one page

- **Problem.** Static composition is well-founded; *dynamic* composition (plugins, self-evolving agent harnesses — VSCode, Koishi, agent runtimes) is not. Today's substitute — restart a process (temporal) or restart a service (spatial) — discards state and can't express intra-process dependencies (§1).
- **Revertible effects (§3.1).** An effect is `Γ → Γ × (Γ → Γ)`: new state + inverse. The effect context `∂Γ = Γ × (Γ→Γ)` carries `(state, accumulator)`; `track` composes inverses onto the accumulator; `recover` applies it. One-sided inverses chosen *per state* (witnessed effects `𝔈*`) are enough. `⋄` composes effects preserving revertibility. Independence (Def. 19) — transformation monoids commute and don't disturb each other's inverses — buys *any-order* revert (Cor. 21); LIFO needs no hypothesis (Thm 16).
- **Reactive coeffects (§3.2).** Coeffect context `Σ = (k:K) ⇀ 𝒱_k` — typed keys to values. `set` is itself a revertible effect (coeffect operations are effects). A component declares a *specification* `d ⊆ K`; `σ ⊧ d` is decidable satisfaction; every store transition is classified *activating / deactivating / neutral* against each spec (Def. 26). Isolation realms make one key bind differently per context; interception attaches per-key metadata (monoid, right-biased) so an orchestrator can constrain *how* a dependency is used without touching provider or consumer (§3.2.3).
- **The context paradigm (§3.3).** `Γ∞ = μΓ. Γ × (Γ→Γ) × Σ` — recursive context: state + accumulator + coeffect table. Load = execute effects; unload = recover. Observational equivalence `≃` (quotient by what the coeffects' operations can observe) makes recovery honest and supplies the independence assumption (Thm 42: operations at commutative keys are independent).
- **Calculus (§4).** A component is `(d, p, e)` — spec, provision, witnessed effect. A *fiber* is an instantiation with lifecycle state, parent, own table, retirement flag, committed view `ω` (which providers it resolved to). The registry derives the coeffect context as the union of ACTIVE fibers' tables (single-source keys). Five base rules: the orchestration rules (O-Insert/O-Retire/O-Remove) are orchestrator actions legal under stated premises (freshness + parent + disjoint provisions; retire is unconditional; remove requires retired-inactive-leafless); the lifecycle rules (L-Reload/L-Unload) fire on *target view ≠ committed view*. Only the L- rules are reactive. Four refinements: **withdrawal** (L-Leave marks a provider out of service before its inverses run; L-Unload is guarded by `¬relied` so consumers finish teardown first — Thm 63), **iteration** (effect iterators = reified delimited continuations; boundary between iterations where a divert may abort), **asynchrony** (inertia: a launched iteration lands; reload/unload chain), **failure** (L-Raise: recover-before-record, per-fiber error outcome, no re-entry from error). Metatheory: preservation, global temporal composability, global spatial composability, progress (the system always quiesces — Thm 66, *under its hypotheses*: acyclic dependency relation, bounded iterator length, all steps lifecycle rules; mutual-dependency cycles are refused, not solved — §6.5), confluence (quiescent states related by ≃ up to renaming — Thm 73, *under its hypotheses*: pairwise independence, every component total on its provision (Def. 69), **no failed fiber**; the paper's own caveat: "Failure is excluded from the statement because it is a genuine source of divergence").
- **Implementation (§5).** Cordis: `ctx.effect` (Alg. 1), `ctx.get/set` + `notify` (Algs. 2–3), fiber state machine with `refresh/reload/unload` (Algs. 4–5), Proxy-mediated context access (Alg. 6); declarative loader — entries `(id, url, isolate, intercept, config, disabled)`, configuration tree, per-field reconciliation, managed realms with delimiters (Alg. 7); three-phase HMR — module classification (Alg. 8), stale-entry detection (Alg. 9), transactional reload with cache backup/rollback (Alg. 10).
- **Discussion (§6).** System boundary (acquisition vs emission; withholding vs compensation), service multiplexing (exclusive binding vs **service broker** — load balancing, rolling updates, cross-process), capability-based access control via declared deps + interception (sandboxing needs an external boundary), language independence (closures; DI typing + mediation), mutual dependencies (cycles = predictable permanent inactivity; decompose cores + integration components), dependency versioning (interface drift / key collision; namespacing / peer deps / structural compatibility), OS co-design.
- **The paper's own future direction (§8):** self-evolving agent harnesses — "a compelling direction for future validation". That is Antiek's flywheel + Lineup. This spec is the transfer.

## 3. Terminology (Antiek-facing)

| Term | Paper | Antiek meaning |
|---|---|---|
| Context (Γ∞) | state + accumulator + coeffect table | the running Antiek system: DuckDB graph + inverse log + provider registry |
| Effect | mutation with an inverse | any tracked write (graph write, event emit, provider registration, loop side effect) |
| Revertible effect | `Γ → Γ × (Γ→Γ)`, tracked | an operation that can be undone in place by its inverse |
| Accumulator | composite of inverses (LIFO) | per-component undo stack; "what reverts if I unload this" |
| Coeffect | declared requirement | "I need: a model of family X, the vector index, the arXiv client, the operator token" |
| Coeffect spec `d` | set of keys | a component's declared needs (its capability request) |
| Provision `p` | set of keys it may write | what the component offers to others |
| Satisfaction | `σ ⊧ d` | all declared providers are ACTIVE |
| Notify | activating / deactivating / neutral | the *classification* of each store transition against a component's spec (Def. 26); the response is reload/unload via target-view comparison (Def. 46, Alg. 5) — no event payload is delivered to components |
| Component | `(d, p, e)` | an Antiek module: flywheel loop, lineup role, adapter, algorithm |
| Fiber | named instantiation with lifecycle | one running instance (e.g., one arXiv sync run, one model binding) |
| Committed view `ω` | provider identity map at activation | "which concrete provider am I running against" |
| Target view | what it should be running against | recomputed on every store change; reload fires on mismatch |
| Guard (`relied`) | withdrawal ordering | "wait until all consumers of my binding have deactivated" |
| Inertia | in-flight async transition lands | a launched LLM call or ingestion completes before teardown |
| Isolation realm | key → realm → value | tenant/user/test-scoped bindings of the same logical dep |
| Interception | per-key metadata monoid | policy on *how* a dep is used (SSRF allowlist, read-only, budget cap) |
| Loader entry | `(id,url,isolate,intercept,config,disabled)` | the declarative spec of what should be running |
| Reconciliation | diff config → least-disruptive ops | applying a config change without tearing down everything |
| HMR | transactional module reload | replacing adapter/loop code live with rollback |
| Boundary | inside = revertible, outside = not | DuckDB = inside; email/R2/payments = outside |
| Compensation | coarser-than-`≃` recovery | IVT verdict reversing an accrual; refund pattern |

## 4. Architecture — the Antiek Context Runtime (ACR)

ACR is the proposed Python realization of the paper's Γ∞ for the Antiek substrate (FastAPI + asyncio + DuckDB). It follows Cordis's three-tier shape: core (effects + coeffects + fibers), loader (declarative config + reconciliation), hmr (module replacement). It is *not* a port of Cordis; it is a Python realization of the same calculus, using the paper's own language-independence analysis (§6.4): Python supplies closures (temporal requirement), an import system + `sys.modules` eviction (module retraction), type hints + `__getattr__`/descriptors (coeffect typing/mediation), and asyncio tasks (the paper explicitly notes Python coroutines need explicit task spawning for Algorithm 5's `create_task`).

### 4.1 Core: `runtime/context/` (new package)

```
runtime/context/
  __init__.py        # public API: Context, component(), provide, inject, effect
  context.py         # Context: Γ∞ realization (state refs, accumulator, coeffect table)
  effects.py         # effect(), execute() — Algorithm 1 (guard, LIFO inverse folding, armed flag)
  coeffects.py       # get/set/isolate/intercept + notify — Algorithms 2–3
  fiber.py           # Fiber + refresh/reload/unload — Algorithms 4–5 (asyncio task = inertia)
  registry.py        # registry of fibers, uid atom, provider resolution (Defs. 44–45)
  access.py          # mediated access — Algorithm 6 (walk parent chain; INACTIVE/UNDECLARED)
```

Key realization decisions (each is a *decision*, with the paper citation):

1. **State projection = DuckDB through `db_lock`.** The state half of Γ is the existing single-writer DuckDB (`runtime/db_lock.py` — the single-writer contract the pass-10 incident already proved necessary). ACR effects that mutate the graph must run *inside* the write lock and yield an inverse closure that performs the compensating SQL. This *replaces* the ad-hoc retry/disconnect dance with the paper's discipline: an inverse per atomic mutation, composed LIFO. (Paper §3.1, Defs. 8–12; Cordis `fiber.ts`.)
2. **Accumulator projection = inverse log.** A per-fiber Python list of inverse callables (LIFO). The existing `write_log` table (203,781 events) remains the *audit/event-sourcing* record; the accumulator is the *mechanism* that can actually undo. The paper explicitly contrasts event sourcing (append compensating events) with executing inverses (§7.3) and uses both when appropriate: `write_log` stays for provenance; the accumulator is what teardown runs.
3. **Coeffect projection = typed key registry.** `Key[T]` objects (like Cordis symbol keys) with: value type, equivalence `≃` (default: identity on value; keys may override), operation set (methods that must respect `≃`), and an `is_commutative` flag (Def. 39 — *this flag is the discipline that buys any-order revert*; default False, set True only for route/listener/bag-shaped keys).
4. **One mutation primitive.** `ctx.effect(forward, inverse)` where both are async callables; `forward` may be a generator yielding `(step_forward, step_inverse)` pairs (effect iterator, Def. 51) — the paper's iterator form maps exactly onto Python generators/`yield`. The `armed` flag (Alg. 1) makes recovery fire at most once.
5. **Isolation realms** (`ctx.isolate(key, realm)`) for multi-tenant/user/test bindings — two-layer `key → realm → value` (Defs. 28–29). Antiek multi-user ("own your mind" per user) makes this non-optional: user A's `memory` must not resolve to user B's.
6. **Interception** (`ctx.intercept(key, metadata)`) — per-key metadata monoid, right-biased so the *enclosing* (system) context overrides component declarations (Defs. 30–31). This is the SSRF guard, budget cap, and read-only policy mechanism (see §5.3).
7. **Confinement (Def. 48).** A component's effect function may only write its own provisioned keys and read its declared keys. Enforcement: runtime mediation in `runtime/context/access.py` (walk the fiber chain — Algorithm 6) plus a **new** ACR lint (the existing `tools/lint/owner_boundary_check.py` is a different property — one-owner-per-layer servability — and is not the right starting file).

### 4.2 Fiber lifecycle (the paper's state machine, in asyncio)

State space (Def. 49): `Inactive(ζ) | Reloading(i, g, ω) | Active(g, ω) | Unloading(g, ω, ζ)` — the payloads matter: `i` the remaining effect iterator, `g` the accumulator built so far, `ω` the committed view, `ζ` the outcome (⊥ or error). Dropping them would make L-Raise and the withdrawal guard inexpressible. Transitions: `L-Begin/L-Iter/L-Finish` (activation as effect iterator — each iteration may `await`), `L-Divert` (target changed at an iteration boundary → abort or land-then-unload), `L-Raise` (recover-before-record; error outcome; no re-entry from error), `L-Leave` (mark UNLOADING *before* scheduling inverses — providers stop providing one step early), `L-Unload` (guard `¬relied` → drain dependents → run accumulator → discard committed view). Inertia: `fiber.inertia` = the asyncio task handle; launched iterations land before new transitions (§4.3.3; inertia is prose, not a numbered definition).

The **single-writer + guard** interaction deserves explicit design: ACR fibers that write DuckDB must hold the write lock only during *their own* iterations, and the `relied` guard's dependent-drain happens *before* the provider's final inverse (which is what releases the shared resource). This is the paper's Algorithm 5 lines 10/25 ordering, which the pass-10 DuckDB incident (RW+RO config collision) showed Antiek currently gets wrong by accident rather than by construction.

### 4.3 Declarative loader: `runtime/context/loader.py`

Configuration tree of entries `(id, url, isolate, intercept, config, disabled)` (Def. 74), realized as YAML/JSON (house pattern: ansible + systemd units already use YAML). Per-field reconciliation (least-disruptive): `id/url` → rebuild; `isolate` → realm reassignment (Alg. 7, delimiter tags); `intercept` → update in place (no reload); `config` → component decides (diff, reload on material change); `disabled` → unload/reload. Group component loads child entries as a keyed diff over child ids (`@cordisjs/group` pattern → Antiek `runtime/context/groups.py`). Confluence (Thm 73) guarantees the quiescent state is a function of the final config alone — the operator can edit config while running and the system converges.

### 4.4 HMR: `runtime/context/hmr.py`

Three-phase engine (Algs. 8–10): (1) module classification over `sys.modules` import graph (accepted/declined; cycles default to declined), (2) stale-entry detection (transitive imports, declined as boundary), (3) transactional reload (invalidate caches with backup, re-import, swap fibers; on any failure restore caches and rebuild from backup — never a half-reloaded state). Antiek v1 scope: HMR for *acquisition adapters and research tools only* (pure-Python, no compiled extensions), explicitly not for `interfaces/research/api/app.py` itself (the API process stays restart-deployed until P2).

### 4.5 Where ACR sits in the existing tree

- New: `runtime/context/` (core), `runtime/context/loader.py`, `runtime/context/hmr.py`.
- Wrapped (not rewritten): `runtime/db_lock.py` (state projection), `substrate/multimedia/provider_router.py` (provider resolution → coeffect resolution), `runtime/research_runner/` (flywheel → fibers), `acquisition/*` adapters (→ components), `interfaces/research/api/app.py` routes (→ effects on the API context).
- No change to: the DuckDB schema, the SPA framework, the auth model, the deploy topology (this spec does not move the restart boundary; it shrinks *what needs* a restart).

## 5. Feature mappings

Each mapping: **paper mechanism** → **Antiek today** → **Antiek with ACR** → **acceptance test**. File anchors are to `~/Antiek/platform/` paths on main.

### 5.1 Research flywheel → revertible-effects runtime (§3.1, §4.3.2, §4.3.4)

**Today.** `antiek-continuous-research.service` has been dead since 2026-07-16 (SIGTERM, never restarted); the arXiv OAI sync (`tools/arxiv_oai_sync.py`) runs as a systemd oneshot, fails at 05:38:58Z after 1h18m CPU, and strands its checkpoint at `skip=31200`; the knowledge-event recovery thread logged `WriteLockTimeout` then `OverflowError: int too large to convert to float` on prod (04:37:08Z, traceback pinned to `app.py:6784` per forensic passes 7–16). **Forensic honesty:** today's `origin/main` has the retry at `app.py:6772` as `delay = min(0.05 * (2 ** (transient_failures - 1)), 0.5)` — *capped*, not unbounded — and line 6784 is thread construction. The overflow mechanism is therefore NOT explained by the current code; the spec treats it as an open question, not a proven `2**` bug. What ACR changes regardless: retry arithmetic lives inside iterations with per-fiber error outcomes, so the daemon can never spin on an unbounded counter in daemon-level code (the class of bug is excluded by structure, whatever its 2026-08-13 instance was).

**With ACR.** Each loop iteration is an *effect iterator* (Def. 51): `yield (apply_step, revert_step)` per stage (gather → distill → store → promote). The daemon is a *fiber* whose accumulator is the iteration inverse stack.

- **Checkpoint resumability.** The arXiv resumption token (`SyncCheckpoint` / `arxiv_oai_sync.json` today) is **not** the fiber's committed view `ω` — it is a *durable coeffect binding* (`cursor.arxiv` key) that outlives the fiber, so it survives both unload and process restart. Policy (chosen): **successful pages commit** — each page-fetch iteration yields an inverse that is a no-op after commit; unload does NOT rewind committed pages, it only rolls back the in-flight page (divert grain = per page, §4.3.2). On `L-Raise` (read timeout), the fiber recovers the accumulator (rolls back the partial in-flight page write), records the error outcome, and — unlike today — *stays retired* rather than silently dying or re-entering (L-Begin requires `INACTIVE(⊥)`; an error outcome withholds re-entry against an unchanged environment, per §4.3.4). Re-enabling is a fresh O-Insert of a new fiber (or a target-view change), never a "reload of the failed fiber" — the paper's calculus has no such transition (L-Raise → `Inactive(ξ)`; L-Begin requires `Inactive(⊥)`).
- **Bounded retry by construction.** Whatever the 04:37:08Z overflow's exact source was (open question — see §1), the failure class is: *retry arithmetic in daemon-level code outside any lifecycle*. In ACR, retry is a fresh transition decision (O-Remove + O-Insert of the fiber, or a target-view change), never arithmetic inside the loop body: counters live inside iterations, and the fiber's error outcome (L-Raise) stops the loop with recovery-before-record (§4.3.4).
- **Loop rollback.** "Undo last loop pass" becomes: unload the loop fiber → accumulator applies inverses in LIFO → graph returns to pre-pass state (up to `≃`). This is the paper's *temporal composability* at the exact granularity the flywheel needs (Thm 16; Cor. 62: a departing fiber's contribution is nothing).
- **Flywheel HMR.** Loop code changes (new gap logic) hot-swap via §4.4: old fiber disposed (effects reverted), new fiber from reloaded module — without killing the daemon or discarding process-local caches. The paper's motivation §1.2.2 (self-evolving harnesses) is this feature.

**Acceptance.** (1) Inject a synthetic failure at iteration N of a 5-iteration loop; assert graph state after recovery == state before iteration 1 (≃, per key equivalence); assert fiber ends `INACTIVE(error)` and the daemon keeps serving other fibers. (2) Kill arXiv sync mid-page; restart; assert it resumes from the last committed checkpoint, not from 0. (3) `pytest` regression: overflow-class retry counters are unreachable (lint: no `**` exponent in loop code).

### 5.2 LLM Action Lineup → reactive coeffects + service broker (§3.2, §6.2)

**Today.** The Lineup has 17 dispatch roles with `dispatch_role` resolution (`substrate/dispatch/config.yaml` `role_tiers` + `substrate/dispatch/router.py` on main; the canonical checkout is 2,111 behind main, so main-only files are cited from `origin/main`), provider routing in `substrate/dispatch/router.py` + `substrate/dispatch/lineup_override.py` (both `origin/main`; `substrate/multimedia/provider_router.py` is a *multimedia/Krea* routing seam, not the Lineup router), `effective_model_for_action()` (action > role > default; PR #3076), cascade runner with owner-model authority, and per-action `allowed_models`. Provider failures (deepseek API stalls, kimi spawn errors, bridge flapping) are handled ad hoc per call site; the health probe polls the bridge with an 8s budget that the bridge's 21–32s responses blow through (~16% probe failure rate, no working alert).

**With ACR.** The Lineup becomes a *coeffect graph*.

- **Provider = fiber with provision `{model.family, model.instance, api-key.realm}`.** A consumer role declares `inject: {model.family, api-key.realm}` and *never* names a concrete provider. Resolution happens in the registry; the committed view records which concrete provider fiber satisfied the declaration at activation.
- **Provider swap = notify, not a config reload.** Switching `deepseek/deepseek-v4-flash → deepseek/deepseek-v4-pro` for role `note_taker` is a loader `config` change on the provider entry. `notify` classifies the change against each consumer's spec: consumers whose provider identity changed → `RELOADING` (new committed view), others → neutral no-op. No restart, no 500s, no manual "reset provider registry" (the test-env fixture bug class from #3076 disappears because registry state is lifecycle-owned).
- **Service broker for multi-provider families (§6.2).** A broker fiber provides `model.family` while backing providers register with it via revertible effects. Load balancing (round-robin/least-loaded), rolling updates (new provider fiber activates, weights shift, old unloads after in-flight drain — the paper's *quiescence*-based provider transition), and cross-process invocation (hermes bridge as a remote provider behind an RPC coeffect with an async contract — exactly the paper's §6.2 caveat: the bridge's 21–32s responses are why the interface must be async, which the health probe's 8s budget already demonstrates).
- **The health probe as a dependent, with latency inside the key.** Satisfaction-reactivity sees *presence*, not *latency* (a slow provider still satisfies `σ ⊧ d`). ACR therefore keeps a timeout **inside the health coeffect's operations** (the `health.bridge` key's operations carry their own latency budgets, Def. 24 — operations are part of the key's contract). The probe becomes a dependent fiber of that key; the alert webhook becomes a dependent of the probe's success key, so a dead webhook is a `deactivating` transition, not a silent 404. Timeout arithmetic is moved into the key's operations, not deleted.
- **Budget/anti-gaming as interception.** The daily budget caps become interception metadata on the `spend` key: right-biased, so the system-level cap overrides any component-level declaration (Defs. 30–31). **Two distinct budget systems exist today** — `would_exceed` in `interfaces/research/api/settings_budget.py` (operator cap) and `EXA_DAILY_BUDGET_USD` in `acquisition/search/exa/budget.py` (per-provider cap). Under ACR they are *separate keys* (`budget.operator`, `budget.exa`) unless the unification is designed explicitly; the spec proposes separate keys in v1.

**Acceptance.** (1) With role `note_taker` ACTIVE on provider A, swap provider entry to B; assert: role fiber reloads, committed view = B, zero 5xx in the window, in-flight call completed under inertia. (2) Withdraw provider A while a consumer is mid-call; assert the call lands (inertia) then the consumer deactivates with effects reverted. (3) Kill the bridge provider; assert dependents deactivate (probe reports `deactivating`), and when the bridge returns, they reactivate — all without a restart and with the alert webhook receiving the event. (4) Two providers, equal outputs, different identity → dependents bounce (provider-identity comparison, not value).

### 5.3 Link Monster & acquisition → hot-swappable components + interception (§5.2.2, §3.2.3, §6.3)

**Today.** `acquisition/link_monster/` (platform classification, oembed ladder, SSRF guard `fetchguard.py`, graph store) + 19 acquisition packages ≈ 79 `.py` files (`acquisition/{arxiv,books,gmail,inbox,interview,openaccess,opt_in,papers,podcasts,rss,search,snapshot,substack,textbooks,twitter,urls,video,voice,youtube}/`). Adapter code changes require a full service deploy/restart (pass-8/10 deploy incidents are the evidence of the cost); the SSRF guard is a hand-rolled allowlist check per fetch site.

**With ACR.**

- **Each adapter = component** `(inject: {http, oembed, ssrf-policy, store}, provide: {digested.URL, source.*})`. Adapter bugs are per-fiber failures (L-Raise): a failing platform adapter recovers its partial writes and records the error — a bad YouTube extraction can no longer strand the ingestion pipeline.
- **HMR for adapters (§5.2.2).** Adapter code updates land via transactional module reload: old fiber disposed (its partial graph writes revert), new fiber from the reloaded module, rollback to backup module on import error. **HMR discards component-private in-memory state** (the paper is explicit: "a component's own in-memory state does not survive a reload unless placed in a longer-lived dependency" — §7.3). Therefore: any state that must survive a reload (arXiv cursor, token buckets, rate-limit state) lives in **durable coeffect bindings or loader config**, never in adapter globals; the stale-set list in `hmr.py` must enumerate these keys. The `oai_pmh.py.bak-20260811` untracked-file incident class (manually patched prod source) becomes unnecessary: the loader's transactional reload *is* the safe patch path.
- **SSRF guard = interception, not per-site code.** `fetchguard.py` becomes metadata on the `http` coeffect key: `{allowed_hosts: [...], allow_private: false}` — enforced by the http provider at invocation time, adjustable at runtime without reloading any adapter, and *right-biased* so the system policy overrides adapter-declared metadata (Defs. 30–31; §6.3's capability-attenuation example is this exact shape: "grant read-only database access to a community component"). Adapters that fetch are *confined* (Def. 48): they can only reach declared keys, so an adapter cannot read undeclared dependencies or branch on another fiber's lifecycle. This is **policy, not a socket sandbox** — the paper is explicit (§6.3) that language-level access control is insufficient against a malicious component; a raw-socket escape requires a real execution boundary (out of v1 scope, §10.5).
- **Config reconciliation for platform lists.** The `platforms.py` classification table becomes loader config; adding/removing a platform is a YAML edit that reconciles incrementally (Thm 73) instead of a code change.

**Acceptance.** (1) Deploy a deliberately broken adapter via the loader; assert: import fails → caches restored → old fiber still ACTIVE (transactional rollback), system otherwise unaffected. (2) Change `ssrf-policy` metadata to block a host; assert in-flight fetches to that host fail at the provider, adapters do not reload, and no adapter can bypass (confinement test). (3) Unload the YouTube adapter mid-ingestion; assert its partial writes revert and other adapters unaffected.

### 5.4 "Own your mind" → user-facing spatiotemporal semantics (§1.1, §3.3, §5.2.1)

This is the product-facing heart: the paper's *transparency* is the "own your mind" promise made formal.

- **Per-algorithm effect transparency.** Every user-facing algorithm (the Lineup roles, the flywheel loop, curation/ranking, ad targeting) becomes a fiber *the user can see*. UI: "This algorithm currently holds 12 effects. Reverting it would: remove 3 graph edges, retract 2 knowledge events, release model binding `deepseek-v4-pro`. Nothing else changes." — that sentence is literally the accumulator's content (§3.1, Thm 16/Cor. 62). The user gets a *revert button* backed by the accumulator, not a settings toggle that half-works.
- **Declared needs as trust manifest.** Each component's `inject` set is the "what does this algorithm touch" manifest (capability request, §6.3). Antiek shows it before activation: "note_taker requires: model family (any), your graph read scope, your budget." The user approves or denies — a *capability review at load time* (§6.3), which is exactly the "manage their algorithms" promise. Un-declared access raises `UNDECLARED_ACCESS` and is visible in the UI.
- **Algorithm on/off = loader `disabled` flag.** Turning off an algorithm is an entry edit → fiber unload → effects revert in place. No restart, no orphan state, and the user's graph returns to its pre-activation state (up to `≃` — the UI states what reverts and what is merely "observationally restored").
- **Isolation realms = per-user graphs (§3.2.3, Defs. 28–29).** The same logical keys (`memory`, `attention`, `rankings`) resolve to per-user realms. Multi-user Antiek gets tenant isolation *by construction* — the "two subagents both `get("memory")` and do not share a store unless you say so" example from the grok dossier is the multi-user case.
- **Export/import = configuration tree + accumulator state.** `GET /export/my-graph` extends to export the *component configuration tree* (the loader's declarative config, §5.2.1) plus per-fiber accumulator manifests. Import = reconciliation (Thm 73: the quiescent state is a function of the final config — importing a config converges regardless of load order).
- **User-managed provider choice = broker selection (§6.2).** The model pickers in settings/lineup become broker policy: "for my note_taker, prefer: my own local model, fall back to subscription, never metered." The broker honors the user's declared preference, and switching is a weight change (rolling update), not a restart.

**Acceptance.** (1) UX: the Lineup board shows, per role: declared needs, current provider (identity), effect count, and a "revert & disable" control; disabling reverts and the graph diff is shown before/after. (2) API: `GET /algorithms/{id}/effects` returns the accumulator manifest; `POST /algorithms/{id}/revert` runs it and returns the recovery diff. (3) Isolation: two test users with identical logical deps get disjoint stores (no cross-user leakage test).

### 5.5 Graph/data layer → spatiotemporal versioning via durable compensation (§3.1, §6.1)

**Today.** DuckDB graph (documents 26,678 / chunks 5,435 / nodes 767 / edges 221) + `write_log` 203,781 events; `tools/lint/graph_temporal_integrity.py` (bitemporal edge windows); backup = nightly DuckDB EXPORT to R2 (SHA-256 verified at host + R2).

**With ACR.** The graph is the *state projection* of the root context. The paper's honest boundary discipline applies:

- **The accumulator is per-fiber and in-memory; durability is compensation.** Cordis reverts in-process effects; it does not give you a crash-safe undo of a database (§7.3 — the paper explicitly contrasts itself with DSU/event-sourcing/STM; §6.1 — emissions across the boundary are withheld or compensated, never reverted). ACR therefore does **not** claim "graph version = accumulator stack". Instead: `write_log` remains the provenance record, and a **new table** `acr_inverse_log(fiber_uid, seq, key, inverse_sql, committed_view_hash, status)` records *compensating statements* for the small set of keys that need crash-safe undo (v1: arXiv cursor, frame-telemetry accruals). That table is a *compensation ledger with a crash story we design*, explicitly labeled as beyond the paper's guarantees — the paper's metatheory does not cover replay-after-crash.
- **Batch rollback (in-process).** A research pass or ingestion batch = one fiber episode. "Undo the last pass" = run the fiber's accumulator (LIFO, in-process, Thm 16) — the *state* of a batch episode is the accumulator boundary, and this works while the process lives. This is exactly the paper's temporal composability at the grain Antiek needs (Cor. 62 under pairwise independence — see the obligation in §8).
- **Backup/restore = withholding + compensation (§6.1).** R2 uploads are emissions: withhold until the export verifies (the freshness marker + SHA-256 already implement withholding); restore = re-import + replay `acr_inverse_log` to the chosen point (our compensation design, not a paper theorem).
- **Observational equivalence (§3.3.2).** Recovery restores the graph *up to `≃`*: generative ids (DuckDB sequences) are not restored; bindings no key observes may differ. Per-key `≃`: node/edge tables use row-identity undo; caches (`discovery_cache`) use observational equivalence (equal under published operations). The UI states this in revert previews — no bit-exact promise.

**Acceptance.** (1) Roll back a 1,000-row ingestion batch via the accumulator in-process; assert the graph differs from pre-batch state only up to `≃` (sequences may differ; all observable queries identical). (2) Crash mid-recovery of a *compensable* key (arXiv cursor): on restart, replay completes from `acr_inverse_log`. (3) New lint passes on `acr_inverse_log` (every inverse references a committed effect).

### 5.6 Reading-app UX surfaces

- **The Lineup board** (tactics board) gains the *dependency view*: providers as nodes, roles as consumers, edges = declared keys; ACTIVE/RELOADING/UNLOADING/INACTIVE states as chips (the paper's lifecycle states are the truth; the UI renders them). A provider swap renders as a lifecycle-state transition cascade; Fig. 2 of the paper is the state machine we render (its two outlined states, Reloading/Unloading, are the ones users should see), but the animation grammar is our UX, not the paper's.
- **"What changed" feed.** Lifecycle-state transitions are logged by the runtime as a **new side channel** (per-fiber state changes: L-Begin/L-Finish/L-Leave/L-Unload with the key that moved) and surfaced as a user-visible activity feed. This channel is *new* — the paper's `notify` delivers no payload to components (Def. 26 is a classification, not an event bus), so the feed is our observability layer, not the mechanism itself.
- **Revert preview panel** (see 5.4): before any disable/rollback, show the accumulator manifest as a diff list with `≃` caveats.
- **Settings/lineup model pickers** become broker-policy editors (preferences, weights, fallback chains), not raw model selectors.
- **Scene/atmosphere surfaces (Werner, brain mascot) are NOT ACR surfaces** — they remain presentation; no dependency semantics leak into mascot behavior (explicit non-goal, §10).

### 5.7 AFA frame telemetry → compensation case study (§6.1, Def. 24)

**Today.** `substrate/ad_inventory/frame_attention_accrual.py` + `frame_telemetry` route: accruals written on frames; the pass-10 incident (DuckDB `ConnectionException` on `frame_telemetry`, 500s in the `connect_write(..., purpose="ad/frame_telemetry")` path of `interfaces/research/api/ad_routes.py`, ~line 365 on today's `origin/main`) showed the write path's fragility; anti-gaming (PR #3069) adds an IVT verdict pre-accrual filter.

**With ACR.** Telemetry accrual is the paper's *acquisition/emission* split made concrete — with one explicit choice: **the observation insert is the revertible effect** (inside the boundary: insert accrual row, inverse = delete by observation id), and **the payout/attribution emission is withheld** until the IVT verdict, then compensated. The anti-gaming filter (PR #3069) becomes *withholding* — the paper names this exact pattern ("withhold an emission until the state that produced it is certain to persist" — the output-commit problem, §6.1). A late IVT reversal is *compensation* (a coarser-than-`≃` inverse, composed in LIFO with other effects). The `frame_attention_accruals` key is declared *commutative* (Def. 39 — per-observation bag rows, so any-order revert is sound and audits replay in any order).

**Acceptance.** (1) A frame_telemetry write fails mid-batch; assert prior accruals in the batch revert and the route returns a structured error, no partial accruals. (2) IVT verdict on an already-accrued observation triggers compensation: reversal accrual + audit row, composed in LIFO. (3) The commutative-key lint accepts `frame_attention_accruals` and rejects an ordered key (e.g., a payout sequence) declared commutative.

### 5.8 Ops and infrastructure

- **Health probe → dependent fiber** (see 5.2): probe failures become `deactivating` events with the *cause* (provider slow/absent) instead of a FAILURE state; the dead webhook (404) is detected as a deactivated dependent, not a silent log line.
- **Deploy → config reconciliation + HMR.** The pass-7/8/10 deploy incidents (stale build stamp, restart-triggered DuckDB collision, uncommitted hotfix) all trace to restart-as-composition. ACR shrinks the restart surface: code changes to adapters/tools/lineup land via HMR; only `app.py`-level changes restart (P2 goal: eliminate even that with a full ACR host).
- **prod-parity gains a semantic check.** Today `prod_parity` compares `build_sha` only (blind to the uncommitted db_lock patch). With ACR, parity includes the *loader configuration tree hash* and the *inverse-log head* — drift becomes visible as a config diff, not a surprise.
- **Backup freshness + R2 = withholding/compensation discipline** (see 5.5).
- **Secrets as coeffects, not env globals.** `secrets.env` keys become coeffect bindings (`api-key.<provider>`) with realms per environment; rotation = provider fiber replacement (withdraw old binding, install new — dependents bounce on identity change, which is *desired* for rotation and matches the paper's provider-identity semantics).

## 6. API surface (additive; v1 = P0/P1 endpoints, P2 endpoints marked)

```
GET  /system/context                  # Γ∞ digest: state hash, accumulator count, coeffect table
GET  /system/fibers                   # registry: name, component, state, committed view, declared/provided keys
GET  /algorithms/{id}                 # component entry (config, inject, provide, effect manifest)
GET  /algorithms/{id}/effects         # accumulator manifest (what reverts)
POST /algorithms/{id}/revert          # run accumulator; returns recovery diff (≃-labeled)
POST /algorithms/{id}/disable         # loader entry disabled=true (reconcile)
GET  /providers/{key}                 # coeffect binding: realm, provider fiber, operations, ≃, commutative flag
PUT  /config/tree                     # replace a subtree of the declarative config (reconcile)
POST /hmr/reload                      # transactional reload of changed modules (dry-run flag first)
GET  /system/notify-feed              # activating/deactivating/neutral event feed (SSE)
POST /export/my-graph                 # extends existing export with config tree + inverse-log manifest
```

All endpoints auth-gated as today (operator + Cloudflare Access); the notify feed is per-user realm-scoped.

## 7. Frontend (P1+)

- Lineup board dependency view (state chips, notification cascade animation).
- Algorithm detail drawer: declared needs, current providers, effect manifest, revert/disable controls, `≃` caveat copy.
- Broker-policy editors in settings (preference/weight/fallback per role).
- "What changed" activity feed (SSE-backed).
- No new design language: house Lemon/PostHog-feel components; the dependency graph reuses existing graph rendering (nodes/edges already rendered in the reading app).

## 8. Testing & verification

House gates apply (pytest + shards, mypy declared-bar, tsc, vitest, keystone, enforce-declared-bar, visualtest). ACR-specific:

1. **Calculus conformance suite** (new `runtime/context/tests/`): each lifecycle rule as a test — L-Begin/L-Iter/L-Finish/L-Divert/L-Raise/L-Leave/L-Unload; inertia (in-flight iteration lands); guard (provider unload waits for dependents); confluence under Thm 73's hypotheses (same final config, shuffled orchestration orders → quiescent states related by ≃; **plus a failure-injected case that must diverge** — failure is excluded from the theorem); per-fiber failure isolation; **interleaved-fiber independence on the actual graph keys** (two fibers writing the same DuckDB tables, one reverts — the other's writes must survive; this is the real independence test, not a toy commutative bag).
2. **Fault injection** (extend `tools/faultinject/`): provider faults, readonly-fs, locked-db, mid-iteration kill — assert accumulator recovery and no cross-fiber leakage.
3. **Misreading-hazard regression tests** (from the grok dossier — these are the traps the implementation must not fall into):
   - no snapshot/rollback semantics (revertible ≠ transactional): a test that mutates via two interleaved fibers and reverts one — the other's state must survive;
   - one-sided inverses: revert then re-apply is NOT a no-op; double-revert is a no-op (armed flag);
   - provider identity not value: equal-value replacement bounces dependents; in-place mutation does not;
   - no pub/sub: notify delivers no payload beyond satisfaction/provider identity; components must not subscribe to ad hoc events on the store;
   - teardown order: provider's L-Leave precedes its inverses; dependents drain before L-Unload (assert via ordering probes);
   - runtime does not verify inverses: a wrong atomic inverse must be caught by *author tests* — every effect gets a round-trip test (apply → revert → assert ≃) as a CI requirement.
4. **Property tests** for the accumulator: random effect sequences; LIFO revert always reaches `≃`-initial state; commutative keys allow shuffled revert.
5. **DuckDB integration**: single-writer contract maintained; every effect's inverse runs inside the write lock; no RO/RW config collision (regression test from the pass-10 incident: open RW, run every read path).
6. **Production parity extension**: loader config tree hash + inverse-log head in `prod_parity`; uncommitted-file drift becomes a config diff.
7. **Adversarial review gate**: before merge of any ACR core change, a different-lineage reviewer runs the misreading-hazard suite against the diff (house pattern: grok adversarial review).

## 9. Rollout

### P0 — Foundations (the paper's calculus, minimal surface)
- `runtime/context/` core: `effect()` with guard + LIFO accumulator; typed coeffect keys with `≃` and commutative flag; fiber state machine (inertia, guard, L-Raise); registry + provider identity; mediated access (INACTIVE/UNDECLARED).
- Wrap the **arXiv sync** as the first fiber (highest pain, cleanest cut): effect-iterator per page, durable inverse log for cursors, L-Raise on timeout, loader entry with `disabled` flag.
- Wrap **frame telemetry** accrual as revertible effect + withholding (IVT) — the anti-gaming S2 pattern becomes the paper's emission discipline.
- ACR conformance + fault-injection suites; misreading-hazard regression tests.
- **Acceptance:** arXiv sync survives induced failures and resumes from checkpoint; frame telemetry batch failure reverts fully; all lifecycle tests green; zero production behavior change otherwise.

### P1 — Lineup as coeffect graph + user semantics
- Provider fibers + service broker for model families; `effective_model_for_action` resolves through the registry; provider swap = notify (no restart, no 5xx).
- Health probe → dependent fiber; alert webhook → dependent fiber (dead-webhook detection).
- Per-user isolation realms; algorithm detail drawer (declared needs, effect manifest, revert & disable); `/system/fibers` + notify feed (SSE).
- Config tree + reconciliation for Lineup/adapters (`PUT /config/tree`).
- **Acceptance:** live provider swap with zero 5xx; user disables an algorithm and the graph reverts (diff shown); probe failures emit events, not silent FAILURE; multi-user isolation tests green.

### P2 — HMR, flywheel resurrection, ops parity
- HMR engine for adapters + research tools (transactional reload with rollback).
- Continuous-research daemon as a fiber tree (loop = fiber, iterations = effect iterators); resurrect on a *recoverable* basis (the Jul-16 death class becomes an error outcome with a restart policy instead of a silent corpse).
- prod-parity semantic extension; backup/restore with inverse-log replay; full ACR host for `app.py` (restart-free deploys).
- **Acceptance:** adapter HMR rollback drill; flywheel runs 7 days without manual intervention (gap iterations recover individually); deploy drill with zero restarts.

## 10. Explicit non-goals (v1) and honest limits

1. **No restart-free API process in P0/P1.** `interfaces/research/api/app.py` remains restart-deployed until the P2 full host. ACR components are *inside* the process.
2. **No replacement of DuckDB, the SPA, or the auth model.** ACR composes with them.
3. **No bit-exact recovery.** Recovery is up to `≃`; generative ids are not restored; the UI and API say so (Defs. 33–37, Lemma 38 — the paper is explicit that physical state is not recovered, and this spec does not overclaim).
4. **No automatic trust for AI-generated components.** The paper's §8 vision (self-evolving harnesses) is P2+; v1 requires operator review of any new component's `inject`/`provide` (capability review, §6.3) before activation.
5. **No sandboxing in v1.** The paper is explicit (§6.3): access control via declared deps is not a security boundary against malicious code. ACR confinement + interception is *policy*, not *sandbox*; untrusted execution stays outside (remote exec, containers) until a real sandbox lands.
6. **No redo stacks, no transactions.** One-sided inverses only; transactional semantics for specific keys (budgets, ledgers) live *inside* those keys' operations (grok hazard 1–2).
7. **No value-level reactivity (FRP/signals) in the core.** Notification is component-level; a signal can live *inside* a coeffect value later (§7.4 of the paper).
8. **Mascot/presentation surfaces are not ACR surfaces.**
9. **The paper is a preprint under active revision** (README: "may change substantially"). This spec pins the draft of 2026-08-13; re-check §3–§6 before implementing P1+ details. The dossier's "UNKNOWN" passages (§10 of dossier-deepseek.md) are the places extraction was unreliable — re-read the PDF there.

## 11. Appendix — paper § ↔ mechanism ↔ Antiek file mapping

| Paper | Mechanism | Antiek file/module |
|---|---|---|
| §3.1, Defs. 1–12 | revertible effects, accumulator | `runtime/context/effects.py` (new); wraps `runtime/db_lock.py` |
| §3.1.3, Def. 19 | effect-function independence | `runtime/context/effects.py` independence checks |
| §3.3.2, Def. 39 | commutative key (flag) | `runtime/context/coeffects.py` `is_commutative` |
| §3.2.1, Defs. 22–24 | coeffect context, operations | `runtime/context/coeffects.py`; provider resolution via `substrate/dispatch/router.py` + `lineup_override.py` |
| §3.2.2, Defs. 25–26 | specs, satisfaction, notify | `runtime/context/coeffects.py`; `tools/ops/health_probe.sh` → dependent fiber |
| §3.2.3, Defs. 27–31 | isolation + interception | `runtime/context/coeffects.py`; SSRF policy → `acquisition/link_monster/fetchguard.py` (PR #3071 branch); budget → `interfaces/research/api/settings_budget.py` |
| §3.3.1, Def. 32 | Γ∞ context type | `runtime/context/context.py`; DuckDB = state projection |
| §3.3.2, Defs. 33–42 | observational ≃, key commutativity | `runtime/context/coeffects.py` per-key ≃; revert-preview UI |
| §4.1, Defs. 43–45 | components, fibers, registry | `runtime/context/fiber.py`, `registry.py` |
| §4.2, Defs. 44/46 | committed view / target view | `fiber.py` |
| §4.2, Def. 47 | registration = parent-tracked effect (O-Insert/O-Retire) | `fiber.py` `use()` |
| §4.2, Def. 48 | confinement (writes ⊆ p, reads ⊆ d) | new runtime check in `runtime/context/access.py` + new lint |
| §4.3.1, Def. 50 | withdrawal guard (`relied`) | `fiber.py` unload drain |
| §4.3.2, Defs. 51–52 | effect iterators | `effects.py` generator protocol; arXiv sync pages (divert grain = per page) |
| §4.3.3 | inertia | asyncio task handle in `fiber.py` |
| §4.3.4 | L-Raise, per-fiber failure | `fiber.py`; structurally excludes unbounded retry arithmetic in daemon-level code (the 2026-08-13 04:37Z OverflowError is an open forensic question — see §1/§5.1) |
| §4.4, Thms. 59–73 | metatheory (progress, confluence) | conformance suite `runtime/context/tests/` |
| §5.1, Algs. 1–6 | Cordis core | `runtime/context/*` |
| §5.2, Def. 74, Alg. 7 | loader, reconciliation, realms | `runtime/context/loader.py`; config tree YAML |
| §5.2.2, Algs. 8–10 | HMR | `runtime/context/hmr.py`; `acquisition/*` adapters |
| §6.1 | boundary, withholding, compensation | frame telemetry accrual (`substrate/ad_inventory/frame_attention_accrual.py`), R2 backup |
| §6.2 | service broker, rolling updates | provider broker in `runtime/context/`; lineup model pickers |
| §6.3 | capability access control | mediated `access.py`; interception policies |
| §6.4 | language independence (Python) | closures + asyncio + `sys.modules` eviction |
| §6.5 | mutual deps → decompose | design rule for flywheel/lineup graphs (no cycles in v1) |
| §6.6 | key namespacing/versioning | `Key[T]` namespacing: `model.deepseek.v4-pro`; peer-version checks in loader |
| §8 | self-evolving harnesses | continuous-research daemon as fiber tree (P2) |

---
*Spec v0.1, generated 2026-08-13 by the forensic/spec agent. Sources: paper draft of 2026-08-13 (first-hand full read + two independent subagent dossiers), Cordis source (cloned), Antiek main-tree file anchors. This document is a proposal; no production code was changed.*
