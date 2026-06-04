# The Reality-Contact Ratio (RCR) — the metric contract

**Date:** 2026-06-04
**Branch:** `caffen-rc/SPR-06` (Antiek Reality-Contact Ledger, spec `~/specs/antiek-reality-contact/`)
**Source spec:** SPR-06 — *The metric contract + convergence with First Light*
**Status:** ✅ Canon. SPR-01..05 merged on this branch; this records the definition future Antiek sessions inherit as the meaning of RCR.

This is the single document a maintainer reads to understand **what RCR means, how it is computed, why `tools/reality_contact/boundaries.yaml` draws the CORE/BOUNDARY line where it does, how to change that line without silently redefining the number, and how this suite-level measure complements — and does not overwrite — First Light's one-real-run done-bar.** It is self-contained: the RCR number is recomputable from the definition + worked example in §1 alone.

---

## 0. The one thing to read first — 97.62% does NOT mean "the suite is real"

The headline RCR on this branch is **97.62%** (164 reality / 168 claiming core-claims). That number looks reassuring. **It is not a clean bill of health, and treating it as one would re-commit the exact error this whole instrument was built to correct — over-trusting "green."**

Two facts make the caveat load-bearing:

1. **`theater = 0` is TRUE.** Zero tests statically resolve a mock onto a CORE symbol and then assert against that mock. That is a real, honest result — the static classifier found no "patch the orchestrator, assert a synthesis" pattern.

2. **But the metric is BY DESIGN blind to the dominant disease.** The disease that motivated the whole spec is *"mock the LLM, then assert a synthesis came back."* RCR cannot see it, for two compounding reasons:
   - The LLM/TTS provider (`substrate.dispatch.providers`) is classified **BOUNDARY**, not CORE (§2). A test that stubs the provider and asserts a synthesis is counted **`reality`** for the orchestrator/graph it genuinely runs — which is correct *for those subsystems*, but means provider-faking never registers as theater.
   - The provider is not even faked by *patching* in this codebase. It is faked by **dependency injection** — `register_provider(stub)`, `register_providers=False`, `Fake*Provider`, `StubProvider`. A grep for those patterns across `tests/` finds them in **56 files** (verified on this branch, 2026-06-04). Dependency injection is **invisible to static mock-detection**: there is no `patch()` target to resolve, so the classifier sees a test that exercises the real orchestrator end-to-end and labels it `reality`, even though the synthesis *content* is stubbed.

   The ledger records this as `provider_boundary_mock_file_count: 0` and then explains, in `provider_boundary_mock_file_count_note`, that **a value of 0 is EVIDENCE OF the blind spot, not absence of it.**

> **Quote the ledger's own `known_blind_spots` block (verbatim, `tools/reality_contact/ledger.json`):**
>
> > *"LLM/TTS provider mocks (`substrate.dispatch.providers`) and the other external seams … are classified BOUNDARY, not theater, BY DESIGN … So this metric does NOT detect the 'mocked the LLM and asserted a synthesis' pattern that motivated it. The boundary contract is pending SPR-06 operator ratification."*
> >
> > *"A value of 0 is EVIDENCE OF the blind spot, not absence of it: provider/LLM faking in this codebase is done by DEPENDENCY INJECTION (`register_provider(stub)`, `register_providers=False`), NOT by patching the providers module — and DI is invisible to static mock-detection. So DI-stubbed-LLM tests are counted 'reality' (they exercise the real orchestrator) even though the synthesis content is stubbed. SPR-06 should quantify the DI-fake magnitude — a grep of `register_provider` / `Fake*Provider` / `StubProvider` finds it in ~56 files."*

