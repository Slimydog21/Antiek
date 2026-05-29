"""SPR-05 — cross-path §9.0 servability polarity agreement.

The chunk/search path (``substrate/graph/search.py``) and the book
full-text path (``substrate/books/serve.py``) read the SAME
``documents.content_class`` column. Before SPR-05 they diverged in
polarity: the book path was a deny-by-default ALLOWLIST (NULL / unknown →
gated, not servable), while the chunk path was a DENYLIST whose
``content_class IS NULL OR content_class NOT IN (RESTRICTED_CONTENT_CLASSES)``
clause let a NULL or unrecognised class *pass*. That was a live fail-open
on the search surface.

This test proves the two paths now AGREE on full-text servability for
every ``content_class`` — including ``None``/NULL and an explicitly
unrecognised literal, both of which MUST be DENIED on both paths. It
checks agreement at two levels:

1. the in-memory predicates (``chunk_full_text_servable`` vs
   ``is_servable_full_text(servability_of(...))``), and
2. the live SQL paths (``search`` vs ``serve_full_text``) against a
   DuckDB seeded with one document+chunk per class.

It also carries an explicit non-vacuity guard (G-B): a simulation of the
old denylist clause makes the chunk path disagree with the book path on
NULL/unknown, which reds the agreement assertion. So the test cannot pass
vacuously — reintroducing the fail-open would break it.

================================================================================
LEGAL-REVIEW CHECKLIST — operator (the §9 gate owner) signs before merge
================================================================================
The PR description references this block. The merge is gated on the
operator's sign-off; no code path merges automatically.

  [ ] 1. STRICTENING: the change can only REMOVE access, never grant it.
         The chunk gate moved from a denylist (NULL/unknown PASSED) to a
         deny-by-default allowlist routed through the owned predicate, so
         the post-state is a strict subset of the pre-state. Restricted,
         NULL, and unknown classes are now denied where some previously
         passed; no class newly gains access.
  [ ] 2. CARVE-OUT: NONE NEEDED (SPR-05 M2 option (b)). Documented at the
         chunk gate in substrate/graph/search.py (search()'s §9.0 block).
         A NULL-grandfather is the blanket fail-open §9.0 forbids, not a
         finite named set, so no legacy_chunk_grandfathered branch is
         created; legitimately-servable legacy docs re-enter the allowlist
         via the Sprint 18 ip_holders content_class backfill (on
         provenance, never on a NULL hole).
  [ ] 3. NULL content_class DENIED on both chunk and book paths
         (test_null_denied_on_both_paths + live-SQL assertions).
  [ ] 4. UNKNOWN/unrecognised content_class DENIED on both paths
         (test_unknown_literal_denied_on_both_paths + live-SQL).
  [ ] 5. BLAST RADIUS — substrate change confined to the gate + owned
         predicate, plus one required private-research call-site fix and
         two test updates recording the strictening:
            substrate/graph/search.py            (chunk gate → allowlist)
            substrate/books/servability.py       (owned predicate exposed)
            interfaces/research/api/grounding.py  (grounder → private_research;
                                                    see note below)
            tests/test_servability_polarity.py    (NEW: cross-path proof)
            tests/test_graph.py                   (search-mechanics docs seeded servable)
            tests/test_retrieval_time_gate.py     (legacy-NULL now DENIED)
         ZERO payout / Stripe / G2 / G3 / attribution-compute files touched
         (verified: git diff --name-only origin/main).
  [ ] 6. POLARITY TEST GREEN + NON-VACUITY demonstrated (G-A + G-B):
            pytest tests/test_servability_polarity.py -v        # 23 pass
            # fail-before: restore "... IS NULL OR NOT IN (...)" on the
            #   chunk gate → the live-SQL agreement tests FAIL (3 red).
            # pass-after: revert → 23 pass. Non-vacuity proven.
  [ ] 7. DIVERGENCE WITH SPR-08 — RECONCILE BEFORE SIGNING. A parallel
         Foundation effort reached the OPPOSITE answer on the same §9.0 gate,
         and the §9 gate owner is being asked to ratify both. Read the
         divergence note immediately below and decide which design is canon
         (this SPR-05 / NULL-denied, or SPR-08 / NULL-grandfathered) before
         signing — do NOT ratify two contradictory §9.0 gates.
            - SPR-08 ("§9.0 servability polarity unification — chunk+book+
              ATTRIBUTION") lives ONLY on the dead-v1 branch
              foundation/integration. Its chunk gate is
                AND (d.content_class IS NULL OR d.content_class IN (
                     CHUNK_SERVABLE_CONTENT_CLASSES))
              i.e. it KEEPS NULL servable via a named
              legacy_chunk_grandfathered carve-out, and it ALSO hardens the
              money/attribution path (substrate/attribution/compute.py) to
              deny-by-default — a fail-open SPR-05 deliberately leaves
              untouched (out of scope).
            - SPR-05 (this branch) makes the opposite ratified-looking call:
              NULL DENIED, carve-out NONE-NEEDED, compute.py untouched.
            - Why this is NOT a merge blocker for SPR-05 (verified):
              Foundation v2's index.html mandates "per-sprint direct PRs to
              main, no integration branch"; foundation/integration is NOT an
              ancestor of origin/main; and SPR-08's symbols
              (CHUNK_SERVABLE_CONTENT_CLASSES / legacy_chunk_grandfathered /
              the compute.py polarity) are ABSENT from origin/main — its fix
              never shipped. SPR-05's correct baseline is origin/main @
              5413fdc, not the stale foundation/integration. The task's
              "diff against foundation/integration" instruction was a
              stale-baseline assumption, not a property of the code.
            - Operator decision owed before sign-off: (a) does NULL get
              denied (SPR-05) or grandfathered (SPR-08)? and (b) does the
              attribution money-path (compute.py) get the deny-by-default
              hardening SPR-08 did and SPR-05 leaves fail-open? Both questions
              are §9.0 / Sprint-18-legal-gate decisions for the §9 gate owner.

  ___ operator sign-off (date / initials) ______________________

NOTE on grounding.py (item 5): the deny-by-default strictening would
otherwise make the claim-grounder return zero chunks for every wrestled
document whose content_class is still NULL (wrestling-loaded docs start
NULL until the tier/class assigner refines them). The grounder is the
operator's own personal-research path (it validates claims against the
document the operator is actively wrestling), never an ad-attribution /
money surface — so it is moved onto the pre-existing privileged
policy_tag='private_research' §9.0 bypass.

  HONEST DELTA — this is NOT merely "restoring prior behavior": the
  private_research tag is in PRIVILEGED_POLICY_TAGS and so SKIPS the §9.0
  chunk gate entirely, which grants STRICTLY MORE than the grounder's old
  default 'attribution_eligible' tag. Under the prior denylist that default
  admitted NULL but EXCLUDED restricted_pending_opt_in; private_research
  re-admits NULL AND ALSO admits restricted_pending_opt_in on the grounder.
  The widening is bounded to the operator's single wrestled document (the
  grounder's search is document_id-scoped) and re-opens the gate on NO
  attribution-eligible surface. The §9 gate owner should ratify this
  widening of the operator-only grounder path explicitly, not as a no-op.
  It is a call-site fix, not a policy or gate-polarity change.
================================================================================
"""

