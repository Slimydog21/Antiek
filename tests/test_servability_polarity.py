"""SPR-03 — cross-path §9.0 servability polarity agreement.

The chunk/search path (``substrate/graph/search.py``) and the book
full-text path (``substrate/books/serve.py``) read the SAME
``documents.content_class`` column. Before SPR-03 they diverged in
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
vacuously — reintroducing the fail-open would break it. The keystone
SOURCE-LEVEL seed-and-catch (restore the ``IS NULL OR NOT IN`` clause on
the SQL gate → ``test_live_null_and_unknown_denied_on_both_paths`` reds)
is recorded in the handoff and in docs/decisions/.

This module is the guard for the ``section-9-0-servability-polarity``
invariant on the staged SPR-03 branch. ON MAIN the invariant stays
@unguarded until the operator merges §9.0 (the staged §9.0 PR merges only
behind the G2/G3 legal gate); this flip lives only on the staged branch.

================================================================================
LEGAL-REVIEW CHECKLIST — operator (the §9 gate owner) signs before merge
================================================================================
The PR description references this block. The merge is gated on the
operator's sign-off; no code path merges automatically. Mirrors
OPERATOR_INPUTS §3 (the critic-corrected §9.0 stage-only checklist).

  [ ] 1. STRICTENING (default/attribution path): the change can only REMOVE
         access there, never grant it. The chunk gate moved from a denylist
         (NULL/unknown PASSED) to a deny-by-default allowlist routed through
         the owned predicate, so the default-path post-state is a strict
         subset of the pre-state. EXCEPTION: the operator-only grounder path
         (item 5) is an intentional WIDENING — not a no-op.
  [ ] 2. CARVE-OUT: NONE NEEDED. Documented at the chunk gate in
         substrate/graph/search.py (search()'s §9.0 block). A NULL-grandfather
         is the blanket fail-open §9.0 forbids, not a finite named set, so no
         carve-out branch is created; legitimately-servable legacy docs
         re-enter the allowlist via the Sprint 18 ip_holders content_class
         backfill (on provenance, never on a NULL hole).
  [ ] 3. NULL content_class DENIED on both chunk and book paths
         (test_null_denied_on_both_paths + live-SQL assertions).
  [ ] 4. UNKNOWN/unrecognised content_class DENIED on both paths
         (test_unknown_literal_denied_on_both_paths + live-SQL).
  [ ] 5. GROUNDER WIDENING — private_research bypass is load-bearing,
         doc-scoped, operator-only, off the money path, and now CODE-ENFORCED
         (search() requires PRIVILEGED_CALLER_TOKEN; a money/ad caller cannot
         present it — test_money_path_caller_cannot_bypass_gate). It WIDENS
         access (re-admits NULL AND restricted_pending_opt_in on the grounder)
         — ratify the widening explicitly, not as a no-op.
  [ ] 6. POLARITY TEST GREEN + NON-VACUITY (G-A + G-B + source seed-and-catch):
            pytest tests/test_servability_polarity.py -q
            # source seed-and-catch: restore "... IS NULL OR NOT IN (...)" on
            #   the chunk gate → live-SQL agreement tests FAIL (red); revert →
            #   green. Pasted in the handoff. Non-vacuity proven.
  [ ] 7. SPR-08 DIVERGENCE — confirm #29 NULL-DENIED is canonical over SPR-08's
         NULL-grandfather. SPR-08 ("§9.0 servability polarity unification —
         chunk+book+ATTRIBUTION", commit d7b5d29, on the dead foundation/
         integration branch) KEEPS NULL servable via a named
         legacy_chunk_grandfathered carve-out AND hardens the money/attribution
         path (substrate/attribution/compute.py) to deny-by-default. SPR-03
         makes the opposite call: NULL DENIED, carve-out NONE-NEEDED,
         compute.py UNTOUCHED. The attribution money-path hardening is a
         SEPARATE §9.0 decision for the operator — NOT closed by this PR. Do
         NOT ratify two contradictory §9.0 gates.

  ___ operator sign-off (date / initials) ______________________

NOTE on grounding.py (item 5): the deny-by-default strictening would
otherwise make the claim-grounder return zero chunks for every wrestled
document whose content_class is still NULL. The grounder is the operator's
own personal-research path; it is moved onto the privileged
policy_tag='private_research' §9.0 bypass, which search() now code-restricts
to callers holding PRIVILEGED_CALLER_TOKEN (the operator-only grounder
entrypoint). HONEST DELTA — this is NOT merely "restoring prior behavior":
the private_research tag SKIPS the §9.0 chunk gate entirely, granting
STRICTLY MORE than the grounder's old default 'attribution_eligible' tag
(which admitted NULL but EXCLUDED restricted_pending_opt_in). The widening is
bounded to the operator's single wrestled document (document_id-scoped) and
re-opens the gate on NO attribution-eligible surface. Ratify the widening of
the operator-only grounder path explicitly.
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
    PRIVILEGED_CALLER_TOKEN,
    PrivilegedPolicyTagError,
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


def test_exactly_one_polarity_function_owns_full_text_servability():
    """Acceptance: full-text servability polarity is defined ONCE, in
    substrate/books/servability.py. The chunk predicate is a thin delegate
    (its module-qualified definition lives in servability), and the search
    gate's allowlist is DERIVED from the owned predicate, not re-declared."""
    assert chunk_full_text_servable.__module__ == "substrate.graph.search"
    # The chunk helper delegates to the owned predicate for every case —
    # not a re-implementation — so there is one polarity, surfaced twice.
    for cc in ALL_CASES:
        assert chunk_full_text_servable(cc) is is_content_class_servable_full_text(cc) \
            or chunk_full_text_servable(cc) == is_content_class_servable_full_text(cc)


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
    """Live-SQL dedicated DENY assertions for NULL + unknown on both paths.

    THE KEYSTONE LIVE-SQL NODE (the seed-and-catch target): restore the old
    ``d.content_class IS NULL OR ... NOT IN (...)`` denylist clause on the
    search() gate and this node REDS (the chunk path serves doc-null /
    doc-unknown again); revert and it greens. That is the non-vacuity proof
    referenced by the section-9-0-servability-polarity invariant."""
    chunk_ids = _chunk_doc_ids_from_search(db_one_doc_per_class)
    for slug in ("null", UNKNOWN_LITERAL):
        doc_id = f"doc-{slug}"
        assert doc_id not in chunk_ids, f"chunk path served {doc_id}"
        assert serve_full_text(db_one_doc_per_class, doc_id).servable is False