**So what is RCR, honestly stated?** It is a floor on a specific, narrow, *static* lie: "a test mocked a CORE engine module and asserted against the mock." It says nothing about whether a test is good, thorough, or correct, and it is structurally silent about the DI-stubbed-LLM pattern. RCR is one of two complementary halves of "is it real?" — the other (First Light's `syntheses≥1`) is the half that *does* catch the DI-stubbed end-to-end fake, because it watches one real research actually complete against live providers. See §3.

Everything below makes this precise. Read §0 again before ever quoting "97.62%" as if the suite were proven real.

---

## 1. Defining RCR — recomputable from this section alone

### 1.1 The unit of measurement: a `(file, subsystem)` claim

RCR is computed over the SPR-01 **ledger** (`tools/reality_contact/ledger.json`). Each test file carries a `subsystem_labels` map keyed by **CORE module name**, with each value in `{"reality", "theater", "indeterminate"}`. (A `mixed` file — real for one core, mocking another — is already expanded into per-subsystem labels in the ledger.)

The atomic unit is a **`(file, subsystem)` pair**, called a **claim**. A file *claims* a core whenever its `subsystem_labels` mentions that core at all — regardless of whether it then runs it (`reality`), mocks it (`theater`), or leaves the classifier unable to decide (`indeterminate`). A file claiming K cores contributes **K** claims. A file with **no** core label — an "n-a" file — contributes **zero** claims, which is the structural reason padding the suite with n-a tests cannot move RCR.

### 1.2 Per-subsystem counts and ratio

For each CORE subsystem `S`:

| Count | Definition |
|---|---|
| `claiming(S)` | number of files whose `subsystem_labels` contains `S` at all |
| `reality(S)` | of those, the count with `subsystem_labels[S] == "reality"` |
| `theater(S)` | the count with `subsystem_labels[S] == "theater"` |
| `indet(S)` | the count with `subsystem_labels[S] == "indeterminate"` |
| `other(S)` | any claim whose label is none of the above — **0 today** (the contract emits exactly three labels); surfaced so an unrecognized label can never sit silently in the denominator |

By construction `claiming(S) = reality(S) + theater(S) + indet(S) + other(S)` — no claim can vanish from the denominator unexplained.

```
RCR(S) = reality(S) / claiming(S)        (None — reported "n/a" — when claiming(S) == 0)
```

An unclaimed subsystem reports `n/a`, **never** `0.0` or `1.0`, so it cannot silently move anything.

### 1.3 The denominator rule and the conservative `indeterminate` handling

**Denominator rule.** Only files that **touch the core** are in `claiming(S)`. The numerator (`reality`) is the *subset* of that denominator the classifier could prove ran the core for real.

**Conservative `indeterminate`.** An `indeterminate` label counts toward `claiming` (the denominator) but **NOT** toward `reality` (the numerator). The classifier reaches `indeterminate` precisely when it *cannot prove* the core ran — so crediting it as reality would be the self-flattery the instrument exists to kill. Consequence: **an `indeterminate` claim can only ever hold RCR down or leave it flat; it can never raise it.** It is reported in its own column, never folded into `reality`.

### 1.4 The headline aggregation — claim-weighted, NOT a mean of ratios

```
headline RCR = ( Σ over all S of reality(S) ) / ( Σ over all S of claiming(S) )
```

i.e. **pooled reality-claims over pooled claims.** Equivalently it is the `claiming(S)`-weighted average of the per-subsystem `RCR(S)`. A naive `mean(RCR(S))` is **deliberately rejected**: it would give a subsystem with 2 claiming files the same vote as one with 84, so a tiny perfect subsystem would flatter (or a tiny bad one would tank) the headline out of proportion to its share of the suite. The pooled claim-weighted ratio answers the useful question — *"of all the core-claiming `(file, subsystem)` pairs in the suite, what fraction make real contact?"* — and is the quantity SPR-04 froze a baseline against. `headline` is `None` (an empty or n-a-only ledger) when `total_claiming == 0`.

These definitions are the verbatim contract of `tools/reality_contact/metric.py`'s `compute_metric` (its module docstring's `DEFINITIONS` / `HEADLINE AGGREGATION RULE` blocks). The doc and the code must not drift; §1.6 pins them together.

### 1.5 Worked micro-example — a 5-test toy suite, by hand, to an exact RCR