from __future__ import annotations

import os
import tempfile
from typing import Optional

import pytest

from runtime.db_lock import connect_write
from substrate.books.serve import serve_full_text
from substrate.books.servability import (
    is_content_class_servable_full_text,
    is_servable_full_text,
    servability_of,
)
from substrate.graph.schema import init_database
from substrate.graph.search import (
    chunk_full_text_servable,
    search,
)

# Every content_class in the documents vocabulary (schema.py §18 CHECK +
# substrate/constants.py), plus the two adversarial cases the gate must
# deny: a NULL/None class and a literally-unrecognised value.
KNOWN_CONTENT_CLASSES: tuple[str, ...] = (
    "public_domain",
    "opt_in_licensed",
    "source_declared_open",
    "user_owned",
    "user_public_contribution",
    "restricted_pending_opt_in",
)
UNKNOWN_LITERAL = "totally_unknown_class"
# Full enumeration the polarity test sweeps: known classes + NULL + unknown.
ALL_CASES: tuple[Optional[str], ...] = KNOWN_CONTENT_CLASSES + (None, UNKNOWN_LITERAL)


class _StubEmbedding:
    dimension = 4

    def encode(self, text: str) -> list[float]:
        h = sum(ord(c) * (i + 1) for i, c in enumerate(text)) or 1
        return [
            float(h % 7) / 7.0,
            float((h >> 3) % 11) / 11.0,
            float((h >> 5) % 13) / 13.0,
            float((h >> 7) % 17) / 17.0,
        ]


