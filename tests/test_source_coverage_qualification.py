"""SPR-DRL-19 — source-coverage qualification for reused knowledge units.

Tests milestones 1-4:
  M1: SourceCoverageQualification — closed compact value, validation, from_envelope.
  M2: Batch archive resolution — one SQL, dedup, exact account predicates.
  M3: Attach qualifications at retrieval — complete/partial/unknown, Alice/Bob isolation.
  M4: Render qualification markers — deterministic, within token budget.

Also covers:
  - Partial/complete/unknown states
  - Same-named Alice/Bob account isolation
  - Dedup / query count proof
  - Token budget behavior with qualification markers
  - Legacy unauthenticated callers → explicit unknown
  - Malformed archive → fail closed
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from processing.embedding.embed import HashEmbedding
from runtime.db_lock import connect_read, connect_write
from substrate.context_pack.assembler import DefaultTokenCounter
from substrate.context_pack.knowledge_reuse import (
    SourceCoverageQualificationError,
    _qualify_units,
    render_unit,
    select_units_within_budget,
)
from substrate.graph.schema import init_database
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.source_coverage import (
    ArchivedSourceCoverageEnvelope,
    ArtifactLeafCoverage,
    ArtifactLeafSourceStatus,
    ArtifactSourceCoverage,
    ArtifactSourceReceipt,
    SourceCoverageQualification,
    SourceCoverageQualificationValidationError,
    validate_archived_claim_support,
)


def test_terminal_archive_claim_support_rejects_mix_and_match() -> None:
    envelope = ArchivedSourceCoverageEnvelope.model_validate({
        "schema_version": 3,
        "pack_schema_version": 4,
        "pack_content_hash": "a" * 64,
        "inherited_reuse": {"leaves": [{
            "investigation_id": "leaf",
            "state": "legacy_unqualified",
            "injected_unit_count": 1,
            "injected_unit_ids": ["unit-real"],
            "qualifications": [],
        }]},
        "claim_support_by_chunk": {"chunk-real": ["unit-real"]},
        "claim_support_leaf_by_chunk": {"chunk-real": "leaf"},
    })
    thesis = {"thesis_components": [{
        "claim": "claim",
        "supporting_chunk_ids": ["chunk-real"],
        "supporting_inherited_unit_ids": ["unit-real"],
    }]}
    validate_archived_claim_support(
        envelope, thesis, manifest_chunk_ids={"chunk-real"}
    )
    with pytest.raises(ValueError, match="unreachable inherited support"):
        validate_archived_claim_support(
            envelope,
            {"thesis_components": [{
                **thesis["thesis_components"][0],
                "supporting_inherited_unit_ids": ["unit-foreign"],
            }]},
            manifest_chunk_ids={"chunk-real"},
        )
    with pytest.raises(ValueError, match="outside the archive manifest"):
        validate_archived_claim_support(
            envelope, thesis, manifest_chunk_ids={"chunk-other"}
        )
    with pytest.raises(ValueError, match="lacks structural provenance"):
        validate_archived_claim_support(
            envelope,
            {"thesis_components": [{
                "claim": "unsupported",
                "supporting_chunk_ids": [],
                "supporting_path_indices": [],
                "supporting_inherited_unit_ids": [],
            }]},
            manifest_chunk_ids={"chunk-real"},
        )
    validate_archived_claim_support(
        envelope,
        {
            "thesis_components": [{
                "claim": "path supported",
                "supporting_chunk_ids": [],
                "supporting_path_indices": [0],
                "supporting_inherited_unit_ids": [],
            }],
            "reasoning_paths_used": [{"path_node_ids": ["node-1"]}],
        },
        manifest_chunk_ids={"chunk-real"},
    )

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SOURCES = ("exa", "parallel", "arxiv", "substack")


def _make_authority(
    account_id: str = "alice",
    investigation_id: str = "inv-test",
    tmp_path: str | None = None,
) -> InvestigationAuthority:
    from pathlib import Path

    root = (
        Path(tmp_path)
        if tmp_path
        else Path(os.environ.get("ANTIEK_RESEARCH_EVENTS_DIR", "/tmp/spr19-test"))
    )
    return InvestigationAuthority(account_id, investigation_id, root)


def _make_envelope(
    *,
    partial: bool = False,
    partial_leaf_ids: list[str] | None = None,
    succeeded_per_leaf: list[list[str]] | None = None,
    total_per_source: int = 3,
) -> ArchivedSourceCoverageEnvelope:
    """Build a minimal ArchivedSourceCoverageEnvelope for testing."""
    if succeeded_per_leaf is None:
        # All sources succeed for all leaves
        succeeded_per_leaf = [list(_SOURCES) for _ in range(total_per_source)]

    leaves = []
    for i, succeeded in enumerate(succeeded_per_leaf):
        leaves.append(
            ArtifactLeafCoverage(
                investigation_id=f"leaf-{i}",
                sources=[
                    ArtifactLeafSourceStatus(
                        source=src,
                        status="succeeded" if src in succeeded else "failed",
                        document_count=1 if src in succeeded else 0,
                    )
                    for src in _SOURCES
                ],
            )
        )

    partial_leaf_ids = partial_leaf_ids or []
    if partial and not partial_leaf_ids:
        # Auto-detect partial leaves from source statuses
        partial_leaf_ids = [
            leaf.investigation_id
            for leaf in leaves
            if any(s.status != "succeeded" for s in leaf.sources)
        ]

    sources = []
    for src in _SOURCES:
        succeeded_count = sum(
            1
            for leaf in leaves
            if any(s.source == src and s.status == "succeeded" for s in leaf.sources)
        )
        sources.append(
            ArtifactSourceReceipt(
                source=src,
                succeeded_leaves=succeeded_count,
                total_leaves=len(leaves),
            )
        )

    return ArchivedSourceCoverageEnvelope(
        pack_content_hash="a" * 64,
        gather_plan_fingerprint="b" * 64,
        coverage=ArtifactSourceCoverage(
            mode="authorized_multi_source",
            evidence_complete=True,
            partial=partial,
            partial_leaf_investigation_ids=sorted(partial_leaf_ids),
            sources=sources,
            leaves=leaves,
        ),
    )


def _seed_synthesis_with_coverage(
    db_path: str,
    authority: InvestigationAuthority,
    envelope: ArchivedSourceCoverageEnvelope,
    *,
    logical_key: str = "terminal",
) -> str:
    """Seed a synthesis row with source coverage in the substrate column."""
    from middleware.archive import ArchiveInputs, archive_synthesis_via_db, authorized_synthesis_id
    from runtime.db_lock import connect_write
    from substrate.investigation_streams import initialize_composite_stream

    initialize_composite_stream(authority)

    con = connect_write(db_path, purpose="spr19_seed")
    try:
        init_database(con)
        sid = authorized_synthesis_id(authority, logical_key)
        inputs = ArchiveInputs(
            target_question="test question",
            synthesis_timestamp=datetime.now(UTC),
            status="passed",
            implicit_recommendation="proceed",
            substrate=envelope.model_dump(mode="json"),
        )
        archive_synthesis_via_db(
            con,
            inputs,
            investigation_id=authority.investigation_id,
            synthesis_id=sid,
            _authority=authority,
        )
    finally:
        con.close()
    return sid


def _make_fake_unit(
    text: str = "test unit text lorem ipsum",
    inv_id: str = "inv-source",
    sim: float = 0.8,
    unit_id: str | None = None,
):
    """Build a fake RetrievedUnit for testing."""
    from substrate.context_pack.knowledge_reuse import RetrievedUnit
    from substrate.contracts.nodes import (
        KnowledgeUnitContract,
        ProvenanceLink,
        ServabilityTag,
    )

    nid = unit_id or f"node-{inv_id}-{hash(text) % 10000}"
    unit = KnowledgeUnitContract(
        node_id=nid,
        node_type="insight",
        text=text,
        investigation_id=inv_id,
        confidence="high",
        retrieval_key=nid,
        provenance=ProvenanceLink(source_document_id="d1", chunk_id="c1"),
        servability=ServabilityTag(content_class="public_domain", serves_full_text=True),
        groundedness_score=0.9,
    )
    return RetrievedUnit(unit=unit, similarity=sim)


def _qualify_from_db(units, authority, db_path: str):
    con = connect_read(db_path)
    try:
        return _qualify_units(units, authority, con)
    finally:
        con.close()


# ---------------------------------------------------------------------------
# M1 — SourceCoverageQualification validation + from_envelope
# ---------------------------------------------------------------------------


class TestM1Qualification:
    def test_complete_state_valid(self):
        q = SourceCoverageQualification(
            state="complete",
            source_successes=(3, 3, 3, 3),
            total_leaves=3,
            partial_leaf_count=0,
        )
        assert q.state == "complete"
        assert q.source_ratios == ("3/3", "3/3", "3/3", "3/3")

    def test_partial_state_valid(self):
        q = SourceCoverageQualification(
            state="partial",
            source_successes=(3, 2, 3, 1),
            total_leaves=3,
            partial_leaf_count=2,
        )
        assert q.state == "partial"
        assert q.partial_leaf_count == 2

    def test_unknown_state_valid(self):
        q = SourceCoverageQualification.unknown()
        assert q.state == "unknown"
        assert q.source_successes == (0, 0, 0, 0)
        assert q.total_leaves == 0

    def test_reject_complete_with_partial_leaves(self):
        with pytest.raises(
            SourceCoverageQualificationValidationError, match="complete.*partial_leaf"
        ):
            SourceCoverageQualification(
                state="complete",
                source_successes=(3, 3, 3, 3),
                total_leaves=3,
                partial_leaf_count=1,
            )

    def test_reject_partial_without_partial_leaves(self):
        with pytest.raises(
            SourceCoverageQualificationValidationError, match="partial.*partial_leaf_count > 0"
        ):
            SourceCoverageQualification(
                state="partial",
                source_successes=(3, 2, 3, 3),
                total_leaves=3,
                partial_leaf_count=0,
            )

    def test_reject_negative_success_count(self):
        with pytest.raises(SourceCoverageQualificationValidationError, match="negative"):
            SourceCoverageQualification(
                state="complete",
                source_successes=(-1, 3, 3, 3),
                total_leaves=3,
            )

    def test_reject_success_exceeds_total(self):
        with pytest.raises(SourceCoverageQualificationValidationError, match="exceeds total"):
            SourceCoverageQualification(
                state="complete",
                source_successes=(4, 3, 3, 3),
                total_leaves=3,
            )

    def test_reject_partial_count_exceeds_total(self):
        with pytest.raises(
            SourceCoverageQualificationValidationError, match="partial_leaf_count.*exceeds"
        ):
            SourceCoverageQualification(
                state="partial",
                source_successes=(2, 2, 2, 2),
                total_leaves=3,
                partial_leaf_count=5,
            )

    def test_reject_wrong_successes_length(self):
        with pytest.raises(SourceCoverageQualificationValidationError, match="exactly 4"):
            SourceCoverageQualification(
                state="complete",
                source_successes=(3, 3, 3),  # type: ignore[arg-type]
                total_leaves=3,
            )

    def test_reject_unknown_with_partial_leaves(self):
        with pytest.raises(
            SourceCoverageQualificationValidationError, match="unknown.*partial_leaf"
        ):
            SourceCoverageQualification(
                state="unknown",
                source_successes=(0, 0, 0, 0),
                total_leaves=3,
                partial_leaf_count=1,
            )

    def test_reject_unknown_with_claimed_counts(self):
        with pytest.raises(
            SourceCoverageQualificationValidationError,
            match="unknown.*counts",
        ):
            SourceCoverageQualification(
                state="unknown",
                source_successes=(1, 1, 1, 1),
                total_leaves=1,
            )

    def test_reject_complete_with_incomplete_ratio(self):
        with pytest.raises(
            SourceCoverageQualificationValidationError,
            match="complete.*every source",
        ):
            SourceCoverageQualification(
                state="complete",
                source_successes=(2, 2, 1, 2),
                total_leaves=2,
            )

    def test_reject_overflow_leaf_count(self):
        with pytest.raises(
            SourceCoverageQualificationValidationError,
            match="bound of 100",
        ):
            SourceCoverageQualification(
                state="complete",
                source_successes=(101, 101, 101, 101),
                total_leaves=101,
            )

    def test_from_envelope_complete(self):
        env = _make_envelope(partial=False, total_per_source=3)
        q = SourceCoverageQualification.from_envelope(env)
        assert q.state == "complete"
        assert q.source_successes == (3, 3, 3, 3)
        assert q.total_leaves == 3
        assert q.partial_leaf_count == 0

    def test_from_envelope_partial(self):
        # One leaf fails one source → partial
        succeeded = [
            list(_SOURCES),  # leaf-0: all succeed
            list(_SOURCES),  # leaf-1: all succeed
            ["exa", "parallel", "arxiv"],  # leaf-2: substack fails
        ]
        env = _make_envelope(partial=True, succeeded_per_leaf=succeeded)
        q = SourceCoverageQualification.from_envelope(env)
        assert q.state == "partial"
        assert q.partial_leaf_count > 0
        assert q.source_successes[3] < q.total_leaves  # substack has fewer successes

    def test_frozen_immutable(self):
        q = SourceCoverageQualification.unknown()
        with pytest.raises(AttributeError):
            q.state = "complete"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# M2 — batch archive resolution
# ---------------------------------------------------------------------------


class TestM2BatchResolution:
    def test_batch_resolve_single_investigation(self, tmp_path):
        from middleware.archive import resolve_source_coverage_qualifications

        db = str(tmp_path / "test.duckdb")
        env = _make_envelope(total_per_source=3)
        auth = _make_authority("alice", "inv-source-1", str(tmp_path))
        _seed_synthesis_with_coverage(db, auth, env)

        con = connect_read(db)
        try:
            result = resolve_source_coverage_qualifications(con, auth, frozenset({"inv-source-1"}))
        finally:
            con.close()

        assert "inv-source-1" in result
        row = result["inv-source-1"]
        assert row is not None
        assert row == env.model_dump(mode="json")

    def test_batch_resolve_missing_investigation_returns_none(self, tmp_path):
        from middleware.archive import resolve_source_coverage_qualifications

        db = str(tmp_path / "test.duckdb")
        con_write = connect_write(db, purpose="init")
        try:
            init_database(con_write)
        finally:
            con_write.close()

        auth = _make_authority("alice", "inv-nonexistent", str(tmp_path))
        con = connect_read(db)
        try:
            result = resolve_source_coverage_qualifications(
                con, auth, frozenset({"inv-nonexistent"})
            )
        finally:
            con.close()

        assert result["inv-nonexistent"] is None

    def test_batch_resolve_dedup_same_source(self, tmp_path):
        """Two units from the same source investigation → one lookup."""
        from middleware.archive import resolve_source_coverage_qualifications

        db = str(tmp_path / "test.duckdb")
        env = _make_envelope(total_per_source=2)
        auth = _make_authority("alice", "inv-shared", str(tmp_path))
        _seed_synthesis_with_coverage(db, auth, env)

        con = connect_read(db)
        try:
            result = resolve_source_coverage_qualifications(con, auth, frozenset({"inv-shared"}))
        finally:
            con.close()

        # Only one entry despite being requested once (dedup at input level)
        assert len(result) == 1
        assert result["inv-shared"] is not None

    def test_batch_resolve_multiple_investigations(self, tmp_path):
        """Resolve multiple unique source investigations in one batch."""
        from middleware.archive import resolve_source_coverage_qualifications

        db = str(tmp_path / "test.duckdb")
        auth_a = _make_authority("alice", "inv-a", str(tmp_path))
        auth_b = _make_authority("alice", "inv-b", str(tmp_path))
        env_a = _make_envelope(total_per_source=3)
        env_b = _make_envelope(total_per_source=2)
        _seed_synthesis_with_coverage(db, auth_a, env_a)
        _seed_synthesis_with_coverage(db, auth_b, env_b)

        con = connect_read(db)
        try:
            result = resolve_source_coverage_qualifications(
                con, auth_a, frozenset({"inv-a", "inv-b"})
            )
        finally:
            con.close()

        assert len(result) == 2
        assert result["inv-a"] is not None
        assert result["inv-b"] is not None

    def test_batch_resolution_executes_one_statement(self, tmp_path):
        from middleware.archive import resolve_source_coverage_qualifications

        db = str(tmp_path / "test.duckdb")
        auth_a = _make_authority("alice", "inv-a", str(tmp_path))
        auth_b = _make_authority("alice", "inv-b", str(tmp_path))
        _seed_synthesis_with_coverage(db, auth_a, _make_envelope(total_per_source=2))
        _seed_synthesis_with_coverage(db, auth_b, _make_envelope(total_per_source=2))

        inner = connect_read(db)

        class CountingConnection:
            def __init__(self, con):
                self.con = con
                self.execute_count = 0

            def execute(self, query, params=None):
                self.execute_count += 1
                return self.con.execute(query, params)

        counted = CountingConnection(inner)
        try:
            result = resolve_source_coverage_qualifications(
                counted, auth_a, frozenset({"inv-a", "inv-b"})
            )
        finally:
            inner.close()

        assert counted.execute_count == 1
        assert set(result) == {"inv-a", "inv-b"}

    def test_batch_resolve_empty_set_returns_empty(self, tmp_path):
        from middleware.archive import resolve_source_coverage_qualifications

        auth = _make_authority("alice", "inv-x", str(tmp_path))
        db = str(tmp_path / "test.duckdb")
        with connect_write(db, purpose="init") as write_con:
            init_database(write_con)
        con = connect_read(db)
        try:
            result = resolve_source_coverage_qualifications(con, auth, frozenset())
        finally:
            con.close()

        assert result == {}

    def test_batch_resolve_rejects_non_authority(self, tmp_path):
        from middleware.archive import resolve_source_coverage_qualifications

        db = str(tmp_path / "test.duckdb")
        with connect_write(db, purpose="init") as write_con:
            init_database(write_con)
        con = connect_read(db)
        try:
            with pytest.raises(TypeError, match="InvestigationAuthority"):
                resolve_source_coverage_qualifications(con, "not-an-authority", frozenset({"x"}))
        finally:
            con.close()


# ---------------------------------------------------------------------------
# M3 — attach qualifications (complete/partial/unknown, Alice/Bob)
# ---------------------------------------------------------------------------


class TestM3AttachQualifications:
    def test_complete_unit_qualified(self, tmp_path):
        """A unit from a complete investigation gets complete qualification."""
        db = str(tmp_path / "test.duckdb")
        env = _make_envelope(total_per_source=3)
        auth = _make_authority("alice", "inv-complete", str(tmp_path))
        _seed_synthesis_with_coverage(db, auth, env)

        units = [_make_fake_unit(inv_id="inv-complete")]
        result = _qualify_from_db(units, auth, db)

        assert len(result) == 1
        qual = result[0].coverage_qualification
        assert qual is not None
        assert qual.state == "complete"
        assert qual.source_successes == (3, 3, 3, 3)

    def test_partial_unit_qualified(self, tmp_path):
        """A unit from a partial investigation gets partial qualification."""
        db = str(tmp_path / "test.duckdb")
        succeeded = [
            list(_SOURCES),
            list(_SOURCES),
            ["exa", "parallel", "arxiv"],  # substack fails for leaf-2
        ]
        env = _make_envelope(partial=True, succeeded_per_leaf=succeeded)
        auth = _make_authority("alice", "inv-partial", str(tmp_path))
        _seed_synthesis_with_coverage(db, auth, env)

        units = [_make_fake_unit(inv_id="inv-partial")]
        result = _qualify_from_db(units, auth, db)

        qual = result[0].coverage_qualification
        assert qual.state == "partial"
        assert qual.partial_leaf_count > 0

    def test_missing_archive_yields_unknown(self, tmp_path):
        """A unit from an investigation with no archive → unknown."""
        db = str(tmp_path / "test.duckdb")
        con_write = connect_write(db, purpose="init")
        try:
            init_database(con_write)
        finally:
            con_write.close()

        auth = _make_authority("alice", "inv-no-archive", str(tmp_path))
        units = [_make_fake_unit(inv_id="inv-no-archive")]
        result = _qualify_from_db(units, auth, db)

        qual = result[0].coverage_qualification
        assert qual.state == "unknown"

    def test_alice_bob_isolation(self, tmp_path):
        """Same-named inv-X under different accounts → different qualifications."""
        db = str(tmp_path / "test.duckdb")
        env_alice = _make_envelope(total_per_source=3)
        env_bob = _make_envelope(
            partial=True,
            succeeded_per_leaf=[
                list(_SOURCES),
                ["exa", "parallel"],  # arxiv + substack fail
            ],
        )
        auth_alice = _make_authority("alice", "inv-shared-name", str(tmp_path))
        auth_bob = _make_authority("bob", "inv-shared-name", str(tmp_path))
        _seed_synthesis_with_coverage(db, auth_alice, env_alice)
        _seed_synthesis_with_coverage(db, auth_bob, env_bob)

        # Qualify from Alice's perspective
        units_alice = [_make_fake_unit(inv_id="inv-shared-name")]
        result_alice = _qualify_from_db(units_alice, auth_alice, db)

        # Qualify from Bob's perspective
        units_bob = [_make_fake_unit(inv_id="inv-shared-name")]
        result_bob = _qualify_from_db(units_bob, auth_bob, db)

        qual_alice = result_alice[0].coverage_qualification
        qual_bob = result_bob[0].coverage_qualification

        assert qual_alice.state == "complete"
        assert qual_bob.state == "partial"
        assert qual_alice != qual_bob

    def test_duplicated_source_shares_one_lookup(self, tmp_path):
        """Multiple units from the same source investigation share one result."""
        db = str(tmp_path / "test.duckdb")
        env = _make_envelope(total_per_source=2)
        auth = _make_authority("alice", "inv-shared", str(tmp_path))
        _seed_synthesis_with_coverage(db, auth, env)

        units = [
            _make_fake_unit(inv_id="inv-shared", unit_id="node-1", sim=0.9),
            _make_fake_unit(inv_id="inv-shared", unit_id="node-2", sim=0.8),
            _make_fake_unit(inv_id="inv-shared", unit_id="node-3", sim=0.7),
        ]
        result = _qualify_from_db(units, auth, db)

        # All three should have the same qualification
        quals = [r.coverage_qualification for r in result]
        assert all(q == quals[0] for q in quals)

    def test_legacy_unauthenticated_returns_all_unknown(self, tmp_path):
        """Legacy unauthenticated callers (authority=None) → explicit unknown."""
        from substrate.context_pack.knowledge_reuse import retrieve_prior_units

        db = str(tmp_path / "test.duckdb")
        emb = HashEmbedding()
        con = connect_write(db, purpose="init")
        try:
            init_database(con)
        finally:
            con.close()

        # Create a substrate (even though empty)
        from substrate.graph.retrieval_substrate import make_substrate

        sub = make_substrate("brute_force", db, model=emb)
        try:
            # With authority=None → legacy path
            units = retrieve_prior_units(sub, question_text="test", authority=None)
            # Even if units were returned, all should have unknown qualification
            for u in units:
                assert u.coverage_qualification is not None
                assert u.coverage_qualification.state == "unknown"
        finally:
            sub.close()

    def test_qualify_units_preserves_ordering(self, tmp_path):
        """Qualification does not change unit ordering or similarity."""
        db = str(tmp_path / "test.duckdb")
        env = _make_envelope(total_per_source=3)
        auth = _make_authority("alice", "inv-ord", str(tmp_path))
        _seed_synthesis_with_coverage(db, auth, env)

        units = [
            _make_fake_unit(inv_id="inv-ord", unit_id="node-high", sim=0.95),
            _make_fake_unit(inv_id="inv-ord", unit_id="node-mid", sim=0.80),
            _make_fake_unit(inv_id="inv-ord", unit_id="node-low", sim=0.65),
        ]
        result = _qualify_from_db(units, auth, db)

        assert [r.unit_id for r in result] == ["node-high", "node-mid", "node-low"]
        assert [r.similarity for r in result] == [0.95, 0.80, 0.65]

    def test_malformed_envelope_raises(self, tmp_path):
        """Malformed archive coverage → SourceCoverageQualificationError."""
        from middleware.archive import (
            ArchiveInputs,
            archive_synthesis_via_db,
            authorized_synthesis_id,
        )

        db = str(tmp_path / "test.duckdb")
        auth = _make_authority("alice", "inv-bad", str(tmp_path))
        from substrate.investigation_streams import initialize_composite_stream

        initialize_composite_stream(auth)

        con = connect_write(db, purpose="seed_bad")
        try:
            init_database(con)
            sid = authorized_synthesis_id(auth, "terminal")
            inputs = ArchiveInputs(
                target_question="test",
                synthesis_timestamp=datetime.now(UTC),
                status="passed",
                implicit_recommendation="proceed",
                substrate={
                    "schema_version": 1,
                    "pack_schema_version": 2,
                    "coverage": {"garbage": True},
                },
            )
            archive_synthesis_via_db(
                con,
                inputs,
                investigation_id=auth.investigation_id,
                synthesis_id=sid,
                _authority=auth,
            )
        finally:
            con.close()

        units = [_make_fake_unit(inv_id="inv-bad")]
        with pytest.raises(SourceCoverageQualificationError, match="malformed"):
            _qualify_from_db(units, auth, db)

    def test_invalid_archived_json_raises(self, tmp_path):
        db = str(tmp_path / "test.duckdb")
        auth = _make_authority("alice", "inv-invalid-json", str(tmp_path))
        synthesis_id = _seed_synthesis_with_coverage(
            db, auth, _make_envelope(total_per_source=1)
        )
        with connect_write(db, purpose="corrupt-source-coverage-json") as con:
            con.execute(
                "UPDATE syntheses SET substrate = ? WHERE synthesis_id = ?",
                ["{not-json", synthesis_id],
            )

        with pytest.raises(
            SourceCoverageQualificationError,
            match="unavailable",
        ):
            _qualify_from_db(
                [_make_fake_unit(inv_id="inv-invalid-json")], auth, db
            )

    def test_valid_unrelated_legacy_substrate_is_unknown(self, tmp_path):
        db = str(tmp_path / "test.duckdb")
        auth = _make_authority("alice", "inv-legacy-substrate", str(tmp_path))
        synthesis_id = _seed_synthesis_with_coverage(
            db, auth, _make_envelope(total_per_source=1)
        )
        with connect_write(db, purpose="replace-with-legacy-substrate") as con:
            con.execute(
                "UPDATE syntheses SET substrate = ? WHERE synthesis_id = ?",
                ['{"legacy_graph_summary":{"node_count":3}}', synthesis_id],
            )

        result = _qualify_from_db(
            [_make_fake_unit(inv_id="inv-legacy-substrate")], auth, db
        )
        assert result[0].coverage_qualification.state == "unknown"

    def test_database_reopen_reproduces_qualification_and_rendered_bytes(self, tmp_path):
        db = str(tmp_path / "test.duckdb")
        auth = _make_authority("alice", "inv-restart", str(tmp_path))
        _seed_synthesis_with_coverage(db, auth, _make_envelope(total_per_source=2))
        units = [_make_fake_unit(inv_id="inv-restart", unit_id="node-restart")]

        first = _qualify_from_db(units, auth, db)
        second = _qualify_from_db(units, auth, db)

        assert first[0].coverage_qualification == second[0].coverage_qualification
        assert render_unit(first[0]) == render_unit(second[0])

    def test_missing_archive_schema_fails_authenticated_reuse_closed(self, tmp_path):
        auth = _make_authority("alice", "inv-no-schema", str(tmp_path))

        class MissingArchiveConnection:
            def execute(self, _query, _params=None):
                raise RuntimeError("syntheses table absent")

        with pytest.raises(
            SourceCoverageQualificationError,
            match="unavailable",
        ):
            _qualify_units(
                [_make_fake_unit(inv_id="inv-no-schema")],
                auth,
                MissingArchiveConnection(),
            )


# ---------------------------------------------------------------------------
# M4 — render qualification markers + budget behavior
# ---------------------------------------------------------------------------


class TestM4Rendering:
    def test_render_complete_includes_ratios(self):
        qual = SourceCoverageQualification(
            state="complete",
            source_successes=(3, 3, 3, 3),
            total_leaves=3,
        )
        unit = _make_fake_unit()
        unit = type(unit)(
            unit=unit.unit,
            similarity=unit.similarity,
            content_class=unit.content_class,
            taken_down=unit.taken_down,
            coverage_qualification=qual,
        )
        rendered = render_unit(unit)
        assert "[source_coverage=complete" in rendered
        assert "exa:3/3" in rendered
        assert "parallel:3/3" in rendered
        assert "arxiv:3/3" in rendered
        assert "substack:3/3" in rendered

    def test_render_partial_includes_count_and_ratios(self):
        qual = SourceCoverageQualification(
            state="partial",
            source_successes=(3, 2, 3, 1),
            total_leaves=3,
            partial_leaf_count=2,
        )
        unit = _make_fake_unit()
        unit = type(unit)(
            unit=unit.unit,
            similarity=unit.similarity,
            content_class=unit.content_class,
            taken_down=unit.taken_down,
            coverage_qualification=qual,
        )
        rendered = render_unit(unit)
        assert "[source_coverage=partial" in rendered
        assert "leaves=2/3" in rendered
        assert "exa:3/3" in rendered
        assert "substack:1/3" in rendered

    def test_render_unknown_marker(self):
        qual = SourceCoverageQualification.unknown()
        unit = _make_fake_unit()
        unit = type(unit)(
            unit=unit.unit,
            similarity=unit.similarity,
            content_class=unit.content_class,
            taken_down=unit.taken_down,
            coverage_qualification=qual,
        )
        rendered = render_unit(unit)
        assert "[source_coverage=unknown]" in rendered

    def test_render_no_qualification_is_explicitly_unknown(self):
        unit = _make_fake_unit()
        rendered = render_unit(unit)
        assert "source_coverage=unknown" in rendered

    def test_qualification_consumes_budget(self):
        """Qualification markers count toward the token budget."""
        counter = DefaultTokenCounter()
        qual = SourceCoverageQualification(
            state="complete",
            source_successes=(3, 3, 3, 3),
            total_leaves=3,
        )
        unit_with_qual = _make_fake_unit()
        unit_with_qual = type(unit_with_qual)(
            unit=unit_with_qual.unit,
            similarity=unit_with_qual.similarity,
            content_class=unit_with_qual.content_class,
            taken_down=unit_with_qual.taken_down,
            coverage_qualification=qual,
        )
        unit_without_qual = _make_fake_unit(unit_id="node-no-qual")

        rendered_with = render_unit(unit_with_qual)
        rendered_without = render_unit(unit_without_qual)

        tokens_with = counter.count(rendered_with)
        tokens_without = counter.count(rendered_without)

        assert tokens_with > tokens_without, "qualification marker must add token cost"

    def test_budget_overflow_with_qualifications(self):
        """With many qualified units, a tight budget forces overflow."""
        qual = SourceCoverageQualification(
            state="complete",
            source_successes=(3, 3, 3, 3),
            total_leaves=3,
        )
        units = []
        for i in range(30):
            u = _make_fake_unit(
                text=f"unit {i} " + "lorem ipsum " * 8,
                unit_id=f"node-{i:03d}",
                sim=0.95 - i * 0.001,
            )
            u = type(u)(
                unit=u.unit,
                similarity=u.similarity,
                content_class=u.content_class,
                taken_down=u.taken_down,
                coverage_qualification=qual,
            )
            units.append(u)

        counter = DefaultTokenCounter()
        selected, decisions = select_units_within_budget(units, budget=500, counter=counter)
        over = [d for d in decisions if d.decision == "dropped-over-budget"]
        assert over, "qualification markers increase per-unit cost, causing overflow"

    def test_mixed_qualification_states_in_render(self):
        """Mix of complete, partial, unknown units render correctly."""
        qual_complete = SourceCoverageQualification(
            state="complete",
            source_successes=(3, 3, 3, 3),
            total_leaves=3,
        )
        qual_partial = SourceCoverageQualification(
            state="partial",
            source_successes=(2, 2, 2, 1),
            total_leaves=3,
            partial_leaf_count=1,
        )
        qual_unknown = SourceCoverageQualification.unknown()

        for qual, expected_fragment in [
            (qual_complete, "[source_coverage=complete"),
            (qual_partial, "[source_coverage=partial"),
            (qual_unknown, "[source_coverage=unknown]"),
        ]:
            unit = _make_fake_unit(unit_id=f"node-{qual.state}")
            unit = type(unit)(
                unit=unit.unit,
                similarity=unit.similarity,
                content_class=unit.content_class,
                taken_down=unit.taken_down,
                coverage_qualification=qual,
            )
            rendered = render_unit(unit)
            assert expected_fragment in rendered

    def test_emitted_receipt_matches_injected_complete_unit(self, tmp_path):
        from substrate.context_pack.knowledge_reuse import (
            DECISION_INJECTED,
            UnitDecision,
            _emit_knowledge_reused,
        )
        from substrate.event_log import trajectory

        qualification = SourceCoverageQualification(
            state="complete",
            source_successes=(2, 2, 2, 2),
            total_leaves=2,
        )
        base = _make_fake_unit(inv_id="inv-source", unit_id="node-qualified")
        unit = type(base)(
            unit=base.unit,
            similarity=base.similarity,
            content_class=base.content_class,
            taken_down=base.taken_down,
            coverage_qualification=qualification,
        )
        decision = UnitDecision(
            unit_id=unit.unit_id,
            source_investigation_id=unit.source_investigation_id,
            similarity=unit.similarity,
            decision=DECISION_INJECTED,
        )

        _emit_knowledge_reused(
            investigation_id="inv-event",
            injected=[unit],
            decisions=[decision],
            context_pack_event_id="pack-event",
            role="user_agent",
            events_dir=str(tmp_path),
            policy_id=None,
        )

        payload = trajectory("inv-event", events_dir=str(tmp_path))[0]["payload"]
        assert payload["reused_unit_ids"] == ["node-qualified"]
        assert payload["source_qualifications"] == [
            {
                "unit_id": "node-qualified",
                "source_investigation_id": "inv-source",
                "state": "complete",
                "source_successes": [2, 2, 2, 2],
                "total_leaves": 2,
                "partial_leaf_count": 0,
            }
        ]


# ---------------------------------------------------------------------------
# Integration — end-to-end qualification through retrieve_prior_units
# ---------------------------------------------------------------------------


class TestEndToEnd:
    def test_retrieve_qualifies_authenticated_units(self, tmp_path):
        """Full round-trip: seed graph + archive → retrieve → qualified units."""
        from substrate.context_pack.knowledge_reuse import retrieve_prior_units
        from substrate.graph.insight_question import promote_insight
        from substrate.graph.ops import insert_node
        from substrate.graph.retrieval_substrate import make_substrate

        db = str(tmp_path / "e2e.duckdb")
        emb = HashEmbedding()
        auth = _make_authority("alice", "inv-source-e2e", str(tmp_path))

        # Seed graph with insight units
        con = connect_write(db, purpose="e2e_seed")
        try:
            init_database(con)
            con.execute("BEGIN")
            doc_id = "doc-e2e"
            chunk_id = "chunk-e2e"
            con.execute(
                "INSERT INTO documents (document_id, title, source_tier, "
                "document_type, content_class) VALUES (?, ?, 1, 'paper', ?)",
                [doc_id, "Title", "public_domain"],
            )
            con.execute(
                "INSERT INTO chunks (chunk_id, document_id, chunk_index, text, "
                "embedding, token_count) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    chunk_id,
                    doc_id,
                    0,
                    "neutral atom qubit suppression",
                    emb.encode("neutral atom qubit suppression"),
                    4,
                ],
            )
            claim_id = insert_node(
                con,
                canonical_label="claim: neutral atom qubit",
                node_type="claim",
                graph_scope="depth",
                investigation_id="inv-source-e2e",
                embedding=emb.encode("neutral atom qubit suppression"),
                on_conflict="ignore",
            )
            promote_insight(
                text="neutral atom qubit error rate suppression milestone",
                investigation_id="inv-source-e2e",
                confidence="high",
                supported_by=[claim_id],
                source_document_id=doc_id,
                chunk_id=chunk_id,
                embedding_provider=emb,
                con=con,
            )
            con.execute("COMMIT")
        finally:
            con.close()

        # Seed archive with complete coverage
        env = _make_envelope(total_per_source=3)
        _seed_synthesis_with_coverage(db, auth, env)

        # Retrieve and qualify
        sub = make_substrate("brute_force", db, model=emb)
        try:
            units = retrieve_prior_units(
                sub,
                question_text="neutral atom qubit error rate suppression",
                authority=auth,
            )
        finally:
            sub.close()

        assert units, "must retrieve the seeded unit"
        for u in units:
            assert u.coverage_qualification is not None
            assert u.coverage_qualification.state == "complete"

    def test_retrieve_unknown_for_legacy_caller(self, tmp_path):
        """Legacy unauthenticated caller → all units qualified as unknown."""
        from substrate.context_pack.knowledge_reuse import retrieve_prior_units
        from substrate.graph.insight_question import promote_insight
        from substrate.graph.ops import insert_node
        from substrate.graph.retrieval_substrate import make_substrate

        db = str(tmp_path / "legacy.duckdb")
        emb = HashEmbedding()

        con = connect_write(db, purpose="legacy_seed")
        try:
            init_database(con)
            con.execute("BEGIN")
            doc_id = "doc-legacy"
            chunk_id = "chunk-legacy"
            con.execute(
                "INSERT INTO documents (document_id, title, source_tier, "
                "document_type, content_class) VALUES (?, ?, 1, 'paper', ?)",
                [doc_id, "Title", "public_domain"],
            )
            con.execute(
                "INSERT INTO chunks (chunk_id, document_id, chunk_index, text, "
                "embedding, token_count) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    chunk_id,
                    doc_id,
                    0,
                    "quantum error correction threshold",
                    emb.encode("quantum error correction threshold"),
                    4,
                ],
            )
            claim_id = insert_node(
                con,
                canonical_label="claim: quantum error",
                node_type="claim",
                graph_scope="depth",
                investigation_id="inv-legacy",
                embedding=emb.encode("quantum error correction threshold"),
                on_conflict="ignore",
            )
            promote_insight(
                text="quantum error correction threshold breakthrough",
                investigation_id="inv-legacy",
                confidence="high",
                supported_by=[claim_id],
                source_document_id=doc_id,
                chunk_id=chunk_id,
                embedding_provider=emb,
                con=con,
            )
            con.execute("COMMIT")
        finally:
            con.close()

        sub = make_substrate("brute_force", db, model=emb)
        try:
            # authority=None → legacy unauthenticated path
            units = retrieve_prior_units(
                sub,
                question_text="quantum error correction threshold",
                authority=None,
            )
        finally:
            sub.close()

        for u in units:
            assert u.coverage_qualification is not None
            assert u.coverage_qualification.state == "unknown"
