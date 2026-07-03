# ADR-177 — Single-writer coexistence: reconciling the reuse substrate's held read-only connection with `db_lock`'s writer

**Decision date:** 2026-07-03
**Status:** 🟡 PROPOSED — recommendation staged, awaiting DB-layer-owner ratification in issue [#177](https://github.com/Slimydog21/Antiek/issues/177). No product source changed (M4 gated).
**Owner:** AIIH SPR-01 (Antiek Invariant & Integration Hardening) · ratifier = DB-layer owner / operator (Lane G owns the single-writer invariant)
**Tree of record:** branch `caffen/AIIH-SPR-01` off `reader/integration`, HEAD `b082fe7b`. duckdb `1.5.4` (pin `duckdb>=1.1.0`), Python 3.12.

This ADR ranks the three reconciliation options named in #177 and recommends one, so the DB-owner can ratify or redirect in a single read without re-deriving the mechanism. It implements nothing — invariant #1 (single-writer) is the cardinal invariant and a wrong DuckDB-lifecycle change weakens it silently, under concurrency, in a way the six failing tests would NOT reveal.

---

## The mechanism (self-contained — a zero-context reader can ratify from here)

Antiek's invariant #1 is **single-writer**: every graph write funnels through `runtime/db_lock.py::connect_write` under `--workers 1`, so exactly one process ever opens the graph file read-write. Reads go through `runtime/db_lock.py::connect_read` (`duckdb.connect(path, read_only=True)`), which is meant to run concurrently with the writer.

DuckDB enforces a hard, in-process, per-file rule: **a read-only handle and a read-write handle to the same database file cannot be open at the same time** — they have "different configurations." Opening the second one raises:

```
duckdb.ConnectionException: Connection Error: Can't open a connection to
same database file with a different configuration than existing connections
```

This is verified verbatim at the pinned duckdb 1.5.4 by a 4-line repro (issue #177, re-run this session):

```python
import duckdb, tempfile, os
p = os.path.join(tempfile.mkdtemp(), "t.duckdb")
duckdb.connect(p).close()                 # create the file
ro = duckdb.connect(p, read_only=True)    # the reuse substrate's held _con
duckdb.connect(p)                          # db_lock's read-write open  → RAISES
```

The exclusion is **symmetric** (read-write-first then read-only-second raises identically) and **per-process** (it is not the OS `flock`; it is DuckDB's own instance-cache config check).

**Where each side lives in the product:**

- **Read-only, held.** The SPR-05 retrieval substrate (`substrate/graph/retrieval_substrate.py`) caches a read-only connection on `_con`. `BruteForceSubstrate.open` (`retrieval_substrate.py:136-137`) calls `db_lock.connect_read(db_path)` and stores the result via `__init__` (`:131-133`); the VSS fallback does the same (`:331,:339,:346`). The reuse module reads that held connection through `substrate/context_pack/knowledge_reuse.py::_substrate_connection` (`knowledge_reuse.py:269-286`, `con = getattr(retrieval_substrate, "_con", None)` at `:279`), and `retrieve_prior_units` runs its node-similarity scan over it (`:348`, `:356`, `:377`).
- **Read-write, transient.** `db_lock.connect_write` opens `duckdb.connect(db_path)` (`db_lock.py:316`) under an `fcntl.flock`, for each write.

When the cascade launch path holds the reuse `_con` read-only **and** any code opens the same graph file read-write during that window, DuckDB raises the coexistence error. That is #177.

## Verified signature (what is and is NOT red on this tree)

| Check | Command | Result (this session) |
|---|---|---|
| Isolation, single-process | `pytest tests/test_cascade_api.py -m "not integration" -p no:cacheprovider` | **17/17 pass** (15.8s) — functionally correct in isolation |
| Single-file under xdist | `pytest tests/test_cascade_api.py -m "not integration" -n auto --dist loadscope` | **17/17 pass** (20.5s) |
| Minimal 4-line repro | script above | **raises the exact `ConnectionException`** |
| Fast regression gate (new) | `pytest tests/test_single_writer_coexistence.py` | **1 xfailed** (0.64s) — drives the real `connect_read`+`_con`+`connect_write` path |

**Honest, load-bearing caveat (rigor #1):** the "6 failing `test_cascade_api.py` tests" from #177 are **dormant on this tree.** #177 was filed against `main` (`f4503b0b`), and its own "Signature (verified)" section states the six reds appear **only in the FULL suite under `-n auto`**, never in the single-file run. More decisively: the red requires the reuse substrate to be *threaded into the cascade launch path*, which was done by **PR #140 (`d6b8fe37`, "flywheel: wire the reuse substrate into the cascade launch path")** — and #140 is **not an ancestor of this tree's HEAD** (`git merge-base --is-ancestor d6b8fe37 HEAD` → false). Precisely: #140 was merged and then reverted on the `main` line (`eca87c8f`, `d569ebc4`, both likewise not ancestors of HEAD), and it was **never merged into `reader/integration`**, so its wire was never present on *this* lineage in the first place — "absent here," not "reverted here." On this tree `interfaces/research/api/cascade_routes.py:413-414` constructs `HostLocalRunner(...)` with **no** `retrieval_substrate`, so `host_local.py::_maybe_reuse_prior_knowledge` (`:255`) short-circuits on `None` (`:263-264`) and no read-only `_con` is ever held during a launch. **The mechanism is real (repro proves it); the cascade-API red is not currently reproducible here because the flywheel wire is absent on this lineage (never merged in — see above).** The reconciliation below is what lets #140's wire land safely — that is the real value, not clearing a red that this tree does not have.

Because of that, the M2 regression test (`tests/test_single_writer_coexistence.py`) deliberately drives the reuse-substrate open + `db_lock` writer **directly**, not through the cascade API — so it characterizes the raw seam and stays a valid gate whether or not #140's wire is present.

## The #140 lifecycle trace (rigor #4 — read the close, don't trust the message)

#140's final commit is titled *"close the reuse substrate in runner.join() (SPR-02 F3 lifecycle)."* The actual diff (`git show d6b8fe37 -- runtime/research_runner/host_local.py`) adds, **after** `await asyncio.gather(*tasks, ...)` in `join()`:

```python
sub = self._retrieval_substrate
if sub is not None and hasattr(sub, "close"):
    with contextlib.suppress(Exception):
        sub.close()
```

Tracing the timing across the three files:

1. **Open.** `cascade_routes._reuse_substrate()` (added by #140) calls `make_substrate("brute_force", _db(), model=...)` → `connect_read(_db())` at **runner-construction time**, and passes it as `HostLocalRunner(..., retrieval_substrate=_reuse_substrate())`. The read-only `_con` is therefore held from the moment the launch endpoint builds the runner.
2. **Held.** It stays open through the entire launch: `_maybe_reuse_prior_knowledge` at start (`host_local.py:250`), the whole browse/stream phase, and the promotion-funnel drain.
3. **Close.** `CascadeSession.join_and_merge()` calls `await self._runner.join()` (`cascade_session.py:197`); #140's `join()` closes the substrate there — but only **after** all research tasks finished.
4. **Write.** `join_and_merge()` then opens `connect_write` for the merge (`cascade_session.py:259`) and the synthesis artifact (`:225`); the promotion funnel also writes via `connect_write` (`promotion_funnel.py:126`), and those funnel writes can fire **during** step 2, while `_con` is still held.

**Finding — the close-gap is NOT a localized "join() forgot to close under xdist."** `join()`'s close is at the *terminal* point, but the coexistence window is the *whole launch*. Any read-write open that lands during steps 1–2 — a sibling investigation's `connect_write`, the promotion funnel's write, or (under full-suite `-n auto`) an unrelated module's writer on the same file — collides with the still-open read-only `_con`, and `join()`-closing afterwards cannot help. This is exactly what #177's signature describes ("a connection leak/overlap from a sibling module … causes the read-only `_con` to coexist with a read-write write") and why #140's join()-close was **necessary but insufficient** — the whole #140 wire was subsequently reverted on the `main` line (it was never on this lineage).

**Confidence (rigor #1): the localization is INCONCLUSIVE as a matter of direct observation, but the mechanism is decisive.** I could not run the full-suite red on this tree (the wire is absent on this lineage, so there is nothing to observe), so I cannot point at the single colliding writer empirically. What I *can* assert from the DuckDB exclusion rule + the #140 timing is that a terminal `join()`-close cannot make a launch-lifetime read window disjoint from writes that occur *inside* that window. That reasoning is what the ranking below rests on, and the recommendation names the one empirical result that would overturn it.

## The three options

### Option 1 — Transient reads (open+close per query)

Stop caching `_con`; the reuse substrate opens a `connect_read` for the duration of a retrieval and closes it immediately, mirroring `db_lock`'s transient-write pattern.

- **Diff surface (concrete):**
  - `substrate/graph/retrieval_substrate.py` — `BruteForceSubstrate.__init__/:131-133,:136-137` and the VSS fallback (`:331,:339,:346`) stop holding `_con`; `query()` (`:139-156`, `:371-390`) opens `connect_read`, runs, closes in a `finally`.
  - `substrate/context_pack/knowledge_reuse.py::_substrate_connection` (`:269-286`) + `retrieve_prior_units` (`:299-404`, which calls `_substrate_connection` once at `:348` then runs multiple `con.execute` scans) — wrap the whole retrieval in a single transient connection opened at the top and closed at the end, so all its scans share one short-lived read handle.
- **Invariant-#1 risk: LOW for integrity — but with a NAMED availability residual on the writer side.** It never opens a second writer and never corrupts state, so the single-writer *integrity* invariant is untouched (the risk class that matters most). But DuckDB's exclusion is **symmetric**, and the residual has two sides, only one of which is benign:
  - *Reader-side (benign).* A transient read that opens *during* an active writer raises — caught by the reuse path's existing try/except (`knowledge_reuse.py:343-346` returns `[]`), so it degrades to "no reuse." No red, no corruption.
  - *Writer-side (the one that must be named).* A `db_lock.connect_write` that opens *while a transient read is still mid-scan* fails the **writer** with the same coexistence `ConnectionException`. `connect_write` is on invariant #1's critical path and is **not** wrapped in the reuse try/except; worse, the existing retry helper `connect_write_retrying` (`db_lock.py:337-386`) only retries `WriteLockTimeout`, **not** this `ConnectionException`, so the write fails **loud and un-retried**. This is an *availability* regression (a rare, recoverable, non-corrupting failed write) — not an integrity violation of single-writer — but it is real, and it lands on the write path rather than the reuse path.
  Narrowing the window (whole-launch → short start-of-launch retrieval scan) makes both residuals rare but does not eliminate the writer-side one. See the recommendation for the small pairing that neutralizes it.
- **Behavior-change cost: LOW.** Reconnect-per-retrieval overhead only. #140 already chose `brute_force` (not the `vss` default) precisely because `brute_force`'s `connect_read` is copy-free; a fresh read connection is cheap.
- **Minimal? Mostly.** Localized to the retrieval substrate + the one reuse accessor. Narrows the collision window from "whole launch" to "just the start-of-launch retrieval scan," which is where #177's red overlap lives.

### Option 2 — Unified single connection (the true single-writer model)

Route reads and writes through **one** connection with a consistent config; there is no second handle, so RO/RW coexistence is structurally impossible.

- **Diff surface (concrete):** `runtime/db_lock.py` (the connection factory: `connect_write`/`connect_read`/`LockedConnection`, `:247-334`) grows a shared-handle model, and **every** read site retargets onto it — `connect_read` callers across `interfaces/research/api/*` (`library.py:76`, `distill_routes.py:177`, `ad_routes.py:189,290`, `payout_dashboard.py:222`, `marketplace.py:45`, `connector.py:58`, …), `substrate/graph/retrieval_substrate.py`, `runtime/research_runner/*`, `substrate/corpus_audit.py`. Dozens of files.
- **Invariant-#1 risk: LOW structurally, HIGH by construction.** Structurally it is the *strongest* option (see steelman) — one handle can never collide with itself. But a single shared DuckDB connection is not safe for concurrent cursors across the async coroutines Antiek runs under `--workers 1`; making it correct forces **serializing every read behind the writer's lock**, which removes the read/writer concurrency the system currently relies on and rewrites the most load-bearing seam. New bugs there are the expensive kind.
- **Behavior-change cost: HIGH.** Reads that run concurrently with the writer today would contend on the shared handle. Latency + throughput change across every read path.
- **Minimal? No.** Largest diff, deepest behavior change.

### Option 3 — Lifecycle discipline (close the held `_con` before any read-write open, reopen after)

Keep the held `_con`, but bracket writes: close it before a `connect_write` and reopen after. #140 shipped the *minimal* version of this (close once at `join()`).

- **Diff surface (concrete):** every cascade write site brackets the substrate — `cascade_session.py:225` (artifact) and `:259` (merge), `promotion_funnel.py:126` (funnel), plus `host_local.py::join()` (`:444-448`) as #140 had it; or a coordinator that makes the substrate yield its read handle whenever the `flock` writer is active.
- **Invariant-#1 risk: MEDIUM / SUBTLE.** It adds no writer, so it cannot *directly* break single-writer — but it is **racy**: "close-before/reopen-after" leaves windows where a sibling writer opens between your close and reopen, or your reopen lands during a sibling's write. It papers the symptom at *known* write sites; a NEW write site (or the sibling-module writer #177 blames) silently reopens the hole. This is the option most likely to look fixed (six tests green) while leaving the structural coexistence latent — the precise failure the invariant-risk review lens exists to catch.
- **Behavior-change cost: MEDIUM.** Reconnect churn + write/read coordination.
- **Minimal? The minimal version is insufficient (shipped in #140, reverted on `main`); a sufficient version is neither minimal nor cleanly localized.** #140 is the empirical proof: the smallest Option-3 diff (join()-close) did not clear the red.

### Summary

| Option | Diff surface | Invariant-#1 risk | Behavior change | Minimal? | Structural guarantee? |
|---|---|---|---|---|---|
| **1 · Transient reads** | `retrieval_substrate.py` conn lifecycle + `knowledge_reuse` accessor (`:269-286`,`:348`) | **Integrity: Low** (adds no writer, no corruption). **Availability residual**: symmetric exclusion can fail an *un-retried* `connect_write` if a read is mid-scan | Low (reconnect/retrieval) | Mostly | No — window narrowed not closed; reader-side residual degrades to "no reuse", writer-side is a rare loud failed write |
| **2 · Unified connection** | `db_lock.py` + every `connect_read` site (dozens) | Low structurally / **High** by construction (serializes reads) | High | No | **Yes** — one handle can't collide with itself |
| **3 · Lifecycle discipline** | every cascade write site + `join()` | **Medium/subtle** — racy; fake-green prone | Medium | Minimal version insufficient (#140, reverted on `main`); sufficient version not localized | No |

## Steelman of Option 2 — the unified connection (rigor #2)

Option 2 is the biggest diff and the easy one to dismiss as "too invasive," so state its strongest case honestly: **it is the only option that makes the coexistence *structurally impossible* rather than merely *avoided*.** Options 1 and 3 both leave two handles that *could* collide and rely on timing (Option 1 narrows the window; Option 3 sequences the window) to keep them apart — a future read site, a new writer, or a scheduling change can reopen the hole in either. Option 2 removes the second handle entirely: with one connection there is nothing to coexist with, which is *exactly* the spirit of invariant #1 ("exactly one writer"). If the flywheel is going to thread a persistent reader into the write-hot cascade path permanently, the structural guarantee is the honest end-state, and every session that re-derives "why is pytest red again" is paying the interest on not having it.

**Why it is still not the recommendation now:** the structural guarantee comes bundled with serializing every read behind the writer and rewriting `db_lock` — the single most invariant-critical seam — for a red that is *currently dormant* on this tree. That is a large, high-risk change bought to pre-empt a symptom that only appears once #140's wire is landed on this lineage. The disciplined sequence is: take the low-risk window-narrowing fix (Option 1) now so the wire can land safely, and escalate to Option 2 only if Option 1's residual coexistence proves to actually fire in production/CI. Option 2 is the right *destination*; it is not the right *first step*.

## Recommendation

**Adopt Option 1 (transient reads) as the reconciliation, gated on DB-owner ratification.**

Rationale, ranked: its **single-writer *integrity* risk is the lowest of the three** (it adds no second writer and cannot corrupt state), it is **localized** to the retrieval substrate + the single reuse accessor, and it **mirrors the existing transient-write pattern** in `db_lock`. It directly removes the launch-lifetime held-read window that is the proximate cause of #177 — which #140's Option-3 join()-close could not do.

**Reconciling the writer-side residual (named, not glossed).** Option 1 does not make coexistence *impossible*: DuckDB's exclusion is symmetric, so a `connect_write` that opens while a transient read is mid-scan still fails the **writer**, un-retried (see Option 1's risk section). That is why the recommendation is Option 1 **paired with one small, contained change**: teach the write path to treat the coexistence `ConnectionException` as retryable — either widen `connect_write_retrying` (`db_lock.py:337-386`) to catch it alongside `WriteLockTimeout`, or have `connect_write` briefly retry on it — so a rare collision becomes a sub-second retry instead of a loud failed write. That pairing is still far smaller and far lower integrity-risk than Option 2's rewrite of the write seam, and it keeps the residual an *availability* concern, never an *integrity* one. **If** the DB-owner judges even that residual unacceptable — e.g. the collision is with a concurrent sibling writer often enough that retries thrash — the weight shifts to **Option 2's structural guarantee**, which is precisely why Option 2 (not Option 3) is named the explicit fallback. Option 3 is not recommended as a sole fix: its minimal form is already proven insufficient (#140, reverted on `main`) and its sufficient form is racy and fake-green-prone.

**The one piece of evidence that would overturn this recommendation:** a full-suite `-n auto` repro **with #140's wire restored** showing the coexistence collision is **always at a single, identifiable write site that reliably occurs *after* the start-of-launch retrieval read completes** (i.e., the read window and the colliding write are naturally disjoint except for one localized ordering bug). If that is what the repro shows, then a targeted Option-3 close/reopen at that one site would be both minimal *and* sufficient and would beat Option 1 by avoiding all reconnect overhead. Conversely, if the repro shows the collision is with a **concurrent sibling investigation's or sibling module's writer** (which #177's "sibling module" language and the cross-scope `-n auto`-only signature both suggest), then no per-site lifecycle discipline is sufficient and Option 1 — or, if its residual fires, Option 2 — is required. Producing that repro requires temporarily re-landing #140's wire, which is itself a change the DB-owner should authorize; it is out of scope for this ADR (M4 is gated).

## What is NOT done here (M4 gate)

No product source is modified. `runtime/db_lock.py`, `substrate/context_pack/knowledge_reuse.py`, and `substrate/graph/retrieval_substrate.py` are unchanged. The regression gate `tests/test_single_writer_coexistence.py` is staged as `xfail(strict=True, raises=duckdb.ConnectionException)` and will flip to a real green only after the ratified option lands. Implementing a fix before ratification is precisely the failure this gate exists to prevent (weakening invariant #1 under concurrency, invisibly). Link this ADR from #177 so the issue and the decision stay joined.
