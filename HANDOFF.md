# Lane: `research_only` — the derivable-only rights state

Branch `lane/rightsonly-20260920`, worktree `/tmp/lane-rightsonly`, based on `ebc5996ad`.

## Step 0 — the gap was still open

```
$ grep -rn "research_only" --include='*.py' substrate/
(no output)
```

Widened beyond the brief's grep, since one string match is weak evidence:

```
$ grep -rn "research_only\|research-only\|researchOnly" --include='*.py' --include='*.ts' --include='*.tsx' --include='*.sql' --include='*.md' .
tools/serve_gate_audit.py:50:       or is owner/research-only (legitimately ungated) is a §9.0 privilege
tools/serve_gate_audit.py:136:    #: consumer (a leak) or is owner/research-only (legitimately ungated) is a
docs/master-product-spec.md:1518:  ads invites a different legal response than research-only
docs/master-product-spec.md:2593:use covers research-only use; not monetized distribution).
```

Four prose mentions, no state. Built.

## Where this state sits among the ones that already exist

The rights model turned out to be five states over `documents.content_class`, not
the three the spec prose implies:

| state | publicly servable | owner-readable | default excerpt | earns | trainable | citable |
|---|---|---|---|---|---|---|
| `public_domain`, `user_owned`, `user_public_contribution`, `opt_in_licensed`, `source_declared_open` | yes | yes | full body | varies | yes | yes |
| `restricted_pending_opt_in` | no | no | 500-char snippet | accrues to escrow | no | yes |
| `personal_reading` | no | **yes, in full** | none | never | no | no |
| `research_only` **(new)** | no | **never** | **0 by default, per-tier** | never | no | **yes** |
| NULL (legacy) | grandfathered | — | — | — | — | no |

`research_only` is the mirror image of `personal_reading`, which is exactly why it
could not reuse it. `personal_reading` is owner-readable and publicly non-servable;
this one is never-owner-readable and derivable-only. Folding them together would
widen the owner-read privilege onto content that was never licensed to be read —
the §9.0 leak the state exists to close. The buyer of a discounted ingestion **is**
the owner, so the owner path is precisely the one that has to refuse.

Its nearest neighbour on the retrieval axis is `restricted_pending_opt_in` (body
withheld, reachable only on a privileged tag), and it differs there on two axes
that matter commercially: the gated class yields a 500-char snippet by default and
accrues to escrow, while this one yields nothing by default and accrues nothing.

## What changed

- **`substrate/constants.py`** — `RESEARCH_ONLY_CONTENT_CLASS`, added to
  `NON_TRAINABLE_CONTENT_CLASSES`, new `research_derivable_only` presentation
  status. Three import-time assertions: not servable, **not owner-readable**, not
  TurboPuffer-indexed. The owner assertion is the one that keeps this state from
  collapsing back into `personal_reading`.
- **`substrate/rights/research_only.py`** (new) — the per-tier quotation policy.
  Named tiers `derived_only` (0), `brief_quotation` (200), `snippet_parity` (500),
  read off `documents.metadata`, with a bespoke per-work character count that
  overrides the tier. Deny-by-default on anything absent, malformed or
  unrecognised, and every resolved cap clamped to `SERVE_SNIPPET_MAX_CHARS`. **The
  knob only ever tightens** — that clamp is what keeps invariant 1 true in the
  presence of a knob at all.
- **`substrate/books/servability.py`** — `RESEARCH_DERIVABLE_ONLY`, a distinct
  branch, absent from `_SERVABLE_STATUSES`. The existing drift assertion is
  untouched.
- **`substrate/books/serve.py`** — the refusal branch, placed immediately after
  takedown and **before** the owner branch. It does not read `owner` at all, so
  there is no owner-shaped hole for a later edit to widen.
- **`substrate/graph/retrieval_gate.py`** — `RESEARCH_ONLY_CONTENT_CLASSES`, folded
  into `_NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES`; `is_chunk_body_withheld` returns
  `(True, "research_only")` unconditionally. Kept as its own set rather than joining
  `PERSONAL_ONLY_CONTENT_CLASSES`, because that set is granted to a matching
  `owner_user_id` on the privileged branch and this class must never take that grant.
- **`substrate/collective_graph/eligibility.py`** — added to
  `NON_ATTRIBUTABLE_CONTENT_CLASSES`; left out of `PUBLIC_GRAPH_CONTENT_CLASSES`.
  It neither accrues nor pays. See "no money path" below.
- **`substrate/rights/register.py`** — added to `VALID_CONTENT_CLASSES` so a source
  can be stamped with it.
- **`tools/codegen/chunk_provenance.py`** — `research_only` is deliberately **absent**
  from `NON_CITABLE_CONTENT_CLASSES`, and `provenance_policy_errors()` now pins both
  halves: citable, and withheld everywhere a body could travel.
- **`substrate/corpus_audit.py`** — new standing check `research_only_withheld`.
- **`tests/test_research_only_rights_state.py`** (new) — 45 tests.

## The two invariants

**1. No serve path returns a `research_only` body.** The paths were found by
tracing callers of `serve_full_text` and readers of `documents.raw_text`, not from
the brief's list. Asserted: `serve_full_text` (public **and** owner),
`serve_full_text_guarded` (both), `guard_candidate_full_text`,
`guard_document_candidate_full_text`, the `twin_source_envelope` column,
`serve_reader_html` (the second body store, both paths), `build_research_seed`
(including the case where the *caller* supplies the body as `passage_text`),
`curate_reading_list`, `is_chunk_body_withheld`, `graph.search` on the public tag,
and `rights_audit.audit_batch`. Each body assertion serializes the whole result and
scans for a sentinel, so a leak through a field nobody named still fails.