Take this 5-test toy suite. (It uses the real CORE module names so the vocabulary matches the live contract; the *counts* are invented to land on a clean fraction.)

| # | File | `subsystem_labels` | What it represents |
|---|---|---|---|
| 1 | `tests/t1_real_ops.py` | `{graph.ops: reality}` | runs `graph.ops` for real |
| 2 | `tests/t2_theater_ops.py` | `{graph.ops: theater}` | **mocks** `graph.ops` (a CORE symbol) and asserts the mock — theater |
| 3 | `tests/t3_indet_search.py` | `{graph.search: indeterminate}` | classifier cannot prove `graph.search` ran (e.g. a dynamic mock target) |
| 4 | `tests/t4_mixed.py` | `{dispatch.router: reality, graph.search: theater}` | a multi-claim file: real router, mocked search |
| 5 | `tests/t5_na.py` | `{}` (none) | n-a — touches no core; contributes **zero** claims |

*(Module names abbreviated; the full names are `substrate.graph.ops`, `substrate.graph.search`, `substrate.dispatch.router`.)*

Flatten to `(subsystem, label)` claims (file 5 yields none; file 4 yields two):

- `dispatch.router`: `[reality]` → claiming **1**, reality **1** → `RCR = 1/1 = 1.0000`
- `graph.ops`: `[reality, theater]` → claiming **2**, reality **1**, theater **1** → `RCR = 1/2 = 0.5000`
- `graph.search`: `[indeterminate, theater]` → claiming **2**, reality **0**, theater **1**, indet **1** → `RCR = 0/2 = 0.0000`

Headline (pooled):

```
total reality  = 1 + 1 + 0 = 2
total claiming = 1 + 2 + 2 = 5
headline RCR   = 2 / 5 = 0.40 = 40.00%
```

Note the two pieces of behaviour the example demonstrates: file 5 (n-a) added **0** to every count — padding is inert. File 3's `indeterminate` raised `graph.search`'s denominator from 1 to 2 and **dropped** its RCR from 100% to 0% without anyone mocking a core — the conservative handling in action.

### 1.6 Verification — the doc's number IS the code's number

Built as a Python dict and run through the **real** `compute_metric` (not re-implemented arithmetic):

```python
from tools.reality_contact.metric import compute_metric
m = compute_metric(toy_ledger)   # the 5 files above
# → total_reality = 2, total_claiming = 5, headline_rcr = 0.4  (40.00%)
# → dispatch.router RCR 1.0 | graph.ops RCR 0.5 | graph.search RCR 0.0
```

`compute_metric` returns `headline_rcr = 0.4` — **identical** to the hand-derived `2/5`. The same procedure applied to the real ledger on this branch yields `164 / 168 = 0.976190… = 97.62%`, matching `tools/reality_contact/baseline.json`'s recorded headline exactly. (Re-derive: build the toy ledger as a dict and run `compute_metric` — the worked number is reproducible, not asserted.)

### 1.7 What a HIGH RCR does and does NOT tell you (the limits)

- **Does tell you:** the test physically exercised the real CORE engine module(s) it claims — it did not satisfy its assertion against a mock of that module.
- **Does NOT tell you the test is good.** A real-but-shallow test (touches `graph.ops`, asserts almost nothing) counts as `reality`. RCR measures *contact*, not *coverage*, *depth*, or *correctness*.
- **Static blind spots — what the classifier cannot see, and what it does about each:**
  - **Dependency-injection fakes** (`register_provider(stub)`, `register_providers=False`, `Fake*Provider`, `StubProvider`) — invisible: there is no patch target to resolve, so a DI-stubbed test reads `reality`. This is the §0 centerpiece (56 files).
  - **`conftest`-level fixture injection / setattr swaps** — a fake installed through a fixture or a `setattr` on an object the classifier can't resolve fails-safe to `indeterminate` or is not counted — **never silently `reality`.**
  - **Dynamically-built mock targets** — a mock target assembled at runtime (string concatenation, `getattr`) that the classifier cannot statically resolve fails-safe to `indeterminate`.

  The classifier is deliberately **conservative, not omniscient**: when in doubt it does not credit reality. The honest consequence is that the DI blind spot inflates the numerator (DI fakes count as reality), while the indeterminate fail-safe holds the number down (cautious tests are excluded from reality). RCR is a floor on the *static* core-mock lie, nothing more.

