# Briefing-theater taxonomy

**Status:** Active — ANT-EXEC-H2V SPR-02 (2026-06-02)  
**Protocol:** `docs/agent-execution/HARD_TO_VARY.md` (forbidden F1–F8)  
**Audit:** `docs/agent-execution/ADVERSARIAL_RUBRIC.md` (binary PASS/FAIL rows)

**Briefing theater** is orientation prose that *survives* deleting every falsifiable artifact (Env Card, Scope Map, full verify log, named pytest, measured artifact). An adversarial re-read should classify theater **before** accepting closure.

---

## How to use

1. Read the handoff and session log for symptoms below.
2. Match the **strongest** class (multiple classes may apply).
3. Mark session **FAIL** if any matched class lacks a counter-example artifact listed in the discriminant.
4. Map to **F#** for `audit_agent_session.sh` / SPR-04 grep alignment.

**Lineage anchors (load-bearing):**

| Anchor | What it proved | Cite |
|--------|----------------|------|
| **Egghead** | Correct cascade diagnosis + polished briefing, then easy-to-vary verify | `docs/specs/ant-h2v/index.html`, `docs/htmlspec/antiek-hard-to-vary-execution/index.html` |
| **DispatchDecomposer** | Pre-network `TypeError` from keyword drift; not provider outage | `roles/cascade_planner/planner.py`, `scripts/repro_cascade_decompose_contract.py` |
| **AMS-v1 fiction** | Sprint pages cited DOM/paths that never existed on `origin/main` | `docs/ams-v2/verified-interfaces.md`, `tools/specs/verify_spec_refs.ts` |
| **ccb4c66** | Hop-delay tuning → ~4.5s perceived lag class without p95 artifact | `docs/htmlspec/werner-ice-fishing-cursor/index.html`, postmortem `ccb4c66` |
| **D17 ambiguity** | Bare "D17" without line+SHA blocks finding Personal-Reading live-ingest deferral | `docs/engineering_deferrals.md` L475+ |

---

## Class index

| Class | One-line symptom | Maps to |
|-------|------------------|---------|
| T-01 | Truncated pytest as sole sign-off | F1 |
| T-02 | Wrong cwd / system Python | F2 |
| T-03 | "Platform OK" without Scope Map | F3 |
| T-04 | Missing handoff `###` headings | F4 |
| T-05 | Invented p95 / fps / cost | F5 |
| T-06 | Bare xfail without bite fixture | F6 |
| T-07 | Informational CI cited as blocking proof | F7 |
| T-08 | Bare deferral ID ("D17") | F8 |
| T-09 | "Provider down" on pre-network TypeError | F-equivalent (cascade) |
| T-10 | FakeDecomposer-only regression story | F-equivalent (cascade) |
| T-11 | Spec cites unverified UI paths | F3 + anti-fiction |
| T-12 | Contract claims from memory, no `inspect` | F-equivalent (Phase A) |
| T-13 | Mega-briefing replaces handoff packet | F4 + F3 |
| T-14 | Hop/lag "feels fixed" without measurement | F5 (Werner) |

---

### T-01 — Truncated verify tail

**Symptom:** Handoff or chat says "pytest green" while the only attached log is `pytest … 2>&1 | tail -20` (or repeated truncated runs). Collection errors, wrong test selection, and import hangs are invisible.

**Discriminant:** **Theater** if no full log path ≥500 bytes (SPR-08 bar) or complete stdout in Gate results. **Not theater** if `.artifacts/verify.log` (or equivalent) contains the full run from repo root with exit code on the last line.

**Counter-example:** Egghead session had the right `DispatchDecomposer` root cause but failed closure because verify was truncated — a **re-run with full output** and Env Card would have been honest partial closure, not theater.

**Maps to:** **F1** — `docs/agent-execution/HARD_TO_VARY.md` forbidden row F1; egghead cascade session.

---

### T-02 — Wrong interpreter theater

**Symptom:** "All tests pass" while `which python` is system 3.9, pytest invoked from a package subdirectory, or cwd is not repo root (no `pyproject.toml` / Antiek `.venv` in Env Card).

**Discriminant:** **Theater** if Env Card `pwd` ≠ Antiek root or Python path is not `.venv/bin/python`. **Not theater** if canonical block records `pwd`, `.venv/bin/python -V`, and gate commands match `scripts/canonical_verify.sh` profile.

**Counter-example:** Running `tests/test_cascade_planner.py` from repo root with `.venv/bin/python -m pytest … -q` and pasting exit `0` + interpreter path — even one file — is evidence, not theater.

**Maps to:** **F2** — egghead wrong-cwd/venv pattern; SPR-08 `canonical_verify.sh` exists to collapse this class.

---

### T-03 — Unbounded platform OK

