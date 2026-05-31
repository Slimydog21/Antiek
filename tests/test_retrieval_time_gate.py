"""Sprint 18 retrieval-time gate tests (master-spec §9.0 + §15.9).

The Sprint 18 legal gate is binding: restricted content
(content_class='restricted_pending_opt_in') is NOT retrievable on
attribution-eligible paths. The substrate enforces this at SQL-WHERE
level so no application-code mistake can route money based on
restricted content.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database
from substrate.graph.search import (
    PRIVILEGED_CALLER_TOKEN,
    PRIVILEGED_POLICY_TAGS,
    PrivilegedPolicyTagError,
    RESTRICTED_CONTENT_CLASSES,
    search,
)


class StubEmbedding:
    dimension = 4

    def encode(self, text: str) -> list[float]:
        # Deterministic hash-based dummy embedding, length=4.
        h = sum(ord(c) * (i + 1) for i, c in enumerate(text)) or 1
        return [
            float(h % 7) / 7.0,
            float((h >> 3) % 11) / 11.0,
            float((h >> 5) % 13) / 13.0,
            float((h >> 7) % 17) / 17.0,
        ]


@pytest.fixture
def db_with_chunks():
    """DuckDB initialized with 4 documents (2 unrestricted, 1
    restricted, 1 NULL content_class) each with one chunk."""
    tmpdir = tempfile.mkdtemp(prefix="antiek-gate-test-")
    db_path = os.path.join(tmpdir, "test.duckdb")
    con = connect_write(db_path, purpose="retrieval_gate_test")
    init_database(con)
    embed = StubEmbedding()

    docs = [
        ("doc-public", "public_domain", "Open access paper on quantum"),
        ("doc-licensed", "opt_in_licensed", "Opt-in licensed publisher paper"),
        ("doc-restricted", "restricted_pending_opt_in", "Restricted Big-Five book chunk"),
        ("doc-legacy", None, "Legacy chunk with no content_class"),
    ]
    for doc_id, content_class, text in docs:
        con.execute(
            """
            INSERT INTO documents (
                document_id, title, source_tier, document_type, content_class
            ) VALUES (?, ?, 2, 'paper', ?)
            """,
            [doc_id, f"Title for {doc_id}", content_class],
        )
        emb = embed.encode(text)
        con.execute(
            """
            INSERT INTO chunks (
                chunk_id, document_id, chunk_index, text, embedding, token_count
            ) VALUES (?, ?, 0, ?, ?, 10)
            """,
            [f"chunk-{doc_id}", doc_id, text, emb],
        )
    yield con
    con.close()


def test_privileged_policy_tags_are_canonical():
    """Master-spec §9.0 names the two privileged tags. The substrate
    must not silently extend this set."""
    assert PRIVILEGED_POLICY_TAGS == frozenset({"private_research", "operator_only"})


def test_restricted_content_classes_canonical():
    """The set of content classes the substrate withholds from
    attribution-eligible retrieval. Drift here = silent gate hole."""
    assert RESTRICTED_CONTENT_CLASSES == frozenset({"restricted_pending_opt_in"})


def test_default_policy_excludes_restricted(db_with_chunks):
    """The default policy_tag='attribution_eligible' MUST exclude
    restricted_pending_opt_in content. Per master-spec §16.2: 'No
    payouts on an ungated graph.'"""
    embed = StubEmbedding()
    res = search(db_with_chunks, "quantum", model=embed, top_k=10)
    doc_ids = {r["chunk_id"].replace("chunk-", "") for r in res["results"]}
    assert "doc-restricted" not in doc_ids, (
        "default policy_tag exposed restricted content; legal gate broken"
    )
    # SPR-03 strictening: legacy NULL content_class is now DENIED on the
    # chunk path (deny-by-default), matching the book full-text path. The
    # old fail-open that grandfathered NULL was the hole SPR-03 closed —
    # see substrate/graph/search.py §9.0 gate and tests/test_servability_polarity.py.
    assert "doc-legacy" not in doc_ids, (
        "NULL content_class must be denied on the chunk path (deny-by-default)"
    )
    # Public + licensed both pass (legitimately-servable classes unaffected).
    assert "doc-public" in doc_ids
    assert "doc-licensed" in doc_ids


def test_explicit_attribution_eligible_excludes_restricted(db_with_chunks):
    """Explicit policy_tag='attribution_eligible' behaves identical
    to the default — the gate is on/off based on PRIVILEGED set
    membership, not on whether the caller passed a tag."""
    embed = StubEmbedding()
    res = search(
        db_with_chunks, "quantum", model=embed, top_k=10,
        policy_tag="attribution_eligible",
    )
    doc_ids = {r["chunk_id"].replace("chunk-", "") for r in res["results"]}
    assert "doc-restricted" not in doc_ids


def test_private_research_policy_includes_restricted(db_with_chunks):
    """Master-spec §9.0 Option C: restricted content IS retrievable
    when policy_tag in {'private_research', 'operator_only'}. This is
    the fair-use-robust path — operator personal research with no
    attribution flowing."""
    embed = StubEmbedding()
    res = search(
        db_with_chunks, "quantum", model=embed, top_k=10,
        policy_tag="private_research",
        privileged_caller=PRIVILEGED_CALLER_TOKEN,
    )
    doc_ids = {r["chunk_id"].replace("chunk-", "") for r in res["results"]}
    assert "doc-restricted" in doc_ids, (
        "private_research policy did not return restricted content; "
        "the operator's personal-research path needs full corpus access"
    )


def test_operator_only_policy_includes_restricted(db_with_chunks):
    """operator_only is the second privileged policy_tag per §9.0."""
    embed = StubEmbedding()
    res = search(
        db_with_chunks, "quantum", model=embed, top_k=10,
        policy_tag="operator_only",
        privileged_caller=PRIVILEGED_CALLER_TOKEN,
    )
    doc_ids = {r["chunk_id"].replace("chunk-", "") for r in res["results"]}
    assert "doc-restricted" in doc_ids


def test_privileged_tag_without_token_raises(db_with_chunks):
    """SPR-03 stage-safety guard: a privileged policy_tag bypasses the §9.0
    gate (it WIDENS access), so it is code-restricted to callers presenting
    PRIVILEGED_CALLER_TOKEN. Requesting a privileged tag without the token
    RAISES rather than silently serving NULL/restricted content. This is the
    code-enforced half of OPERATOR_INPUTS §3 item 5 — call-site discipline is
    no longer the only thing standing between a money/ad caller and the
    bypass."""
    embed = StubEmbedding()
    for tag in ("private_research", "operator_only"):
        with pytest.raises(PrivilegedPolicyTagError):
            search(db_with_chunks, "quantum", model=embed, top_k=10, policy_tag=tag)


def test_unknown_policy_tag_is_treated_as_non_privileged(db_with_chunks):
    """Defensive: a typo'd or unknown policy_tag (e.g. 'PUBLIC',
    'all_access') must default to the safe-exclude behavior, not the
    privileged-include behavior. The gate fails-closed."""
    embed = StubEmbedding()
    res = search(
        db_with_chunks, "quantum", model=embed, top_k=10,
        policy_tag="typo_value_should_not_unlock",
    )
    doc_ids = {r["chunk_id"].replace("chunk-", "") for r in res["results"]}
    assert "doc-restricted" not in doc_ids, (
        "unknown policy_tag silently unlocked restricted content; "
        "the gate must fail closed"
    )