---

## 2. The boundary contract — `tools/reality_contact/boundaries.yaml`, defended entry by entry

`boundaries.yaml` is the metric's **constitution**. It declares two lists (plus one carve-out list) that drive the entire ledger. The matching rule (per `classifier.py`): a mock target's dotted path `P` matches list entry `E` iff `P == E` **or** `P` startswith `E + "."` — module-prefix-scoped (deliberately *not* symbol-enumerated, which would rot the instant a function is renamed).

### 2.1 CORE — never-mock (6 modules)

A test that mocks one of these (for a subsystem it claims) is theater: its assertion is satisfied by the mock, not the real engine. Each was import-verified on this branch.

| CORE module | Why it is never-mock |
|---|---|
| `orchestration.loop_one.orchestrator` | The Loop-1 phase-1..8 research driver. A test claiming to cover the research loop that patches this is asserting against a **stub of the loop itself**, not running it. |
| `substrate.dispatch.router` | The dispatch **routing/selection + cost-normalization** logic (`dispatch()`, tier selection, `_compute_cost_usd`). This is the core decision code — **not** the provider HTTP clients (those are BOUNDARY, see §2.3). Patching the router stubs the very routing decision a dispatch test exists to prove. |
| `substrate.attribution.compute` | The §9 IP-attribution computation (`compute_attribution_for_synthesis`) — the economically-consequential layer. A test that mocks this is not computing attribution, only echoing a fixture. |
| `substrate.graph.ops` | Graph **write** operations (insert document/chunk/node/edge/section, gate-column updates). The real DuckDB-backed mutations are the substrate's source of truth; stubbing them means **no node was actually written**. |
| `substrate.graph.search` | Graph **retrieval** (`search()`, `cosine_similarity_sql`, `search_nodes_by_label`). Retrieval is load-bearing for every provenance claim; a mocked search returns canned hits instead of exercising the real index. |
| `substrate.graph.schema` | Graph/synthesis **schema + DB initialization** (`init_database`, `init_database_at_path`, `list_tables`). The schema *is* the substrate's shape; a test that stubs it is not exercising the real tables. |

> Note on naming: the master spec's *guessed* `graph.*` package does **not** exist — the real package is `substrate.graph.*`. The CORE list was corrected to the import-verified names; this is why a path-lint of CORE entries resolves against `substrate/graph/`, not a bare `graph/`.

### 2.2 BOUNDARY — legit-to-mock external seams

Stubbing these in a hermetic test is correct engineering, **not theater**. They are listed so the classifier never miscounts a boundary-stub as a core-mock, and so the contract is auditable rather than implicit. The 14 BOUNDARY entries, by class:

- **Network transports:** `httpx`, `requests`, `urllib` — HTTP/URL egress. A test MUST NOT hit the live network; stubbing the transport is hygiene.
- **Provider HTTP clients (the LLM/TTS endpoints):** `substrate.dispatch.providers` — the `anthropic` / `openai_compat` / `openai_tts` / `vision_*` clients that call out to third-party LLM/TTS APIs. This wraps **network egress to an external API** — a boundary, NOT the router's routing core. **This is the most consequential BOUNDARY entry (see §0 and §2.4): it is exactly where the motivating disease hides.**
- **Clock:** `time`, `datetime` — pinning "now"/sleeping is determinism hygiene, not domain logic.
- **Object storage:** `boto3` — AWS/S3/R2 backups & blobs; stub rather than write a live bucket.
- **Email:** `substrate.auth.email_provider` — the AgentMail/Mock email **seam** for magic-link auth. (The auth *domain* logic — magic-link token issuance/verification — is **not** on this list and remains reality-bearing.)
- **Payments:** `tools.stripe_connect` — money movement to a third-party processor; tests use `MockStripeProvider`.
- **Browser automation:** `browserbase` — third-party remote-browser ingestion fallback.
- **Third-party search / ingest endpoints:** `acquisition.search.exa`, `serpapi`, `acquisition.arxiv.client`, `arxiv` — external discovery/ingest HTTP; network egress, not substrate core.

