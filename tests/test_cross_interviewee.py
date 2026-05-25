"""Speak SPR-05 — cross-interviewee verification / story-hardening tests.

Rigor #3, independence is the case that bites: a shared myth
(multiply-attested but false — labelled honestly, can't be detected),
interviewees who heard it from each other (independence guard), a lone
contradicting source (don't suppress the minority), and embedding
false-clusters.

The cardinal rule, asserted throughout: corroboration ≠ truth. The
label is "multiply_attested", never "true", and confidence never
reaches 1.0.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database
from substrate.speak import corroboration, project, publish_gate
from substrate.speak.corroboration import confidence_for, corroborate_project
from substrate.speak.publish_gate import PublishBlocked
from substrate.speak.schema import ensure_speak_schema
from substrate.speak.third_party import record_claim


@pytest.fixture
def db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="speak-corr-test-")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    db_path = os.path.join(tmpdir, "t.duckdb")
    with connect_write(db_path, purpose="setup") as con:
        init_database(con)
        ensure_speak_schema(con)
    return db_path


def _con(db):
    return connect_write(db, purpose="corr_test")


class ConstantEmbedding:
    """Returns the SAME vector for every text — so cosine = 1 for every
    pair. Used to prove the equivalence check (not the embedding) is what
    actually decides a cluster."""

    dimension = 4

    def encode(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0, 0.0]


def _third_party_claim(con, project_id, text, interview_id):
    return record_claim(con, project_id=project_id, text=text, interview_id=interview_id,
                        about_subject=True, subject_ref="the-dad")


# ── confidence function — never proves truth ────────────────────────────


def test_confidence_monotonic_and_never_one():
    assert confidence_for(1) == 0.5
    assert confidence_for(2) > confidence_for(1)
    assert confidence_for(5) > confidence_for(2)
    assert confidence_for(50) < 1.0  # asymptotic — never "proven"


# ── M1 clustering ───────────────────────────────────────────────────────


def test_same_claim_from_two_interviewees_clusters(db):
    with _con(db) as con:
        p = project.create_project(con, title="Dad's biography")
        _third_party_claim(con, p.project_id, "He emigrated to Canada in 1971.", "iv-a")
        _third_party_claim(con, p.project_id, "He emigrated to Canada in 1971.", "iv-b")
        clusters = corroborate_project(con, p.project_id)
        assert len(clusters) == 1
        assert len(clusters[0].member_claim_ids) == 2


def test_embedding_false_cluster_filtered_by_equivalence(db):
    with _con(db) as con:
        p = project.create_project(con, title="Dad's biography")
        # Two UNRELATED claims; the constant embedder makes them cosine=1
        # candidates, but the equivalence check rejects the pair.
        _third_party_claim(con, p.project_id, "He loved playing the oud.", "iv-a")
        _third_party_claim(con, p.project_id, "He worked as an engineer.", "iv-b")
        clusters = corroborate_project(con, p.project_id, embedder=ConstantEmbedding())
        # Not merged → two single-sourced clusters, not one false cluster.
        assert len(clusters) == 2


# ── M2 multiply-attested (corroborated, not proven) ─────────────────────


def test_two_independent_attesters_marks_multiply_attested(db):
    with _con(db) as con:
        p = project.create_project(con, title="Dad's biography")
        c1 = _third_party_claim(con, p.project_id, "He saved a stranger from drowning.", "iv-a")
        _third_party_claim(con, p.project_id, "He saved a stranger from drowning.", "iv-b")
        clusters = corroborate_project(con, p.project_id)
        assert clusters[0].label == "multiply_attested"
        assert clusters[0].label != "true"  # the cardinal rule
        assert clusters[0].confidence == confidence_for(2)
        # Member claims now carry the verification the publish gate reads.
        from substrate.speak.third_party import get_claim
        assert get_claim(con, c1.claim_id).verification == "multiply_attested"


# ── M3 contradiction (preserve the minority) ────────────────────────────


def test_contradiction_flagged_and_minority_preserved(db):
    with _con(db) as con:
        p = project.create_project(con, title="Dad's biography")
        _third_party_claim(con, p.project_id, "He was born in Cairo in 1940.", "iv-a")
        _third_party_claim(con, p.project_id, "He was born in Cairo in 1942.", "iv-b")

        def contradiction(a: str, b: str) -> bool:
            # Same topic (birth in Cairo) but conflicting years.
            return ("1940" in a and "1942" in b) or ("1942" in a and "1940" in b)

        clusters = corroborate_project(con, p.project_id, contradiction=contradiction)
        assert clusters[0].label == "contradicted"
        # Both sides preserved in the members table (minority not suppressed).
        n_members = con.execute(
            "SELECT count(*) FROM speak_corroboration_members WHERE cluster_id = ?",
            [clusters[0].cluster_id],
        ).fetchone()[0]
        assert n_members == 2


# ── M4 independence guard (shared rumor) ────────────────────────────────


def test_shared_rumor_does_not_inflate_confidence(db):
    with _con(db) as con:
        p = project.create_project(con, title="Dad's biography")
        a = _third_party_claim(con, p.project_id, "He once met the president.", "iv-a")
        b = _third_party_claim(con, p.project_id, "He once met the president.", "iv-b")
        # Both heard it from the same origin → same independence key.
        rumor_key = {a.claim_id: "family-legend-7", b.claim_id: "family-legend-7"}
        clusters = corroborate_project(
            con, p.project_id,
            independence_key_for=lambda c: rumor_key.get(c.claim_id),
        )
        # One shared rumor = one attestation, NOT two → not multiply-attested.
        assert clusters[0].independent_attesters == 1
        assert clusters[0].label == "single_sourced"
        assert clusters[0].confidence == confidence_for(1)


# ── M5 feeds the publish gate ───────────────────────────────────────────


def test_uncorroborated_claim_blocked_then_corroborated_publishable(db):
    with _con(db) as con:
        p = project.create_project(con, title="Dad's biography")
        c1 = _third_party_claim(con, p.project_id, "He founded the village school.", "iv-a")
        # Single-sourced → publish gate blocks.
        with pytest.raises(PublishBlocked):
            publish_gate.assert_claim_publishable(con, c1.claim_id)
        # A second independent attestation corroborates it.
        _third_party_claim(con, p.project_id, "He founded the village school.", "iv-b")
        corroborate_project(con, p.project_id)
        publish_gate.assert_claim_publishable(con, c1.claim_id)  # now publishable


def test_claims_needing_corroboration_lists_single_sourced(db):
    with _con(db) as con:
        p = project.create_project(con, title="Dad's biography")
        _third_party_claim(con, p.project_id, "A lone unverified claim.", "iv-a")
        corroborate_project(con, p.project_id)
        needing = corroboration.claims_needing_corroboration(con, p.project_id)
        assert len(needing) == 1
