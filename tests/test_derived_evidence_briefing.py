from __future__ import annotations

import copy
import hashlib
import json

import pytest

from substrate.research_artifact.derived_evidence_briefing import (
    EvidenceBriefingError,
    build_evidence_briefing,
)

QUESTION = "What changed?"


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _pack() -> dict[str, object]:
    citations = []
    for ordinal, (path, text) in enumerate((
        ("Engines", "First <passage> & evidence."),
        ("Airframes", "Second passage."),
        ("Engines", "Third passage."),
    )):
        citations.append({
            "citation_id": "dchunk_" + f"{ordinal + 1:064x}",
            "chunk_ordinal": ordinal,
            "member_index": 0,
            "section_anchor": f"section-{ordinal}",
            "section_path": path,
            "text": text,
            "text_sha256": _sha(text),
        })
    pack: dict[str, object] = {
        "version": "derived_revision_evidence_v1",
        "derived_asset_id": "ast_" + "1" * 32,
        "revision_id": "rev_" + "2" * 32,
        "content_sha256": "3" * 64,
        "generation": 2,
        "is_current": True,
        "index_sha256": "4" * 64,
        "chunker": {"policy": "html", "version": 1},
        "retrieval": {"mode": "deterministic_lexical_v1", "query_sha256": _sha(QUESTION), "top_k": 6},
        "citations": citations,
    }
    pack["pack_sha256"] = _sha(json.dumps(pack, sort_keys=True, separators=(",", ":")))
    return pack


def test_briefing_is_deterministic_grouped_and_escaped() -> None:
    first = build_evidence_briefing(QUESTION, _pack())
    second = build_evidence_briefing(QUESTION, _pack())
    assert first == second
    assert first["section_count"] == 2 and first["passage_count"] == 3
    assert [section["section_path"] for section in first["sections"]] == [
        "Engines", "Airframes"
    ]
    assert [item["chunk_ordinal"] for item in first["sections"][0]["passages"]] == [0, 2]
    assert "First &lt;passage&gt; &amp; evidence." in first["briefing_html"]
    assert "First <passage>" not in first["briefing_html"]
    assert len(first["briefing_json_sha256"]) == 64
    assert len(first["briefing_html_sha256"]) == 64
    assert len(first["artifact_sha256"]) == 64


@pytest.mark.parametrize(
    "mutation", ["question", "pack_digest", "text", "duplicate", "shape", "retrieval"]
)
def test_briefing_refuses_binding_and_integrity_drift(mutation: str) -> None:
    pack = _pack()
    question = QUESTION
    if mutation == "question":
        question = "Different question"
    elif mutation == "pack_digest":
        pack["pack_sha256"] = "f" * 64
    elif mutation == "text":
        pack["citations"][0]["text"] = "changed"  # type: ignore[index]
        body = {key: value for key, value in pack.items() if key != "pack_sha256"}
        pack["pack_sha256"] = _sha(json.dumps(body, sort_keys=True, separators=(",", ":")))
    elif mutation == "duplicate":
        pack["citations"][1]["citation_id"] = pack["citations"][0]["citation_id"]  # type: ignore[index]
        body = {key: value for key, value in pack.items() if key != "pack_sha256"}
        pack["pack_sha256"] = _sha(json.dumps(body, sort_keys=True, separators=(",", ":")))
    elif mutation == "shape":
        pack["extra"] = True
    else:
        pack["retrieval"] = []
        body = {key: value for key, value in pack.items() if key != "pack_sha256"}
        pack["pack_sha256"] = _sha(json.dumps(body, sort_keys=True, separators=(",", ":")))
    with pytest.raises(EvidenceBriefingError):
        build_evidence_briefing(question, copy.deepcopy(pack))


def test_briefing_refuses_html_over_byte_limit() -> None:
    pack = _pack()
    oversized = "x" * (257 * 1024)
    pack["citations"][0]["text"] = oversized  # type: ignore[index]
    pack["citations"][0]["text_sha256"] = _sha(oversized)  # type: ignore[index]
    body = {key: value for key, value in pack.items() if key != "pack_sha256"}
    pack["pack_sha256"] = _sha(json.dumps(body, sort_keys=True, separators=(",", ":")))
    with pytest.raises(EvidenceBriefingError, match="byte limit"):
        build_evidence_briefing(QUESTION, pack)


def test_briefing_refuses_json_escape_expansion_over_byte_limit() -> None:
    pack = _pack()
    oversized_json = "\x01" * 45_000
    pack["citations"][0]["text"] = oversized_json  # type: ignore[index]
    pack["citations"][0]["text_sha256"] = _sha(oversized_json)  # type: ignore[index]
    body = {key: value for key, value in pack.items() if key != "pack_sha256"}
    pack["pack_sha256"] = _sha(json.dumps(body, sort_keys=True, separators=(",", ":")))
    with pytest.raises(EvidenceBriefingError, match="JSON.*byte limit"):
        build_evidence_briefing(QUESTION, pack)


@pytest.mark.parametrize(
    ("field", "value"),
    [("generation", True), ("is_current", 1), ("index_sha256", "bad")],
)
def test_briefing_refuses_malformed_scalar_types(field: str, value: object) -> None:
    pack = _pack()
    pack[field] = value
    body = {key: item for key, item in pack.items() if key != "pack_sha256"}
    pack["pack_sha256"] = _sha(json.dumps(body, sort_keys=True, separators=(",", ":")))
    with pytest.raises(EvidenceBriefingError):
        build_evidence_briefing(QUESTION, pack)


def test_briefing_normalizes_malformed_unicode_to_domain_error() -> None:
    with pytest.raises(EvidenceBriefingError, match="malformed"):
        build_evidence_briefing("bad\ud800question", _pack())
