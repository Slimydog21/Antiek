from __future__ import annotations

import hashlib

import pytest

from services.html_projection.gate import assert_script_free
from substrate.multimedia.information_asset import (
    MultimediaInformationAsset,
    MultimediaInformationAssetError,
    MultimediaKnowledgeRegistrationReceipt,
    project_multimedia_information_asset,
    register_multimedia_information_asset,
)
from substrate.multimedia.read_model import CreateMultimediaDraftRequest, MultimediaAssetStore


class _Registrar:
    def __init__(self) -> None:
        self.seen: MultimediaInformationAsset | None = None

    def register(
        self, asset: MultimediaInformationAsset
    ) -> MultimediaKnowledgeRegistrationReceipt:
        self.seen = asset
        return MultimediaKnowledgeRegistrationReceipt(
            owner_identity_digest=asset.owner_identity_digest,
            asset_id=asset.asset_id,
            revision_id=asset.revision_id,
            html_sha256=asset.html_sha256,
            graph_node_id=f"graph-{asset.asset_id}",
            twin_document_id=f"twin-{asset.asset_id}",
        )


def _records(tmp_path):
    store = MultimediaAssetStore(tmp_path)
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic='<Aircraft & engines "through history">',
            target_minutes=15,
            mode="audio",
            route_policy="balanced",
            sources=("High-bypass engines changed long-haul economics.",),
        ),
        owner_id=" owner-a@example.test ",
    )
    ready = store.approve_dry_run(draft.asset.asset_id, owner_id="owner-a@example.test")
    return draft, ready


def test_ready_multimedia_projects_deterministic_inert_provenance_html(tmp_path) -> None:
    _, ready = _records(tmp_path)
    first = project_multimedia_information_asset(ready, owner_id="owner-a@example.test")
    second = project_multimedia_information_asset(ready, owner_id=" owner-a@example.test ")

    assert first == second
    assert first.owner_identity_digest == hashlib.sha256(b"owner-a@example.test").hexdigest()
    assert first.html_sha256 == hashlib.sha256(first.html.encode()).hexdigest()
    assert first.asset_id == ready.asset.asset_id
    assert first.revision_id == ready.asset.revision_id
    assert "<script" not in first.html.lower()
    assert '&lt;Aircraft &amp; engines &quot;' in first.html
    assert "data-line-id=" in first.html
    assert "data-cited-chunk-ids=\"mm-src-0\"" in first.html
    assert "data-citation-ids=" in first.html
    assert "data-citation-id=" in first.html
    assert "data-document-id=\"operator-source-excerpt-0\"" in first.html
    assert "data-quote-sha256=" in first.html
    assert "synthetic narration or visuals" in first.html
    assert first.source_references[0].chunk_id == "mm-src-0"
    assert first.source_references[0].document_id == "operator-source-excerpt-0"
    assert all(reference.line_id for reference in first.source_references)
    assert len({reference.citation_id for reference in first.source_references}) == len(
        first.source_references
    )
    assert_script_free(first.html)


def test_projection_requires_ready_owner_consistent_record(tmp_path) -> None:
    draft, ready = _records(tmp_path)
    with pytest.raises(MultimediaInformationAssetError, match="not ready"):
        project_multimedia_information_asset(draft, owner_id="owner-a@example.test")
    with pytest.raises(MultimediaInformationAssetError, match="owner identity conflicts"):
        project_multimedia_information_asset(ready, owner_id="owner-b@example.test")
    forged = ready.model_copy(
        update={"asset": ready.asset.model_copy(update={"owner_user_id": hashlib.sha256(b"owner-b@example.test").hexdigest()})}
    )
    with pytest.raises(MultimediaInformationAssetError, match="owner identity conflicts"):
        project_multimedia_information_asset(forged, owner_id="owner-a@example.test")


