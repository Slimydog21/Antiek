# Personal document space — categories, filing, and the suggest-only boundary

**Date:** 2026-05-28
**Branch:** `caffen/lr-spr13`
**Source spec:** Read SPR-13 (personal document space + auto-categorization +
suggest-file-into-project + meta-docs tab), M1–M4
**Status:** built. The auto-categorization is shipped with a STATED stability
bound + an honest fallback (see below) — it is not claimed to "work" on a tiny
corpus, because it genuinely doesn't.

This is the record a maintainer six weeks out reads when they ask "why a
suggestion at 0.45 but not 0.6?", "why do categories disappear below 4 docs?",
or "why doesn't accept happen automatically?" — the answers are here, not in
chat.

---

## 1. Filing is SUGGEST-ONLY (accept files; decline leaves; never auto-ship)

**Decision.** The personal space CONTINUOUSLY SUGGESTS filing a created
deliverable / saved read into a semantically-matching research project. The
file only happens on an EXPLICIT user accept. Decline (dismiss) leaves the doc
exactly where it was. NO path auto-files.

**Why.** A wrong auto-file is absorbed by the reader, who later can't find a
doc that the system silently moved into a project they weren't looking at. A
suggestion the reader declines costs them one dismissal; an auto-file they
didn't want costs them a lost document. Asymmetric harm → suggest-only.

**How it's enforced (mechanical, not aspirational).**
- The match selector (`substrate/books/personal_space.py
  :match_document_to_investigations`) ONLY ranks — it never writes.
- The frontend is split into a PURE `suggestFiling` (shapes the suggestion) and
  an EXPLICIT-accept-only `acceptFiling` (the only mutator). `acceptFiling` is
  wired to a click; it is never called on render or in an effect. A vitest
  asserts the mutator is NOT called without a click and that declining fires
  nothing (`PersonalSpace.test.tsx`, `researchSuggestion.filing.test.ts`).
- Accept files into the ONE chosen project. When a doc matches >1 project the
  surface NAMES them and the reader picks one — `acceptFiling` never iterates
  over candidates, so there is no double-file / auto-ship-to-all.

**What would reverse it.** Nothing short of an operator decision that the
personal space should auto-organize on the reader's behalf. Even then the
single-writer + provenance constraints below stand.

## 2. Filing is a TYPED EVENT through the funnel, not a direct UPDATE

**Decision.** Accepting a suggestion emits a NEW typed event
`document.filed_into_investigation` (schema v21→v22). Its `/events/typed`
side-effect handler sets `documents.investigation_id` through the single-writer
funnel (`connect_write` = `runtime/db_lock`).

**Reuse-vs-new check (operator default 1).** I verified there is no existing
event that associates a document with an investigation: `documents.investigation_id`
is written only at ingest time; the seam events (`seam.read_to_research`) LAUNCH
a new investigation, they don't file an existing doc into an existing one. So a
new event is justified, not a duplicate.

**Why not a direct `UPDATE documents SET investigation_id`.** That bypasses the
only-writer invariant (the serialized host funnel through `runtime/db_lock` is
the sole graph writer). The handler does the write inside `connect_write`, so
filing rides the same funnel as every other mutation. A pytest
(`test_api_document_filing.py`) posts the event and then reads `GET /documents`
to confirm the column changed — tracing emit → handler → read end to end.

**Provenance (§9) preserved.** Filing is a LINK, not a copy: only
`investigation_id` is set. `ip_holder_id` is untouched (immutable on filing);
the chunk/claim chain (`claim→chunk→document→ip_holder_id`) is never rewritten.
The pytest asserts `ip_holder_id` is unchanged after a file. 1:N per the schema
(`documents.investigation_id`; a doc belongs to 0..1 investigation) — re-filing
MOVES the doc, it does not duplicate it.

## 3. Categories are SYSTEM-auto-labeled, with a stated stability bound

**Decision.** Categories EMERGE from semantic clustering of the personal-space
assets (`categorize_assets`): connected-components over a cosine-similarity
graph, each cluster named from its docs' salient terms (the
`documentsByTheme.themeTermsFromInvestigations` idiom). The SYSTEM names them;
the user never hand-organizes folders.