**Symptom:** Closure uses "engine fine," "platform OK," "all paths work," or AMS "green & invisible" without a Scope Map row per entry point (`tested` / `untested` / `live-LLM-required` + evidence).

**Discriminant:** **Theater** if deleting the Scope Map table leaves the closure sentence unchanged. **Not theater** if each claimed surface has `file:line` or `test_file:line` and explicit out-of-scope rows.

**Counter-example:** Handoff Scope Map with `POST /research/plans` (omit `sub_questions`) = `tested` citing `tests/test_cascade_create_plan_light.py` — bounded claim only for that row.

**Maps to:** **F3** — egghead; AMS-v2 master spec "green without verified DOM" (`docs/htmlspec/antiek-hard-to-vary-execution/index.html`).

---

### T-04 — Heading amputation

**Symptom:** Handoff omits `### Env Card`, `### Not proved`, `### Gate results`, or other `TEMPLATES.md` headings; or headings exist but say "see above" with no content.

**Discriminant:** **Theater** if `tools/agent/verify_handoff.ts` (SPR-03) would fail the packet. **Not theater** if every heading present with content or `N/A — <reason>`.

**Counter-example:** Sprint doc-only session: `### Env Card` filled, `### Gate results` = `N/A — docs-only, no pytest`, `### Not proved` lists what prose did not establish.

**Maps to:** **F4** — hides skipped diligence; mega-briefing often triggers T-04 + T-13 together.

---

### T-05 — Invented metrics

**Symptom:** Handoff cites p95 lag ≤950ms, fps, token cost, or "CI green" for serve/rights/craft without a named artifact path, blocking job, or operator measurement procedure.

**Discriminant:** **Theater** if the number can be removed and the narrative unchanged. **Not theater** if Werner handoff attaches measurement file + method (`docs/htmlspec/werner-ice-fishing-cursor/operator-acceptance.md`) or cites `mountain-shell-v2-verification.md` row with command + exit.

**Counter-example:** "p95 not measured this session; SPR-07 blocks merge" under `### Not proved` — honest, not theater.

**Maps to:** **F5** — Werner SPR-07; **ccb4c66** hop-tuning claimed precision without artifact.

---

### T-06 — Rotting xfail guard

**Symptom:** Test marked `xfail` or skipped with rationale in chat but no regression fixture that fails if the guard is removed (`_with_xfail_bite_test` pattern).

**Discriminant:** **Theater** if coverage looks green while production path still broken. **Not theater** if paired bite test exists per `docs/decisions/spr-09-boundary-lint-vs-import-linter.md`.

**Counter-example:** xfail on flaky integration **with** a hermetic test that asserts the underlying contract on every PR — guard and proof separated explicitly in Scope Map.

**Maps to:** **F6**.

---

### T-07 — Informational CI as legal proof

**Symptom:** Closure treats Lost-Pixel diff, axe warn-only, or latency workflow `::warning::` as proof of serve-tier, rights, or craft shipping.

**Discriminant:** **Theater** if no blocking job name + link for the product claim. **Not theater** if claim limited to "informational signal" and blocking gates named separately (`docs/decisions/ci-informational-gates.md`).

**Counter-example:** "Serve closure: `tests/test_arxiv_rights_invariant.py` exit 0" — legal proof row distinct from visual regression warnings.

**Maps to:** **F7**.

---

### T-08 — Bare deferral ID

**Symptom:** Handoff says "deferred per D17" or "D17 blocks" without `engineering_deferrals.md:L###` @ commit SHA.

**Discriminant:** **Theater** if reader cannot open the deferral cluster in one hop. **Not theater** if cite is `engineering_deferrals.md:L475` @ `9aeb2c9` (Personal-Reading live-ingest cluster — operator ingest window, not "code missing").

**Counter-example:** "Live Gutenberg fetch not proved — `engineering_deferrals.md:L475-L504` @ SHA; offline fixtures tested in `tests/…`" — bounded deferral, not theater.

**Maps to:** **F8** — D17 ambiguity class; operator gate docs require line-precise cites.

---

### T-09 — Provider-down misdiagnosis

**Symptom:** Narrative blames LLM outage, rate limits, or "decomposer model" when repro shows `TypeError` before `dispatch()` network I/O (`DispatchDecomposer.decompose` positional/kw-only mismatch).

**Discriminant:** **Theater** if `scripts/repro_cascade_decompose_contract.py` exits 0 with **LLM contacted: no** in dossier but closure still says "provider." **Not theater** if Failure Dossier states pre-network exception with `file:line` and HTTP 500 chain.

**Counter-example:** Live operator card run per `OPERATOR_VERIFY_CASCADE_DECOMPOSE.md` failing on HTTP 502 **after** contract repro green — provider hypothesis then allowed with separate Scope Map row `live-LLM-required`.