def test_projection_refuses_grounding_or_transcript_drift(tmp_path) -> None:
    _, ready = _records(tmp_path)
    manifest = ready.asset.manifest
    conflicting_claim = manifest.claim_to_chunk[0].model_copy(update={"chunk_ids": ("other",)})
    bad_grounding = ready.model_copy(
        update={
            "asset": ready.asset.model_copy(
                update={
                    "manifest": manifest.model_copy(
                        update={"claim_to_chunk": (conflicting_claim,) + manifest.claim_to_chunk[1:]}
                    )
                }
            )
        }
    )
    with pytest.raises(MultimediaInformationAssetError, match="grounding map"):
        project_multimedia_information_asset(bad_grounding, owner_id="owner-a@example.test")

    first_segment = manifest.segments[0].model_copy(update={"script_line_ids": ()})
    bad_coverage = ready.model_copy(
        update={
            "asset": ready.asset.model_copy(
                update={
                    "manifest": manifest.model_copy(
                        update={"segments": (first_segment,) + manifest.segments[1:]}
                    )
                }
            )
        }
    )
    with pytest.raises(MultimediaInformationAssetError, match="transcript coverage"):
        project_multimedia_information_asset(bad_coverage, owner_id="owner-a@example.test")

    lines = list(manifest.script_lines)
    cited_index = next(index for index, line in enumerate(lines) if line.citations)
    cited_line = lines[cited_index]
    conflicting_citation = cited_line.citations[0].model_copy(update={"document_id": "other-doc"})
    lines.append(
        cited_line.model_copy(
            update={
                "line_id": "conflicting-citation-line",
                "sequence": len(lines),
                "citations": (conflicting_citation,),
            }
        )
    )
    segment = manifest.segments[-1].model_copy(
        update={
            "script_line_ids": manifest.segments[-1].script_line_ids
            + ("conflicting-citation-line",)
        }
    )
    claims = manifest.claim_to_chunk + (
        manifest.claim_to_chunk[0].model_copy(
            update={"claim_id": "claim-conflict", "script_line_id": "conflicting-citation-line"}
        ),
    )
    conflicting_identity = ready.model_copy(
        update={
            "asset": ready.asset.model_copy(
                update={
                    "manifest": manifest.model_copy(
                        update={
                            "script_lines": tuple(lines),
                            "segments": manifest.segments[:-1] + (segment,),
                            "claim_to_chunk": claims,
                        }
                    )
                }
            )
        }
    )
    with pytest.raises(MultimediaInformationAssetError, match="citation identity"):
        project_multimedia_information_asset(
            conflicting_identity, owner_id="owner-a@example.test"
        )


def test_registration_receipt_is_exactly_bound_and_tamper_fails(tmp_path) -> None:
    _, ready = _records(tmp_path)
    asset = project_multimedia_information_asset(ready, owner_id="owner-a@example.test")
    registrar = _Registrar()
    receipt = register_multimedia_information_asset(asset, registrar=registrar)
    assert registrar.seen is asset
    assert receipt.graph_node_id == f"graph-{asset.asset_id}"
    assert receipt.twin_document_id == f"twin-{asset.asset_id}"

    tampered = asset.model_copy(update={"html": asset.html + "tampered"})
    with pytest.raises(MultimediaInformationAssetError, match="digest conflicts"):
        register_multimedia_information_asset(tampered, registrar=registrar)

    class ConflictingRegistrar(_Registrar):
        def register(
            self, projected: MultimediaInformationAsset
        ) -> MultimediaKnowledgeRegistrationReceipt:
            receipt = super().register(projected)
            return receipt.model_copy(update={"revision_id": "rev-other"})

    with pytest.raises(MultimediaInformationAssetError, match="receipt conflicts"):
        register_multimedia_information_asset(asset, registrar=ConflictingRegistrar())

    class ForeignSchemaRegistrar(_Registrar):
        def register(
            self, projected: MultimediaInformationAsset
        ) -> MultimediaKnowledgeRegistrationReceipt:
            receipt = super().register(projected)
            return receipt.model_copy(update={"schema_version": "foreign.v1"})

    with pytest.raises(MultimediaInformationAssetError, match="schema conflicts"):
        register_multimedia_information_asset(asset, registrar=ForeignSchemaRegistrar())


def test_registration_rejects_invalid_graph_or_twin_identity(tmp_path) -> None:
    _, ready = _records(tmp_path)
    asset = project_multimedia_information_asset(ready, owner_id="owner-a@example.test")

    class InvalidRegistrar(_Registrar):
        def register(
            self, projected: MultimediaInformationAsset
        ) -> MultimediaKnowledgeRegistrationReceipt:
            receipt = super().register(projected)
            return receipt.model_copy(update={"twin_document_id": "../foreign"})

    with pytest.raises(MultimediaInformationAssetError, match="identity is invalid"):
        register_multimedia_information_asset(asset, registrar=InvalidRegistrar())
