# SPR-10 — thin reachable flywheel surface (reuse provenance)

**Decision date:** 2026-06-01
**Status:** ✅ Active (shipped behind real data — present-only, renders nothing until a run reuses prior knowledge)
**Owner:** SPR-10 (Antiek Flywheel Foundation)
**Scope:** read-only display logic in `apps/reading/` — no events emitted, no source bodies read, no agents run.

SPR-10 makes the research-depth flywheel **felt** by the reader: when a completed
investigation reused prior knowledge, the synthesis surface shows a quiet
"reuse provenance" footnote (which prior insights were reused, linked to the
prior investigations they came from) plus a one-line compounding stat. It is the
explicit **anti-re-spec** sprint — the cited-synthesis viewer
(`MasterMdViewer.tsx` + `synthesisParser.ts` + `ChunkModal.tsx`) already ships;
this sprint **composes/extends** it (zero new components, zero new routes).

## The §5 voice ruling — why a footnote, not a dashboard

The reuse affordance is a collapsed `<details>` block in the **same calm audit
register** as the existing `Appendix` (falsification / risks / constraints) — same
classes (`text-shadow-1 dark:text-moonlight` summary, `text-ink-soft
dark:text-starlight` headings), same collapsed-by-default posture. It is a
**sibling of `Appendix`**, placed right after it in the article body, not a hero
banner above the thesis.

**The precedent it copies is the §14.4 `qualityScore` cue**
(`renderHeaderQualityCue`, MasterMdViewer.tsx ~line 315; parsed at
synthesisParser.ts ~line 263): a typed-optional field on `ParsedSynthesis`,
parsed from a persisted event, rendered as a quiet cue when present and as
**nothing** when absent. SPR-10 follows it exactly:

- **Present-only (the cardinal discipline).** When a run reused nothing —
  `reuseProvenance` empty **and** `compoundingStat` null — `ReuseProvenance`
  returns `null` and renders **nothing at all**, byte-identical to the
  pre-SPR-10 render. There is no zeroed "0 insights reused" placebo. This is the
  same discipline `qualityScore === null` enforces ("rather than guess a value").
  The SPR-02 byte-equivalence test and the `lostpixel` visual-regression
  snapshots are therefore unaffected on the no-reuse path.
- **No SaaS chrome.** No percentage-up arrows, no streak/fire chrome, no
  animated counter, no big-number card, no emoji. The wording is declarative and
  sourced ("reused N insights · …"). `npm run lint:tokens` stays green (no new
  hex literals).

This ruling is the thing a future agent would otherwise re-litigate ("make the
win pop"). The answer is on the record: the surface earns its place by being
**minimal and honest**, not loud — the same call the `qualityScore` cue made.

## The honest M4 no-source finding — `avoided` / `fewerSources` have NO per-investigation source

The spec's headline is "reused N insights · avoided M re-derivations · K fewer
sources than cold". Only the **first** number has a real per-investigation
source today:

- **`reused` (N) is REAL.** It is the count of reused units from the persisted
  `knowledge.reused` event(s) (`reused_unit_ids.length`, unioned across all such
  events — an investigation may emit more than one).
- **`avoided` (M) and `fewerSources` (K) have NO per-investigation source.**
  They require a **cold-baseline comparison**. SPR-09 built
  `compounding/benchmark/` — a **cross-arm benchmark over a frozen question
  set**, NOT a per-investigation measurement event. A search of the generated
  `ActionType` union confirms there is **no `compounding.measured`** (or any
  per-run compounding) action type on the substrate. The unrelated "SPR-09
  compounding flywheel" (the *suggested-next-research* daemon lane in
  `api/research.ts` / `SuggestedResearch.tsx`) is a **different spec's SPR-09**
  (name collision) and is **NOT** this measurement source — we did not wire to it.

Consequently:

- The client **never computes** `avoided` / `fewerSources` (no cold-baseline
  arithmetic, no source-count subtraction — a grep gate proves this; the three
  numbers are read fields only).
- `compoundingStat.avoided` / `.fewerSources` parse from a **per-run measurement
  event IF one is ever emitted** (the `CompoundingMeasuredPayloadShape` seam,
  action type `compounding.measured`), and are **null** until then.