**2. A derived claim citing a `research_only` chunk renders its provenance without
leaking the body.** Asserted on all three projection adapters (synthesis, notebook
resolver, deliverable): the claim and the citation identity (title, ip_holder,
locator) survive, the passage is absent from the serialized doc-model entirely —
absent, not merely hidden in rendered HTML, since an island carries whatever the
model carries. Plus `is_chunk_citable('research_only') is True`.

Two tests exist to stop the suite passing vacuously: `graph.search` on
`private_research` **must** reach the chunks (a state nothing can retrieve derives
nothing, and the product is gone), and the owner full-read of `personal_reading`
**must** still return the body.

## The tests bite — mutation-checked, not assumed

I removed the serve branch and folded the class into the owner lane, i.e. the exact
regression this state exists to prevent:

```
7 failed, 35 passed
FAILED ...test_serve_full_text_withholds_body_on_both_paths[True]
   - AssertionError: assert 'PUBLISHER-CONFIDENTIAL-INTERIOR the licensed interi...
FAILED ...test_reader_html_sidecar_withholds_a_research_only_body
   - AssertionError: owner reader-HTML released a research_only body
FAILED ...test_no_serve_result_field_ever_carries_the_body
   - AssertionError: ServeResult.full_text carried the research_only body on the...
```

The mutant also exposed the secondary failure mode the distinct status prevents:
it fell through to `gated_metadata_only` and served 500 characters of the work as a
"snippet". Restored; 45/45 green.

The standing audit check is falsifiable the same way — one test plants an
owner-path leak and one plants an over-cap quote, and both go red.

## Scope held: no money path was touched

Purchasing, payment and publisher onboarding were not built. The state is
deny-by-default on **both** money sets: absent from `PUBLIC_GRAPH_CONTENT_CLASSES`
(never accrues) and present in `NON_ATTRIBUTABLE_CONTENT_CLASSES` (never pays).
That is tightening, not routing — no accrual, no disbursement, nothing for §9.0
counsel to unwind. It is also the commercially correct default: the consideration
here is the discounted ingestion fee, and ad revenue does not exist yet, which is
the premise of the product. If counsel later ratifies an accrual basis, widening a
class that earns nothing is easy; unwinding escrow that accrued on terms nobody
agreed to is not.

## Corrections to the brief

The brief was accurate on the gap and the design. Two notes:

1. **The brief's file list was incomplete, as it warned it might be.** Tracing found
   two body surfaces beyond `substrate/rights/`, `substrate/legal_gate/`,
   `middleware/source_tier/` and `substrate/rights_audit.py`: the reader-HTML
   sidecar (`substrate/reader_html/store.py`, a second body store) and the
   `twin_source_envelope` column, which `insert_document` derives via
   `guard_candidate_full_text(owner=True)` — an owner-path body decision made
   outside the serve gate. Both are asserted.

2. **`middleware/source_tier/` is not the right tier vocabulary for this knob.** It
   is a 1–5 *evidence-trust* classifier keyed off `document_type`. Keying a
   quotation cap to it would tie a licence term to how trustworthy a document looks,
   which is a category error. The quotation tier is a deal term and lives on the
   document, keyed by its own vocabulary.

## Commands run

```
$ python -m pytest tests/test_research_only_rights_state.py -q
45 passed in 4.68s

$ python -m pytest <20 related suites> -q
259 passed, 1 warning in 34.66s

$ python -m tools.lints.declared_bar enforce ruff --baseline-file tools/lints/baselines/declared_ruff.json
exit=0

$ python -m tools.lints.declared_bar enforce mypy --baseline-file tools/lints/baselines/declared_mypy.json
exit=0

$ python -m mypy --strict <changed modules> | grep <my files>
(no errors in changed files; the 240 reported are pre-existing in transitively
 imported acquisition/books/*, all baselined)

serve_guard_check: PASS   serve_invariants_check: PASS   retrieval_gate_check: PASS
register_check: PASS      owner_privilege_check: PASS    owner_boundary_check: PASS
boundary_check: PASS
```

No existing test was weakened, skipped, xfailed or deleted. The arXiv selection was
not run. Docker was not started.

## Left for later, deliberately

- **No UI.** `apps/reading/src/generated/contracts.ts` carries a `ContentClass`
  Literal that already lags by one — `personal_readable` is not in it either. Only
  *servable* statuses must be representable there (`substrate/contracts/servable.py`
  asserts `FULL_TEXT_SERVABLE <= _CONTENT_CLASS_MEMBERS`), and this status is not
  servable, so the assertion holds and no codegen change was needed. A surface that
  renders "derivable-only" distinctly from "gated" is a separate lane.
- **No ingestion path sets this class yet.** `register_source_document` accepts it;
  which connector stamps it, and on what evidence of a deal, is a §9.0 call.
- **Writing a deal onto a document.** The policy is read from `documents.metadata`;
  no operator surface writes it. A publisher-terms writer belongs with onboarding,
  which is gated.
- **`TRAINING_EXPORT_TABLES` is still empty**, so the non-trainable membership is a
  forward-guard for this class exactly as it is for `personal_reading`.