def _book_path_servable(content_class: Optional[str]) -> bool:
    """The book full-text path's verdict, in-memory."""
    return is_servable_full_text(servability_of(content_class))


# ---------------------------------------------------------------------------
# Level 1 — in-memory predicate agreement, class by class
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cc", ALL_CASES)
def test_chunk_and_book_predicates_agree_per_class(cc):
    """For every class (incl. NULL + unknown) the chunk-path predicate and
    the book-path predicate return the SAME full-text-servable verdict.
    Agreement is asserted one class at a time, so a single divergent class
    reds the suite (rigor: no aggregate-only check)."""
    chunk = chunk_full_text_servable(cc)
    book = _book_path_servable(cc)
    assert chunk == book, (
        f"chunk/book servability disagree for content_class={cc!r}: "
        f"chunk={chunk} book={book}"
    )
    # The chunk predicate must delegate to the owned predicate, not a copy.
    assert chunk == is_content_class_servable_full_text(cc)


def test_null_denied_on_both_paths():
    """Dedicated assertion (rigor card 3): NULL/None DENIES on both paths."""
    assert chunk_full_text_servable(None) is False
    assert _book_path_servable(None) is False


def test_unknown_literal_denied_on_both_paths():
    """Dedicated assertion: an unrecognised literal DENIES on both paths."""
    assert chunk_full_text_servable(UNKNOWN_LITERAL) is False
    assert _book_path_servable(UNKNOWN_LITERAL) is False


def test_known_servable_classes_pass_on_both_paths():
    """No regression: every legitimately-servable class still passes on
    both paths (the strictening only removes access for NULL/unknown/
    restricted, never for established servable provenance)."""
    for cc in ("public_domain", "opt_in_licensed", "source_declared_open",
               "user_owned", "user_public_contribution"):
        assert chunk_full_text_servable(cc) is True, cc
        assert _book_path_servable(cc) is True, cc


def test_restricted_denied_on_both_paths():
    """restricted_pending_opt_in is full-text gated on BOTH paths."""
    assert chunk_full_text_servable("restricted_pending_opt_in") is False
    assert _book_path_servable("restricted_pending_opt_in") is False


# ---------------------------------------------------------------------------
# Level 2 — live SQL agreement (search() vs serve_full_text()) per class
# ---------------------------------------------------------------------------


@pytest.fixture
def db_one_doc_per_class():
    """A DuckDB seeded with one document + one chunk for every case in
    ALL_CASES (each known class, plus a NULL-class doc and an
    unknown-literal-class doc). ``raw_text`` is populated so the book serve
    path has something to gate."""
    tmpdir = tempfile.mkdtemp(prefix="antiek-polarity-")
    db_path = os.path.join(tmpdir, "test.duckdb")
    con = connect_write(db_path, purpose="servability_polarity_test")
    init_database(con)
    embed = _StubEmbedding()
    for cc in ALL_CASES:
        slug = "null" if cc is None else cc
        doc_id = f"doc-{slug}"
        text = f"quantum entanglement passage for {slug}"
        con.execute(
            """
            INSERT INTO documents (
                document_id, title, source_tier, document_type, content_class, raw_text
            ) VALUES (?, ?, 2, 'book', ?, ?)
            """,
            [doc_id, f"Title {slug}", cc, f"FULL BODY of {slug}: {text}"],
        )
        con.execute(
            """
            INSERT INTO chunks (
                chunk_id, document_id, chunk_index, text, embedding, token_count
            ) VALUES (?, ?, 0, ?, ?, 10)
            """,
            [f"chunk-{doc_id}", doc_id, text, embed.encode(text)],
        )
    yield con
    con.close()


def _chunk_doc_ids_from_search(con) -> set[str]:
    """Document ids the chunk/search path (default attribution-eligible
    policy) actually returns — i.e. the chunk path's servable set."""
    res = search(con, "quantum entanglement", model=_StubEmbedding(), top_k=50)
    return {r["document_id"] for r in res["results"]}


