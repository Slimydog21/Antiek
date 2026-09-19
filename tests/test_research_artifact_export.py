"""SPR-AHT-02 — exporter + artifact path."""

from __future__ import annotations

import copy
import hashlib
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from substrate.event_log import trajectory
from substrate.graph import ensure_initialized
from substrate.graph.insight_question import promote_insight
from substrate.research_artifact import export_research_artifact, operator_authority
from substrate.research_artifact.authority import ArtifactAuthority
from substrate.schemas.events import ActionType


class _StubEmbedding:
    dimension = 8

    def encode(self, text: str) -> list[float]:
        d = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in d[: self.dimension]]


def test_artifact_reader_revalidates_archived_claim_reachability(
    art_env, monkeypatch
):
    from substrate.investigation_tenancy import InvestigationAuthority
    from substrate.research_artifact.build_body import _archived_terminal_provenance

    envelope = {
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
    }
    thesis = {"thesis_components": [{
        "claim": "Bound claim",
        "supporting_chunk_ids": ["chunk-real"],
        "supporting_inherited_unit_ids": ["unit-real"],
    }]}
    archived = SimpleNamespace(
        substrate=envelope,
        thesis=thesis,
        substrate_manifest={"chunk": ["chunk-real"]},
    )
    monkeypatch.setattr(
        "middleware.archive.load_synthesis_authorized", lambda *_args, **_kwargs: archived
    )
    monkeypatch.setattr(
        "substrate.legal_gate.read.archive_chunk_ids_compatibility",
        lambda _con, ids, **_kwargs: set(ids),
    )
    authority = InvestigationAuthority("alice", "inv", Path(art_env["events"]))
    _coverage, _reuse, claims = _archived_terminal_provenance(
        authority, db_path=art_env["db"]
    )
    assert claims[0].inherited_support[0].qualification_state == "legacy_unqualified"
    assert claims[0].inherited_support[0].supporting_leaf_investigation_id == "leaf"

    archived.substrate_manifest = {"chunk": ["chunk-other"]}
    with pytest.raises(ValueError, match="outside the archive manifest"):
        _archived_terminal_provenance(authority, db_path=art_env["db"])


@pytest.fixture
def art_env(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="ra-export-")
    db = os.path.join(tmpdir, "t.duckdb")
    events = os.path.join(tmpdir, "events")
    arts = os.path.join(tmpdir, "artifacts")
    os.makedirs(events, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events)
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", arts)
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    ensure_initialized(db)
    return {"db": db, "events": events, "arts": arts}


def test_export_writes_html_and_insight(art_env):
    promote_insight(
        text="Finding one.",
        investigation_id="inv-ra",
        confidence="moderate",
        source_document_id="doc-1",
    )
    authority = operator_authority("inv-ra")
    res = export_research_artifact(
        "inv-ra",
        authority=authority,
        db_path=art_env["db"],
        events_dir=art_env["events"],
    )
    assert res.path.is_file()
    text = res.path.read_text(encoding="utf-8")
    assert "Finding one." in text
    assert res.size_bytes > 0
    rows = trajectory(authority.event_stream_id, events_dir=art_env["events"])
    kinds = [r.get("action_type") for r in rows]
    assert ActionType.ARTIFACT_GENERATED.value in kinds


def test_exact_export_replay_has_one_deterministic_event(art_env):
    authority = operator_authority("inv-replay")
    first = export_research_artifact(
        authority.investigation_id,
        authority=authority,
        db_path=art_env["db"],
        events_dir=art_env["events"],
    )
    second = export_research_artifact(
        authority.investigation_id,
        authority=authority,
        db_path=art_env["db"],
        events_dir=art_env["events"],
    )
    assert second.content_hash == first.content_hash
    assert second.event_id == first.event_id
    rows = trajectory(authority.event_stream_id, events_dir=art_env["events"])
    generated = [
        row for row in rows if row["action_type"] == ActionType.ARTIFACT_GENERATED.value
    ]
    assert len(generated) == 1


def test_export_persists_source_coverage_in_html_and_content_hash(art_env):
    from substrate.research_artifact.import_notes import parse_body_from_path

    authority = operator_authority("inv-source-coverage")
    coverage = {
        "mode": "authorized_multi_source",
        "evidence_complete": True,
        "partial": True,
        "partial_leaf_investigation_ids": ["leaf-1"],
        "sources": [
            {"source": source, "succeeded_leaves": succeeded, "total_leaves": 2}
            for source, succeeded in zip(
                ("exa", "parallel", "arxiv", "substack"),
                (2, 1, 2, 2),
                strict=True,
            )
        ],
        "leaves": [
            {
                "investigation_id": leaf,
                "sources": [
                    {
                        "source": source,
                        "status": (
                            "skipped" if leaf == "leaf-1" and source == "parallel"
                            else "succeeded"
                        ),
                        "document_count": 1,
                    }
                    for source in ("exa", "parallel", "arxiv", "substack")
                ],
            }
            for leaf in ("leaf-0", "leaf-1")
        ],
    }
    result = export_research_artifact(
        authority.investigation_id,
        authority=authority,
        db_path=art_env["db"],
        events_dir=art_env["events"],
        source_coverage=coverage,
    )
    parsed = parse_body_from_path(result.path)

    assert parsed.source_coverage is not None
    assert parsed.source_coverage.partial_leaf_investigation_ids == ["leaf-1"]
    assert parsed.content_hash() == result.content_hash
    assert "Do not interpret this artifact as comprehensive" in result.path.read_text()