**The stability bound (rigor #1 — intellectual honesty).** Below
`MIN_ASSETS_FOR_CLUSTERING = 4` assets, clustering on embeddings is genuinely
unstable: a 2-asset "cluster" is as likely coincidence as theme, and the
salient-term label flips run-to-run on a tiny corpus. So below 4 we do NOT
fabricate clean labels — we ship a single honest **recency** bucket
("Recently read & created", newest first) and the surface SAYS so ("Sorted by
recency — categories kick in once you have 4+ readings"). The same fallback
fires if the embedding model can't be loaded. At/above 4, with embeddings that
separate themes, clustering is deterministic (the fixture test re-runs and
asserts identical labels + membership + ordering).

**Determinism.** Assets are processed in a stable order (sorted by `asset_id`);
the similarity graph is symmetric + threshold-based (same embeddings ⇒ same
edges ⇒ same components); union-find picks the lowest index as the component
root; salient-term ties break alphabetically. So the same docs produce the same
categories run-to-run — the fixture test asserts this (not "looks clustered").

**Who absorbs a wrong auto-label (rigor #2 — fairness).** The reader, who might
not find a doc filed under a category name they wouldn't have chosen. That is
exactly why the stability bound + the honest "recency" fallback + the visible
ordering label matter: we degrade to a stated, never-wrong order rather than
risk a confident wrong theme on a corpus too small to support one.

## 4. The clustering threshold — 0.55

`CLUSTER_SIMILARITY_THRESHOLD = 0.55`. Two of the reader's own deliverables join
the same category iff their cosine similarity is ≥ 0.55. Chosen conservative: it
groups genuinely-related deliverables (the same subject treated across reads)
without collapsing the whole space into one giant bucket (rigor #3 c). A
clustering mistake silently mis-labels (the reader absorbs it — §3 above), so
the bar to GROUP is set high.

## 5. The match (filing) threshold — 0.45

`MATCH_SUGGESTION_THRESHOLD = 0.45`. A doc is suggested for filing into a project
iff its similarity to that project's question is ≥ 0.45. Below 0.45 the doc and
the question share no real subject (cross-domain pairs embed under ~0.4 with the
MiniLM model the rest of Read uses), so a suggestion there is noise the reader
learns to dismiss; at/above it they're discussing the same thing.

It sits BELOW the 0.55 clustering threshold deliberately: filing into an
existing, user-NAMED project is a lower bar to clear than auto-grouping two of
the reader's own deliverables, because a filing suggestion is only ever OFFERED
(accept/decline) while a clustering mistake silently mis-files. A suggestion the
reader can wave away is cheaper than a wrong silent grouping.

**What would reverse the thresholds.** A different embedding model (the numbers
are calibrated to MiniLM `all-MiniLM-L6-v2`), or evidence from real usage that
0.45 surfaces too much noise / 0.55 over-splits. Both are single-constant edits
in `substrate/books/personal_space.py`.

## 6. Saved-reads scope

"Saved reads" are represented as `source.read` events (SPR-07 — the reader
dwelled on a source long enough to count as read; the dwell gate already
filtered these to genuine reads, so listing them is curated, not a raw dump).
They are cleanly enumerable from the event log (under the `read-{document_id}`
reading thread), deduped to the latest read per document. They are INCLUDED in
the personal space (M1) and EXCLUDED from the meta-docs tab (M4, which is
created-deliverables only). This was the verify-or-honestly-scope choice the
spec called out; saved reads turned out cleanly enumerable, so they're in.

## 7. Verified vs assumed

- **Verified:** the filing event sets `investigation_id` through the funnel
  (emit → handler → `GET /documents` read, pytest); the
  `investigation.start_requested` payload's `question` field is the project
  question (events.py + app.py `list_investigations` read it identically);
  determinism of clustering on a fixture (re-run + compare); decline files
  nothing (vitest).
- **Assumed (stated honestly):** clustering produces clean, stable category
  labels on the REAL corpus only AT SCALE (≥ 4 assets with separable themes).
  On the operator's current small corpus the honest **recency** fallback ships.
  The 0.45/0.55 thresholds are calibrated to MiniLM and to a keyword-semantic
  test stub; they have NOT been tuned against a large real corpus — the
  reconsider-if is real usage data.
- **Assumed (clustering determinism scope):** the fixture re-run+compare proves
  determinism against the keyword-semantic test stub. Against the real
  `SentenceTransformerEmbedding` it rests on one assumption — that `encode` is
  deterministic per input (same text → same vector). Given that, the cosine +
  union-find + alphabetical-tiebreak steps are pure-Python deterministic, so the
  clusters are too. The assumption holds for a fixed, locally-served MiniLM
  checkpoint; it would need re-checking if the embedder were swapped for a
  non-deterministic or remotely-served model.
- **Category labels are disambiguated, keyed by id.** Two distinct clusters can
  share top salient terms (same vocabulary, orthogonal embeddings). The label is
  disambiguated (next distinguishing term, then an ordinal) so no two categories
  read identically, and each category carries a stable unique `category_id` (the
  cluster's lowest asset_id) that the surface keys on — the human label is never
  a UI key, so a shared label can never drop a section.