@pytest.mark.parametrize("cc", ALL_CASES)
def test_live_sql_paths_agree_per_class(db_one_doc_per_class, cc):
    """The live chunk path (``search``) and the live book path
    (``serve_full_text``) reach the SAME servable verdict for each class.
    NULL and unknown are denied by both; known-servable classes are
    served by both."""
    slug = "null" if cc is None else cc
    doc_id = f"doc-{slug}"

    chunk_servable_ids = _chunk_doc_ids_from_search(db_one_doc_per_class)
    chunk_servable = doc_id in chunk_servable_ids

    book_servable = serve_full_text(db_one_doc_per_class, doc_id).servable

    assert chunk_servable == book_servable, (
        f"live chunk/book disagree for content_class={cc!r} ({doc_id}): "
        f"chunk_returns={chunk_servable} book_serves={book_servable}"
    )
    # And both equal the owned in-memory predicate.
    assert chunk_servable == is_content_class_servable_full_text(cc)


def test_live_null_and_unknown_denied_on_both_paths(db_one_doc_per_class):
    """Live-SQL dedicated DENY assertions for NULL + unknown on both paths."""
    chunk_ids = _chunk_doc_ids_from_search(db_one_doc_per_class)
    for slug in ("null", UNKNOWN_LITERAL):
        doc_id = f"doc-{slug}"
        assert doc_id not in chunk_ids, f"chunk path served {doc_id}"
        assert serve_full_text(db_one_doc_per_class, doc_id).servable is False


# ---------------------------------------------------------------------------
# G-B — non-vacuity guard: the OLD denylist polarity reds the test
# ---------------------------------------------------------------------------


def _legacy_denylist_chunk_servable(content_class: Optional[str]) -> bool:
    """A faithful re-creation of the pre-SPR-05 fail-open chunk gate:

        WHERE d.content_class IS NULL OR d.content_class NOT IN (RESTRICTED_CONTENT_CLASSES)

    i.e. NULL/unknown PASS (servable), only the explicitly-restricted class
    is withheld. This function exists ONLY to prove non-vacuity — it is the
    thing SPR-05 removed."""
    from substrate.graph.search import RESTRICTED_CONTENT_CLASSES

    if content_class is None:
        return True  # the fail-open: NULL passes
    return content_class not in RESTRICTED_CONTENT_CLASSES


def test_non_vacuity_old_denylist_would_disagree():
    """G-B fail-before, in-test form: if the chunk path used the old
    denylist polarity instead of the owned allowlist, it would DISAGREE
    with the book path on NULL and on the unknown literal — which means the
    agreement assertions above would FAIL. Proving that disagreement here
    guarantees the suite is not vacuously green.

    (The handoff also documents the equivalent source-level fail-before:
    restore the ``IS NULL OR NOT IN`` clause on the SQL gate and re-run.)"""
    # NULL: book denies, old denylist would have served → divergence.
    assert _book_path_servable(None) is False
    assert _legacy_denylist_chunk_servable(None) is True
    assert _legacy_denylist_chunk_servable(None) != _book_path_servable(None)

    # Unknown literal: book denies, old denylist would have served → divergence.
    assert _book_path_servable(UNKNOWN_LITERAL) is False
    assert _legacy_denylist_chunk_servable(UNKNOWN_LITERAL) is True
    assert _legacy_denylist_chunk_servable(UNKNOWN_LITERAL) != _book_path_servable(UNKNOWN_LITERAL)

    # Sanity: the CURRENT chunk path does agree on exactly these cases,
    # which is what the old polarity broke.
    assert chunk_full_text_servable(None) == _book_path_servable(None)
    assert chunk_full_text_servable(UNKNOWN_LITERAL) == _book_path_servable(UNKNOWN_LITERAL)


# ---------------------------------------------------------------------------
# Carve-out (M2): NONE NEEDED — assert the gate matches no NULL/unknown.
# ---------------------------------------------------------------------------


def test_no_legacy_carveout_passes_null_or_unknown():
    """SPR-05 M2 chose (b) 'no carve-out needed'. Assert there is no path —
    named carve-out or otherwise — by which a NULL or unknown class becomes
    servable on the chunk path. A fresh NULL/unknown document is always
    denied (the spec's hard requirement that any carve-out can never match
    arbitrary NULL/unknown)."""
    assert chunk_full_text_servable(None) is False
    assert chunk_full_text_servable(UNKNOWN_LITERAL) is False
    assert chunk_full_text_servable("another_unseen_class") is False