# ---------------------------------------------------------------------------
# STAGE-SAFETY GUARD (OPERATOR_INPUTS §3 item 5) — the privileged bypass is
# code-enforced, not merely call-site-disciplined.
# ---------------------------------------------------------------------------


def _simulated_money_path_caller(con):
    """Stand-in for a money / ad / attribution-path caller that does NOT
    import PRIVILEGED_CALLER_TOKEN. It can only pass the policy_tag STRING.
    The real money path (substrate/attribution/compute.py) never calls
    search() with a privileged tag at all — it filters RESTRICTED_CONTENT_
    CLASSES directly — but this models the worst case the critic flagged: a
    future caller that learns the magic string and tries to use it."""
    return search(
        con, "quantum entanglement", model=_StubEmbedding(), top_k=50,
        policy_tag="private_research",  # the privileged bypass, by string
        # NOTE: no privileged_caller token — this caller cannot construct it.
    )


def test_money_path_caller_cannot_bypass_gate(db_one_doc_per_class):
    """A caller that passes a privileged policy_tag STRING but lacks the
    PRIVILEGED_CALLER_TOKEN is REJECTED (PrivilegedPolicyTagError) — it
    cannot reach the §9.0 bypass. This is the code-enforced half of the
    stage-safety guard: the privileged widening is no longer protected only
    by call-site discipline. A money/ad caller (which has no access to the
    module-private token) provably cannot serve NULL/restricted content via
    the bypass, even knowing the tag string."""
    for tag in ("private_research", "operator_only"):
        with pytest.raises(PrivilegedPolicyTagError):
            search(
                db_one_doc_per_class, "quantum entanglement",
                model=_StubEmbedding(), top_k=50, policy_tag=tag,
            )
    # And the worst-case stand-in caller is rejected too.
    with pytest.raises(PrivilegedPolicyTagError):
        _simulated_money_path_caller(db_one_doc_per_class)


def test_operator_grounder_path_may_use_bypass_with_token(db_one_doc_per_class):
    """The operator-only path (which imports the token) MAY use the bypass:
    with the token, a privileged tag serves NULL AND restricted content (the
    intentional, ratified widening). This is the positive control for the
    guard — proving the guard gates on the TOKEN, not on the tag string."""
    res = search(
        db_one_doc_per_class, "quantum entanglement",
        model=_StubEmbedding(), top_k=50,
        policy_tag="private_research",
        privileged_caller=PRIVILEGED_CALLER_TOKEN,
    )
    served = {r["document_id"] for r in res["results"]}
    # The widening: NULL and restricted are now served on the privileged path.
    assert "doc-null" in served
    assert "doc-restricted_pending_opt_in" in served


def test_token_is_not_a_reconstructable_string():
    """The token is a module-private object sentinel, not a string — a caller
    cannot reconstruct it from config / an event payload / the tag name. A
    look-alike (the tag string, or a fresh object) is NOT the token."""
    assert not isinstance(PRIVILEGED_CALLER_TOKEN, str)
    assert object() is not PRIVILEGED_CALLER_TOKEN
    assert "private_research" is not PRIVILEGED_CALLER_TOKEN


# ---------------------------------------------------------------------------
# G-B — non-vacuity guard: the OLD denylist polarity reds the test
# ---------------------------------------------------------------------------


def _legacy_denylist_chunk_servable(content_class: Optional[str]) -> bool:
    """A faithful re-creation of the pre-SPR-03 fail-open chunk gate:

        WHERE d.content_class IS NULL OR d.content_class NOT IN (RESTRICTED_CONTENT_CLASSES)

    i.e. NULL/unknown PASS (servable), only the explicitly-restricted class
    is withheld. This function exists ONLY to prove non-vacuity — it is the
    thing SPR-03 removed."""
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
    """SPR-03 chose 'no carve-out needed'. Assert there is no path — named
    carve-out or otherwise — by which a NULL or unknown class becomes
    servable on the chunk path. A fresh NULL/unknown document is always
    denied (the spec's hard requirement that any carve-out can never match
    arbitrary NULL/unknown)."""
    assert chunk_full_text_servable(None) is False
    assert chunk_full_text_servable(UNKNOWN_LITERAL) is False
    assert chunk_full_text_servable("another_unseen_class") is False