The defensible line throughout: **a BOUNDARY is a seam that crosses a process/network/money boundary to something we do not own.** A dispatch *routing* test mocking the router (CORE) is theater; the same test stubbing a provider's HTTP call (BOUNDARY) is hygiene.

### 2.3 BOUNDARY_SYMBOLS — the surgical carve-out *inside* a CORE module

One entry, and it is **flagged for operator ratification**:

- `substrate.dispatch.router.DispatchConfig.from_yaml` — `from_yaml(path)` is the config-**file loader**: it `open()`s a YAML file off disk and delegates to `_from_dict`. It is filesystem config-I/O, **not** the routing *decision*. The 12 tests (2.8% of the tree) that stub it substitute an in-memory `DispatchConfig(...)` so the tier→provider map is fixed, then exercise the **real** `dispatch()` / provider-selection / cost logic — none of them patch `dispatch`, `_compute_cost_usd`, or `_from_dict`. The carve-out is checked **before** the CORE prefix match, so a mock landing exactly on this symbol (or a strict child) is classed BOUNDARY even though it sits under a CORE module; `_from_dict` (the real parse) and `dispatch` (the real route) are **not** carved out and remain never-mock. It was added from **evidence** (the M4 ledger surfaced 12 tests stubbing exactly this symbol), not by guess. *(That **12** is the historical M4-ledger count: a boundary-symbol stub is correctly classified as hygiene and leaves no `core_mock_evidence`, so the **current** ledger surfaces zero `from_yaml` references — unlike the 164/168 headline, the 12 is not re-derivable from the committed artifacts on this branch, and an auditor confirming it must grep the dispatch tests, not the ledger.)* **It is an open operator-ratification item — see §2.5.**

### 2.4 Why the LLM provider is BOUNDARY — and the honest tension

`substrate.dispatch.providers` is BOUNDARY because, *for the orchestrator and graph a test actually runs*, stubbing the provider's HTTP call is legitimate hermetic hygiene — a test of the research loop should not require a live, paid, non-deterministic LLM call to prove the loop ran. By that standard the classification is defensible.

The tension — stated plainly, not buried — is that **this is precisely where the disease lives.** "Mock the LLM, assert a synthesis" is *defined by* faking the provider. Classifying the provider BOUNDARY means RCR structurally cannot flag that pattern as theater, and the DI mechanism (§0) means it cannot even see the fake at all. This is not a defect to patch inside RCR — RCR is a *static core-mock* floor and the provider genuinely is an external seam. It is a **boundary of the metric's competence**, and it is the reason First Light's live `syntheses≥1` run is a *necessary* complement, not a redundant one (§3). Whether the provider should remain BOUNDARY given this is **open operator-ratification item (b)** — §2.5.

### 2.5 Change protocol — and the two open operator-ratification items

**Change protocol (binding).** `boundaries.yaml` is the metric's soul: **moving any entry silently moves the number.** Demoting a CORE module to BOUNDARY would let a test stub the real decision code and still read `reality`; promoting a BOUNDARY to CORE would reclassify every hermetic stub of it as theater and could trip the gate retroactively. Therefore:

1. **Any change to `boundaries.yaml` requires operator ratification** — it is not a routine code change.
2. **The change must carry a recorded rationale** (in the entry's `justification` and a decision note), because the file is itself the audit record.
3. **A change re-baselines RCR.** The frozen `baseline.json` (§3.1) was computed against a specific `boundaries_hash` (`sha256:e6a2271d…`, recorded in provenance and matching the live `boundaries.yaml` byte-for-byte on this branch). Changing the contract invalidates that hash and **requires re-freezing the baseline** with new provenance. A contract change that did not re-baseline would compare a new contract's ledger against an old contract's floor — meaningless.

**Open operator-ratification items** (flagged by SPR-01, *not* presented as settled):

- **(a) The `DispatchConfig.from_yaml` BOUNDARY_SYMBOL carve-out.** The claim is that stubbing the loader does not bypass the routing decision (the 12 tests still run real `dispatch()`/cost/`_from_dict`). The operator should confirm this is genuinely a loader/seam and **not** a path that lets a test sidestep a routing decision it claims to cover. If stubbing `from_yaml` were ever found to bypass real routing, this carve-out should be removed and those 12 tests reclassified.
- **(b) Whether `substrate.dispatch.providers` should remain BOUNDARY.** This is where the motivating disease hides (§2.4) and where the 56 DI-fake files live (§0). Keeping it BOUNDARY is defensible (it *is* an external seam) but means RCR is structurally blind to the LLM-fake. The operator should ratify this trade-off explicitly — accepting that RCR's silence here is covered by First Light's live run (§3), not by RCR.

Both items are recorded in `boundaries.yaml` itself under the `⚠️ OPERATOR-RATIFICATION ITEM` and provider comments; this section is their canonical decision home.

---

## 3. The frozen baseline, the blocking gate, and convergence with First Light

### 3.1 The frozen baseline (`tools/reality_contact/baseline.json`)

SPR-04 froze the floor. Recorded values:

| Subsystem | claiming | reality | theater | indet |
|---|---|---|---|---|
| `orchestration.loop_one.orchestrator` | 2 | 2 | 0 | 0 |
| `substrate.attribution.compute` | 3 | 3 | 0 | 0 |
| `substrate.dispatch.router` | 18 | 17 | 0 | 1 |
| `substrate.graph.ops` | 49 | 48 | 0 | 1 |
| `substrate.graph.schema` | 85 | 84 | 0 | 1 |
| `substrate.graph.search` | 11 | 10 | 0 | 1 |
| **Headline** | **168** | **164** | **0** | **4** |

→ **164 / 168 = 97.62%**, `theater = []` (empty), `exemptions = []` (empty).

**Provenance.** Frozen from `python -m tools.reality_contact.ledger` at the SPR-03-merged head of `caffen-rc/SPR-04`. `boundaries_hash = sha256:e6a2271d638db2bd849059a13c609d6546e420566f99f474c304b51307478555` (matches the live `boundaries.yaml`). `ledger_content_hash` is a SHA-256 over the canonical JSON of the **metric-relevant slice only** (`{core_modules, files[].{path, subsystem_labels, core_mock_evidence}}`), so a cosmetic ledger change (a reordered blind-spot string) does not invalidate the floor, while any change to the measured numbers does.

### 3.2 The exemption protocol — fair, recorded recourse for the blocked developer

The gate is one-way, but it is **never a wall**. A legitimate error-path core-mock (e.g. forcing the orchestrator to raise) is permitted — **but never silent**. The recourse:

```bash
python -m tools.reality_contact.ratchet --accept --reason "<why this core-mock is correct>"
```

This appends the current new un-exempted core-mock(s) to `baseline.json`'s `exemptions` list with the rationale **plus** ledger provenance and a timestamp. A bare `--accept` with no reason is **rejected** — the gate refuses to record an exemption with no rationale. Once exempted, that specific `(path, subsystem, target)` core-mock passes forever and can never be re-added silently. The exemption path **only appends**; it never lowers a per-subsystem floor. This is the fairness escape hatch: a developer who hits the gate for a defensible reason has a fair, recorded path through it — not a dead end.

### 3.3 The gate BLOCKS — with a recorded reconsider-if

`.github/workflows/reality_contact.yml` runs the SPR-04 ratchet on every PR and push to `main`. The ratchet regenerates the ledger from the **live tree** in-memory and compares it to the committed baseline; a non-zero exit (1 = a new un-exempted core-mock / a real test hollowed to theater, naming `file:line:symbol`; 2 = usage) **fails the job**. There is deliberately **no** `continue-on-error` and **no** `|| true` on the gate step.

**Why it blocks (the operator chose teeth).** This whole spec exists to kill "green that lies." A reality-contact gate that only *warned* would be the bitterest failure: it would annotate-and-pass exactly the regression it was built to stop. The gate is **deterministic static analysis** over the test tree (parse files, resolve mock targets against `boundaries.yaml`, count theater) — same tree in, same verdict out, on any runner. It has **no** runner-noise failure mode, so the usual "demote to informational" carve-out (correct for the microsecond inline-rubric latency lock, which *does* have runner noise) does not apply: demoting this would hide the teeth the operator asked for, not absorb noise. The fair carve-out for a legitimately-mocked core path is the **recorded exemption** (§3.2), not a blanket downgrade.

**RECONSIDER-IF (recorded so the decision survives turnover).** If **SPR-07's mutation probe demonstrates the static classifier has a HIGH FALSE-POSITIVE rate** — it red-flags tests that *do* make genuine reality contact — then downgrading this gate to **informational** (or narrowing its scope) becomes justified, because a noisy gate gets routed around. Until that evidence exists, it blocks.

**Operator follow-up (not committable from here):** mark `reality-contact-ratchet` a **required** status check in GitHub branch-protection so a red run actually prevents merge. This workflow makes the check exist and go red; only repo settings make it blocking-at-merge. *(Recording this here, not in `operator_gate_actions.md` — that file is First Light's territory; see §4.)*

### 3.4 Why the *theater set* is the gate, not raw RCR — and the ARE reconciliation

The gate keys on the **theater set** (and a per-subsystem theater-**count** floor), never on raw RCR. A raw-RCR floor has a false alarm: adding an honestly-`indeterminate` test raises `claiming(S)` while leaving `reality(S)` flat, so `RCR(S)` *drops* even though nobody mocked a core — punishing cautious engineering and creating pressure to delete the gate. The theater-count floor cannot be tripped by an indeterminate add (theater didn't move), so it fires **only** on a real "mocked the core" event. The two checks compose: a theater-set growth check catches *new* core-mocks (named to `file:line:symbol`); a reality→theater flip check catches *existing real* tests being hollowed out.

> **The ratchet's ARE-reconciliation block (verbatim, `tools/reality_contact/ratchet.py`):**
>
> > *"The repo's baseline philosophy is `tools/lints/baseline.py`: a versioned JSON envelope (`schema_version`) holding a SET of grandfathered offenses keyed by a frozen, sortable tuple, with a 'flag only NEW relative to baseline' predicate (`filter_to_new_only`) and a 'shrink-only' spirit … The reality-contact theater set is the SAME shape — a JSON set of keyed offenses that may only SHRINK silently and may only GROW with a recorded entry. We REUSE that philosophy and its conventions … rather than fork a parallel scheme. We do NOT import `baseline.py` directly: its `ViolationKey` is a 4-field (path, line, col, kind) lint tuple … the reality-contact baseline additionally needs per-subsystem reality/theater/claiming floors and a separate exemptions list with rationales, which is a richer envelope than the lint shape. So the new `baseline.json` FOLLOWS ARE's conventions … in a baseline file of its own, exactly as the ARE Wave-4 ADR anticipated ('a third lint joins with one entry' — here a third *baseline shape* joins by matching the conventions, not the dataclass)."*

(See `docs/decisions/are-wave-4-ci-floor-and-baselines.md` for the ARE baseline mechanism this reuses.)

### 3.5 Convergence with First Light — two complementary halves of "is it real?"

The sibling spec **antiek-first-light** has its own done-bar: a human watching **one real research complete** (`syntheses: 0 → 1`), recorded in *its* SPR-06 decision file at **`docs/decisions/first-light-reality-contact-bar.md`**.

> ⚠️ **Cross-branch reference.** `first-light-reality-contact-bar.md` lives on the **first-light branch** and is **not present on this branch** (`caffen-rc/SPR-06`). It is cross-referenced **by path**; this doc neither creates it nor requires it to be present here. The path is the contract; the file's authorship belongs entirely to First Light.

The two measures answer the same question — *"is the system real?"* — from **two different, both-necessary sides**:

| | **RCR** (this doc) | **`syntheses≥1`** (First Light) |
|---|---|---|
| **Scope** | The *whole test suite* — every core-claiming `(file, subsystem)` pair | *One* end-to-end research run |
| **What it proves** | How much of the suite's "passing" makes static contact with real core engine code | That *one* genuine thing happens end-to-end against live providers |
| **Catches** | A test that mocks a CORE module and asserts the mock (static core-mock theater) | The DI-stubbed-LLM end-to-end fake — the *exact* blind spot RCR cannot see (§0, §2.4) |
| **Blind to** | DI-injected provider fakes; conftest swaps; dynamic targets; test *quality* | The other 168 claims / 429 files it does not exercise; suite-wide breadth |
| **Form** | Continuous, automated, suite-wide static measure | A single, watched, live, end-to-end run |

**Neither is the superior measure, and this doc does not present RCR as the "real" reality measure with First Light's run as anecdotal.** They are precisely complementary: RCR is *broad but static and provider-blind*; `syntheses≥1` is *narrow but live and provider-real*. The DI-stubbed-LLM pattern that RCR is structurally blind to (§0) is **exactly** what First Light's live run catches — and the 429-file test suite First Light never exercises (a single live research run touches no test file) is exactly what RCR measures. Each catches what the other misses. **This doc complements First Light's bar and does not supersede it.**

---

## 4. Parallel-safety — what this sprint did NOT touch

This sprint adds **exactly one** file: `docs/decisions/reality-contact-ratio.md`. It edits no existing file.

- **`docs/operator_gate_actions.md`** — present on this branch but **read-only to this sprint**: it is the sibling antiek-first-light spec's shared doc, and the parallel-safety contract forbids touching it. The §3.3 operator follow-up (mark the check required) is recorded *here*, not there.
- **`docs/decisions/first-light-reality-contact-bar.md`** — First Light's, on the first-light branch, **absent here**. Cross-referenced by path only (§3.5); never created or edited.
- **`boundaries.yaml`, `baseline.json`, and all `tools/reality_contact/*.py`** — documented, not changed. Where the contract raised a question (the two §2.5 items), it is surfaced as an open operator-ratification item, not patched.

---

## 5. Self-ratification (the five values)

- **Intellectual honesty:** the centerpiece — **97.62% does NOT mean the suite is real** — is §0, before the definition, not buried. `theater = 0` is stated as true *and* as blind to the DI-stubbed-LLM disease (56 files, verified). The limits section names every static blind spot and which fail-safe each hits.
- **Fairness:** the blocked developer's recourse (the exemption protocol, §3.2) is documented prominently with the exact command; First Light's bar is framed as an **equal** complement (§3.5), with neither measure presented as lesser — the comparison table gives each its own "catches" and "blind to" row.
- **Rigor:** the RCR definition (§1) is recomputable from the doc alone, proven by the 5-test worked example (§1.5) whose `40.00%` was verified equal to `compute_metric`'s output (§1.6), and whose method reproduces the real `97.62%`.
- **Diligence:** read against the real artifacts — `boundaries.yaml` comments, `metric.py`'s `DEFINITIONS` docstring, `ratchet.py`'s ARE-reconciliation block, the ledger's `known_blind_spots` (quoted verbatim), and the `are-wave-4-ci-floor-and-baselines.md` format reference. First Light's doc was confirmed absent (cross-branch) and not touched; `operator_gate_actions.md` was confirmed present and left untouched.
- **Defensibility:** every CORE and BOUNDARY entry has a recorded justification (§2.1–§2.3), the change protocol forbids silent redefinition (§2.5), and every reconsider-if (the two ratification items, the SPR-07 gate-downgrade condition) is recorded so the metric survives turnover and cannot be quietly re-pointed by a future contributor who never saw this run.