def test_export_persists_inherited_reuse_separately(art_env):
    from substrate.research_artifact.import_notes import parse_body_from_path

    authority = operator_authority("inv-inherited-reuse")
    inherited = {
        "leaves": [{
            "investigation_id": "leaf-0",
            "state": "legacy_unqualified",
            "injected_unit_count": 2,
            "qualifications": [],
        }]
    }
    result = export_research_artifact(
        authority.investigation_id,
        authority=authority,
        db_path=art_env["db"],
        events_dir=art_env["events"],
        inherited_reuse=inherited,
        terminal_provenance={
            "schema_version": 2,
            "pack_schema_version": 3,
            "pack_content_hash": "a" * 64,
            "inherited_reuse": inherited,
        },
    )
    parsed = parse_body_from_path(result.path)

    assert parsed.source_coverage is None
    assert parsed.inherited_reuse is not None
    assert parsed.inherited_reuse.leaves[0].state == "legacy_unqualified"
    assert parsed.content_hash() == result.content_hash
    assert "Inherited knowledge is not direct evidence" in result.path.read_text()

    with pytest.raises(ValueError, match="requires terminal provenance"):
        export_research_artifact(
            "inv-unbound-inherited",
            authority=operator_authority("inv-unbound-inherited"),
            db_path=art_env["db"],
            events_dir=art_env["events"],
            inherited_reuse=inherited,
        )


def test_authorized_rebuild_recovers_archive_coverage_and_rejects_conflict(art_env):
    from datetime import UTC, datetime

    from middleware.archive import ArchiveInputs, archive_synthesis_authorized
    from runtime.db_lock import connect_write
    from substrate.graph.tenancy import GraphTenancyState, transition_graph_tenancy_state
    from substrate.investigation_streams import initialize_composite_stream
    from substrate.investigation_tenancy import InvestigationAuthority
    from substrate.research_artifact.import_notes import parse_body_from_path

    investigation = InvestigationAuthority(
        "alice", "inv-archive-coverage", Path(art_env["events"])
    )
    initialize_composite_stream(investigation)
    bob_investigation = InvestigationAuthority(
        "bob", investigation.investigation_id, Path(art_env["events"])
    )
    initialize_composite_stream(bob_investigation)
    coverage = {
        "schema_version": 1,
        "pack_schema_version": 2,
        "pack_content_hash": "a" * 64,
        "gather_plan_fingerprint": "b" * 64,
        "coverage": {
            "mode": "authorized_multi_source",
            "evidence_complete": True,
            "partial": True,
            "partial_leaf_investigation_ids": ["leaf"],
            "sources": [
                {
                    "source": source,
                    "succeeded_leaves": 0 if source == "arxiv" else 1,
                    "total_leaves": 1,
                }
                for source in ("exa", "parallel", "arxiv", "substack")
            ],
            "leaves": [{
                "investigation_id": "leaf",
                "sources": [
                    {
                        "source": source,
                        "status": "failed" if source == "arxiv" else "succeeded",
                        "document_count": 0 if source == "arxiv" else 1,
                    }
                    for source in ("exa", "parallel", "arxiv", "substack")
                ],
            }],
        },
    }
    with connect_write(art_env["db"], purpose="archive-artifact-coverage") as con:
        archive_synthesis_authorized(
            con,
            investigation,
            ArchiveInputs(
                target_question="Q",
                synthesis_timestamp=datetime(2026, 7, 16, tzinfo=UTC),
                status="passed",
                implicit_recommendation="conditional",
                substrate=coverage,
            ),
            logical_key="terminal",
        )
        bob_coverage = copy.deepcopy(coverage)
        bob_coverage["pack_content_hash"] = "c" * 64
        bob_coverage["coverage"]["partial"] = False
        bob_coverage["coverage"]["partial_leaf_investigation_ids"] = []
        bob_coverage["coverage"]["sources"][2]["succeeded_leaves"] = 1
        bob_coverage["coverage"]["leaves"][0]["sources"][2] = {
            "source": "arxiv",
            "status": "succeeded",
            "document_count": 1,
        }
        archive_synthesis_authorized(
            con,
            bob_investigation,
            ArchiveInputs(
                target_question="Bob's Q",
                synthesis_timestamp=datetime(2026, 7, 16, tzinfo=UTC),
                status="passed",
                implicit_recommendation="conditional",
                substrate=bob_coverage,
            ),
            logical_key="terminal",
        )
        transition_graph_tenancy_state(
            con,
            expected=GraphTenancyState.UNSCOPED,
            desired=GraphTenancyState.COPYING,
        )
        transition_graph_tenancy_state(
            con,
            expected=GraphTenancyState.COPYING,
            desired=GraphTenancyState.SHADOW,
        )

    authority = ArtifactAuthority("alice", investigation.investigation_id)
    rebuilt = export_research_artifact(
        investigation.investigation_id,
        authority=authority,
        db_path=art_env["db"],
        events_dir=art_env["events"],
        emit_event=False,
    )
    parsed = parse_body_from_path(rebuilt.path)
    assert parsed.source_coverage is not None
    assert parsed.source_coverage.partial is True
    assert parsed.source_coverage.leaves[0].sources[2].status == "failed"

    bob_rebuilt = export_research_artifact(
        bob_investigation.investigation_id,
        authority=ArtifactAuthority("bob", bob_investigation.investigation_id),
        db_path=art_env["db"],
        events_dir=art_env["events"],
        emit_event=False,
    )
    bob_parsed = parse_body_from_path(bob_rebuilt.path)
    assert bob_parsed.source_coverage is not None
    assert bob_parsed.source_coverage.partial is False
    assert bob_parsed.source_coverage.leaves[0].sources[2].status == "succeeded"
    assert parsed.source_coverage.leaves[0].sources[2].status == "failed"

    conflicting = copy.deepcopy(coverage["coverage"])
    conflicting["partial"] = False
    conflicting["partial_leaf_investigation_ids"] = []
    conflicting["sources"][2]["succeeded_leaves"] = 1
    conflicting["leaves"][0]["sources"][2] = {
        "source": "arxiv",
        "status": "succeeded",
        "document_count": 1,
    }
    with pytest.raises(ValueError, match="source coverage conflicts"):
        export_research_artifact(
            investigation.investigation_id,
            authority=authority,
            db_path=art_env["db"],
            events_dir=art_env["events"],
            emit_event=False,
            source_coverage=conflicting,
        )