- **`compoundingStat` is null unless a per-run MEASUREMENT event was persisted**
  (M4: "typed optional, null when no measurement"; "with the measurement absent
  the stat line is not in the DOM"). The reused **count** is surfaced by M3's
  `reuseProvenance` list (one entry per reused insight) — it is **NOT**
  synthesized into a "reused N" stat line from the `knowledge.reused` count,
  because a stat line without a measurement would imply one happened. So with
  reuse but no measurement: the list renders, the stat line does **not**. When a
  measurement IS present, the line renders only the clauses whose number is
  non-null — and a `{reused:0}` stat with no other number renders nothing (no
  "0 insights reused" placebo). *(This was tightened in the SPR-10 sharpen round:
  the first build gated the stat on `compoundingPayload || reuseProvenance.length
  > 0`, which rendered a "reused N" line without a measurement — a deviation from
  M4's criteria, now corrected to gate on the measurement event alone.)*

**Non-vacuity is proven anyway.** A synthetic `compounding.measured` fixture
(`{reused: 3, avoided: 2, fewer_sources: 5}`) drives the full three-number render
path in the tests, so the render is provably non-vacuous even though no real
source emits it yet. This mirrors SPR-09's honest null: the seam is live, the
data is not.

**Reconsider-if.** When a per-investigation compounding measurement event is
added to the substrate (a real `compounding.measured` with a sourced cold-baseline
delta), point the parser's `compounding.measured` branch at the real action type
(promote it into the `ActionType` union) — the render path already consumes it.
Until then, M / K stay null and absent. (Open question for SPR-11 / operator: is
the per-run measurement a persisted event or an API field? The seam assumes a
persisted event, matching the rest of `parseSynthesis`.)

## The no-label-in-payload handling

`KnowledgeReusedPayload` (generated/types.ts:624) carries **no human label/title**
for a reused unit — only `reused_unit_ids[i]`, `scores[i]`, and
`source_investigation_ids[i]` (parallel arrays). So each `ReusedInsight` carries
exactly the **real identifiers we have**: the `unitId` and the
`sourceInvestigationId`. The viewer renders `prior insight {unitId}` as the link
text — **never a fabricated human title** (rigor #1). A shorter parallel array
degrades to `null` (honest "unknown origin/score"), never a guess.

## The reachability chain (SPR-01 gate)

The reuse affordance is reachable, and adds **no orphan**:

1. The synthesis it lives in is reached via the existing route
   `App.tsx:107` — `<Route path="/inv/:investigationId" …>`. That route has many
   inbound navigators (e.g. `StartResearch.tsx:326`, `SuggestedResearch.tsx:177`,
   `ChatInputArea.tsx:60`), so it is **not** an orphan.
2. Each reused-insight link is a plain semantic
   `<a href="/inv/:sourceInvestigationId">` → the **same existing** `/inv/:id`
   route. No new route is introduced; the link merely adds another inbound
   reference to a live route. The `reachability_gate.py` (SPR-01) flags NEW
   zero-importer modules and NEW no-inbound-link routes — SPR-10 introduces
   neither (zero new modules, zero new routes), so it is gate-clean.
3. A test (`MasterMdViewer.test.tsx`) asserts each rendered reuse link's `href`
   matches `^/inv/`.

When a reused unit has no known source investigation, its entry renders as plain
text (not an `<a>`) — an honest "no origin recorded", never a dead link to a
missing route.

## §9.0 — reuse links do not bypass the serve gate

A reuse link **navigates** to the prior investigation's own `/inv/:id` synthesis
surface; it does **not** fetch or display a withheld source body. It uses a plain
`<a href>` (mirroring `ChunkModal`'s `OpenInDocumentButton`), with **no**
`getChunk` call. Source-opening anywhere in the viewer still flows through the
existing §9.0-gated `getChunk` path (unchanged). The serve gate is not relaxed.

## a11y (axe) — authoritative check is CI, not the build session

The affordance is semantic markup — a collapsed `<details>/<summary>` with a
`<ul>` of `<a>`/`<span>` — reusing the exact token classes of the already-passing
`Appendix` (no new colour, no image-without-alt, no role hacks). The project's
`@axe-core/playwright` gate runs in CI on this frontend change and is the
**authoritative** a11y check. It was **not** run locally in the build session (no
story/browser harness was exercised), so it is a known-unrun-locally gate — not
asserted green by hand; the CI axe-core run is the real verification.

## Files touched

- `apps/reading/src/lib/synthesisParser.ts` — `ReusedInsight` + `CompoundingStat`
  types; `reuseProvenance` + `compoundingStat` on `ParsedSynthesis`
  (`EMPTY_SYNTHESIS` inits `[]` / `null`); parse from `knowledge.reused` (union
  across events) + the `compounding.measured` seam.
- `apps/reading/src/modes/ResearchWorkstation/MasterMdViewer.tsx` — the
  `ReuseProvenance` render (present-only) + `compoundingStatLine` + the
  `/inv/:id` prior-insight links.
- `apps/reading/src/lib/synthesisParser.test.ts` — M2/M4 present/empty
  non-vacuity cases.
- `apps/reading/src/modes/ResearchWorkstation/MasterMdViewer.test.tsx` — M3/M4/M6
  present/empty + reachable-link (`href` matches `/inv/`) cases.
- `apps/reading/src/modes/Notebook/deriveAutoNotebook.test.ts` — fixture updated
  for the two new `ParsedSynthesis` fields (type-driven, no behaviour change).
