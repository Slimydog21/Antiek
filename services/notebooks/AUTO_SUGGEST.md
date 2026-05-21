# Auto-suggested themes — stub contract + unlock criteria

Status as of SPR-11 closeout (2026-05-21): **stubbed**, feature-flagged
off. The visible UI is an empty section with the copy
"Auto-suggested themes will appear when your library has more
notebooks." NO lorem-ipsum, NO fake suggestions; the future
engineer flipping the flag must read this doc first.

## Why the stub exists at all

The Wrestle Evolution master spec's three-tier notes model (Tier 1
behavior events → Tier 2 per-doc notebooks → Tier 3 per-theme
rollups) locks the position that hand-curation is the cold-start
answer for Tier-3 theme construction. Auto-clustering across Tier-2
notebooks is the AI-native answer to the same question — but
shipping it from day one would (a) produce noise on a small corpus
and (b) skip the curation discipline that IS the cold-start
training data for the eventual topic model.

The stub is shipped, not just planned, because:

1. **It locks the surface.** The index page reserves room for the
   section so future activation is a one-component swap rather
   than a redesign.
2. **It documents the contract.** This file is the spec the topic
   model must fulfill. Without it, the future engineer is guessing.
3. **It surfaces the gate honestly.** Operators clicking through
   see an explanatory copy block and the unlock criteria, not a
   broken feature.

## Unlock criteria

Both must be true before flipping `AUTO_SUGGEST_THEMES_FLAG` to
`true`:

### Criterion 1 — Tier-2 notebook count ≥ 10k

Below ~10k Tier-2 notebooks, any unsupervised clustering is going
to produce a single mega-cluster or wildly overconfident small
clusters. The 10k number is calibrated against the SPR-08 reward
proxy expected scale (cf. `substrate/behavior/REWARD_PROXY.md`):
the medium-horizon backfill stabilises at roughly that corpus
size, which is also when the operator has built up enough
hand-curated theme exemplars to evaluate cluster quality.

**Verification query** (run before flip):
```sql
SELECT COUNT(*) FROM notebook_documents WHERE user_id = ?;
```
If `< 10000`, do NOT flip. The flag is a one-line change; reverting
it is also a one-line change, but a flag-on flag-off cycle visible
to the operator counts as a broken-feature signal.

### Criterion 2 — Topic model passes operator review

Whichever topic-model implementation eventually ships (off-the-
shelf BERTopic, custom LDA, embedding-based clustering, etc.)
must pass two reviews before flip:

- **Holdout review:** the operator manually curates 5 themes on
  a fresh subset, then asks the topic model to cluster the same
  subset. ≥3 out of 5 clusters should overlap with operator-
  curated themes by ≥70% block-level Jaccard. If `<3`, the model
  isn't ready.
- **Stability review:** running the topic model twice on the same
  corpus (with the same random seed) must produce identical
  clusters. A stochastic model that drifts between runs is
  unusable for a UI surface — operators see suggestions move
  between sessions and stop trusting the system.

Both reviews live as runnable scripts under
`tools/auto_suggest_review/` when the topic model is integrated.

## Contract — what the topic model must emit

The surface (`apps/reading/src/modes/Notebook/SuggestedThemes.tsx`)
reads from a writer that supplies the following shape per cluster:

```ts
interface SuggestedTheme {
  cluster_id: string;       // stable across re-runs (criterion 2)
  title: string;            // 2-6 word human-readable summary
  rationale: string;        // 1-2 sentence explanation
  confidence: number;       // [0, 1]; the surface dims cards < 0.5
  source_block_ids: string[]; // Tier-2 blocks in the cluster
}
```

Where the writer lives is the topic-model owner's choice; the
expected location is a new
`services/notebooks/topic_model.py` module that exposes
`def suggest_themes(user_id: str) -> list[SuggestedTheme]`. The
API endpoint that wraps it is
`GET /api/themes/suggested?user_id=...`; until the model lands,
the endpoint returns `[]` and the surface shows the stub copy.

## Feature flag location

`apps/reading/src/modes/Notebook/SuggestedThemes.tsx` —
`AUTO_SUGGEST_THEMES_FLAG`. It's a module-level constant rather
than a runtime config because:

1. **No accidental flips.** A constant requires a code edit + a
   PR + a code-review approval. A runtime config can be flipped
   by an operator dashboard click.
2. **The gate is procedural.** Whoever edits the constant is also
   the person reading this file and confirming both unlock
   criteria. The two acts are coupled.
3. **Bundle size.** A flag-off branch is dead code the bundler
   tree-shakes; a runtime flag keeps both branches in the bundle.

Future engineers: when flipping, do all of:

- [ ] Verify Criterion 1 query returns ≥ 10000.
- [ ] Verify Criterion 2 reviews pass (holdout + stability).
- [ ] Wire `GET /api/themes/suggested` to your topic-model
      writer.
- [ ] Add an integration test in
      `services/notebooks/tests/test_topic_model_contract.py`
      asserting the returned shape matches `SuggestedTheme`.
- [ ] Update this file's "Status" line to "live".

## Why this gate matters

The operator-as-curator IS the product during cold-start. A
flag-on with a half-baked topic model degrades the curatorial
signal that the eventual production model will train on. Worse,
it teaches the operator to ignore the suggestion panel, which
poisons the affordance for the long term.

The stub copy on the surface ("Auto-suggested themes will appear
when your library has more notebooks.") makes the deferral
visible to the operator without lying about future capability.
Flipping the flag prematurely breaks both halves of that
promise.

## Out-of-scope for this stub (revisit when criteria pass)

- Cluster-level merge UI (operator dragging two suggested
  clusters together).
- Confidence-threshold tuning UI.
- Cross-user theme suggestions (multi-user is out of scope per
  the SPR-11 spec).
- Auto-promotion (clusters becoming themes without operator
  approval). The "Promote all" affordance the contract supports
  is a single click by the operator — never automatic.