def test_export_event_failure_leaves_durable_owner_scoped_outbox(art_env, monkeypatch):
    from substrate.research_artifact import export as export_module
    from substrate.research_artifact.outbox import reconcile_pending_events

    authority = operator_authority("inv-pending")
    original_append = export_module.append_event_once
    monkeypatch.setattr(export_module, "append_event_once", lambda *args, **kwargs: None)
    result = export_research_artifact(
        "inv-pending",
        authority=authority,
        db_path=art_env["db"],
        events_dir=art_env["events"],
    )
    assert result.path.exists()
    pending = list((authority.account_dir() / "pending-events").glob("*.json"))
    assert len(pending) == 1
    assert authority.account_id not in pending[0].read_text(encoding="utf-8")

    monkeypatch.setattr(export_module, "append_event_once", original_append)
    first = reconcile_pending_events(authority, events_dir=art_env["events"])
    second = reconcile_pending_events(authority, events_dir=art_env["events"])
    assert (first.attempted, first.delivered, first.pending, first.quarantined) == (
        1,
        1,
        0,
        0,
    )
    assert (second.attempted, second.delivered, second.pending, second.quarantined) == (
        0,
        0,
        0,
        0,
    )
    rows = trajectory(authority.event_stream_id, events_dir=art_env["events"])
    assert [row["action_type"] for row in rows].count(ActionType.ARTIFACT_GENERATED.value) == 1


def test_reconcile_quarantines_poison_without_crossing_owner(art_env):
    from substrate.research_artifact.outbox import reconcile_pending_events

    alice = ArtifactAuthority("alice", "shared-poison")
    bob = ArtifactAuthority("bob", "shared-poison")
    alice_pending = alice.account_dir() / "pending-events"
    alice_pending.mkdir(parents=True)
    (alice_pending / "poison.json").write_text('{"version":2}', encoding="utf-8")

    result = reconcile_pending_events(alice, events_dir=art_env["events"])
    assert (result.attempted, result.delivered, result.pending, result.quarantined) == (
        1,
        0,
        0,
        1,
    )
    assert not list(alice_pending.glob("*.json"))
    assert len(list((alice.account_dir() / "quarantined-events").glob("*.json"))) == 1
    assert not bob.account_dir().exists()


def test_reconcile_refuses_export_event_after_canonical_bytes_are_superseded(
    art_env, monkeypatch
):
    from substrate.research_artifact import export as export_module
    from substrate.research_artifact.outbox import reconcile_pending_events
    from substrate.research_artifact.storage import FilesystemArtifactStore

    authority = operator_authority("inv-superseded")
    monkeypatch.setattr(export_module, "append_event_once", lambda *args, **kwargs: None)
    export_research_artifact(
        "inv-superseded",
        authority=authority,
        db_path=art_env["db"],
        events_dir=art_env["events"],
    )
    FilesystemArtifactStore().write(authority, "newer canonical bytes")

    result = reconcile_pending_events(authority, events_dir=art_env["events"])
    assert (result.delivered, result.pending, result.quarantined) == (0, 0, 1)
    assert trajectory(authority.event_stream_id, events_dir=art_env["events"]) == []