**Maps to:** F-equivalent in `HARD_TO_VARY.md` ("Provider down" when repro shows TypeError); **DispatchDecomposer** lineage.

---

### T-10 — FakeDecomposer-only proof

**Symptom:** "Cascade fixed" citing only `FakeDecomposer` / manual `sub_questions` tests while production bug was `DispatchDecomposer` adapter (`roles/cascade_planner/planner.py:57-69`).

**Discriminant:** **Theater** if no test imports production `DispatchDecomposer` and asserts kwargs to `render_full_prompt` / `dispatch`. **Not theater** if `tests/test_dispatch_decomposer*.py` or cascade light test stubs substrate seam with production import.

**Counter-example:** Tree planner regression via fake — valid **only** when Scope Map row for auto-decompose is explicitly `untested` with rationale, not when session claimed auto-decompose fixed.

**Maps to:** F-equivalent; egghead + ANT-H2V SPR-03/04 scope.

---

### T-11 — AMS anti-fiction path cite

**Symptom:** Sprint or handoff cites `components/ProductsLauncher.tsx`, `#scene-root`, `scene/index.ts`, or other paths that fail `git cat-file -e origin/main:<path>` without `NEW:` prefix.

**Discriminant:** **Theater** if `tsx tools/specs/verify_spec_refs.ts` on the HTML would fail. **Not theater** if path appears in `docs/ams-v2/verified-interfaces.md` as `VERIFIED` or is marked `NEW-to-build (SPR-XX)` with owning sprint.

**Counter-example:** AMS-v2 closure citing `apps/reading/src/scene/Scene.tsx` with Playwright spec named in `mountain-shell-v2-verification.md` — fiction class avoided.

**Maps to:** **F3** (unbounded green) + AMS-v1 fiction lineage; bridges SPR-05 `verify_execution_bundle.sh`.

---

### T-12 — Memory-without-signature contract lock

**Symptom:** Phase A claims "signature requires `investigation_id`" without pasted `inspect.signature` output; or "I read planner.py" with no line numbers matching current tree.

**Discriminant:** **Theater** if Failure Dossier signatures table empty. **Not theater** if A1–A4 complete per `HARD_TO_VARY.md` Phase A (repro exit recorded when sprint names script).

**Counter-example:** Dossier table row `dispatch` @ `substrate/dispatch/router.py:301` with `(*, investigation_id: str, …)` pasted from `.venv/bin/python -c "import inspect…"`.

**Maps to:** F-equivalent (memory-without-test); **DispatchDecomposer** contract bug is the reference lesson.

---

### T-13 — Mega-briefing replaces handoff

**Symptom:** Long orientation markdown (architecture essay, repeated pytest narrative, steelman prose) attached but no `TEMPLATES.md` handoff packet; operator must infer status from tone.

**Discriminant:** **Theater** if adversarial reader cannot find `### Status` and `### Not proved` in &lt;30s. **Not theater** if briefing is supplemental and packet is complete.

**Counter-example:** Egghead-style **short** handoff: 1-page Failure Dossier + Env Card + Gate table — diagnosis can be verbose elsewhere if packet stays mechanical.

**Maps to:** **F4** + **F3** — rejected alternative in ANT-EXEC master spec ("one mega handoff brief").

---

### T-14 — Hop/lag narrative without measurement

**Symptom:** Werner / ice-cursor work claims "snappy," "fixed lag," or "within budget" after hop-delay tuning (`ccb4c66`) without p95 sample artifact, vitest timing hook, or operator acceptance checklist.

**Discriminant:** **Theater** if only subjective UX adjectives. **Not theater** if `useMouseFollow` tests document `LAG_MS` / live-vs-lagged divergence **and** SPR-07 acceptance row satisfied or `### Not proved` states measurement debt.

**Counter-example:** Explicit fail: "p95 &gt;950ms on operator hardware; merge blocked per sprint-07-werner-adapter" — fails product bar but is **not** theater (falsifiable).

**Maps to:** **F5**; **ccb4c66** postmortem; Werner master spec replaces hop theater with bait/line/lag sample model.

---

## Mechanical gate (SPR-02)

```bash
rg -c '^### T-' docs/agent-execution/THEATER_TAXONOMY.md   # expect ≥ 12
```

---

## Related

| Artifact | Role |
|----------|------|
| `ADVERSARIAL_RUBRIC.md` | Binary audit rows referencing T-## |
| `HARD_TO_VARY.md` | Phase A–E + F1–F8 |
| `TEMPLATES.md` | Handoff headings that defeat T-04/T-13 |
| SPR-04 | `audit_agent_session.sh` grep for F-patterns |
| SPR-06 | `CASE_STUDY_CASCADE.md` worked example |