"""Bite tests for the provenance-edge integrity audit.

These exercise the PURE core (no database), so the gate is falsifiable without a
live DuckDB graph. The load-bearing assertion is non-vacuous: if the audit body
were replaced with ``return []`` (a stub), ``test_manifest_orphan_bites`` and
``test_edge_grounding_bites`` would FAIL — that is what makes this a real gate
rather than a green rubber stamp.
"""

from __future__ import annotations

import json

from tools.lint.provenance_edge_audit import (
    Finding,
    audit_edge_grounding,
    audit_manifest,
    new_findings,
)


def _live() -> dict[str, set[str]]:
    return {
        "document": {"doc-1"},
        "chunk": {"chunk-1"},
        "node": {"node-1", "node-2"},
        "edge": {"edge-1"},
    }


# --------------------------------------------------------------------------- #
# synthesis_substrate_manifest — the polymorphic, non-FK-enforceable surface
# --------------------------------------------------------------------------- #
def test_manifest_clean_passes():
    rows = [
        ("syn-1", "document", "doc-1"),
        ("syn-1", "chunk", "chunk-1"),
        ("syn-1", "node", "node-1"),
    ]
    assert audit_manifest(rows, _live()) == []


def test_manifest_orphan_bites():
    # syn-1 pins a chunk that was later deleted — the DB cannot catch this
    # (entity_id is polymorphic, so no FK spans documents/chunks/nodes/edges).
    rows = [
        ("syn-1", "document", "doc-1"),
        ("syn-1", "chunk", "chunk-DELETED"),
    ]
    findings = audit_manifest(rows, _live())
    assert len(findings) == 1
    assert findings[0].surface == "manifest"
    assert findings[0].ref_id == "chunk-DELETED"
    assert "missing chunk" in findings[0].detail


def test_manifest_unknown_kind_bites():
    # A smuggled entity_kind we cannot resolve must never silently pass.
    rows = [("syn-1", "spork", "whatever")]
    findings = audit_manifest(rows, _live())
    assert len(findings) == 1
    assert "unknown entity_kind" in findings[0].detail


# --------------------------------------------------------------------------- #
# edges.chunk_id / edges.source_document_id — nullable grounding columns
# --------------------------------------------------------------------------- #
def test_edge_null_grounding_is_allowed():
    # NULL grounding is legitimate (structural edge); never a finding.
    edges = [("edge-1", None, None)]
    assert audit_edge_grounding(edges, {"chunk-1"}, {"doc-1"}) == []


def test_edge_grounding_bites():
    edges = [
        ("edge-1", "chunk-1", "doc-1"),          # resolves — clean
        ("edge-2", "chunk-GONE", None),          # dangling chunk grounding
        ("edge-3", None, "doc-GONE"),            # dangling document grounding
    ]
    findings = audit_edge_grounding(edges, {"chunk-1"}, {"doc-1"})
    surfaces = sorted(f.surface for f in findings)
    assert surfaces == ["edge.chunk_id", "edge.source_document_id"]


# --------------------------------------------------------------------------- #
# Shrink-only baseline behaviour
# --------------------------------------------------------------------------- #
def test_baselined_finding_does_not_refail():
    rows = [("syn-1", "chunk", "chunk-DELETED")]
    findings = audit_manifest(rows, _live())
    assert findings, "precondition: there is a finding to baseline"
    baseline = {findings[0].key()}
    assert new_findings(findings, baseline) == []


def test_non_baselined_finding_still_fails_with_baseline_present():
    # A baseline for one orphan must NOT suppress a different, new orphan.
    rows = [
        ("syn-1", "chunk", "chunk-DELETED"),   # baselined
        ("syn-2", "document", "doc-NEW-GONE"), # new — must still bite
    ]
    findings = audit_manifest(rows, _live())
    baseline = {Finding("manifest", "chunk-DELETED",
                        "synthesis syn-1 pins missing chunk chunk-DELETED").key()}
    fresh = new_findings(findings, baseline)
    assert len(fresh) == 1
    assert fresh[0].ref_id == "doc-NEW-GONE"


def test_finding_key_is_stable_and_json_round_trips():
    f = Finding("manifest", "x", "synthesis s pins missing chunk x")
    assert f.key() == Finding("manifest", "x", "synthesis s pins missing chunk x").key()
    # keys are the baseline's on-disk identity — must be plain JSON-serializable strings
    assert json.loads(json.dumps({"baselined_keys": [f.key()]}))["baselined_keys"][0] == f.key()
