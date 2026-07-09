from __future__ import annotations

from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from interfaces.research.api.books import _chunk_book_html_for_research
from processing.embedding import (
    HashEmbedding,
    _reset_default_provider,
    embedding_provider_fingerprint,
    set_default_embedding_provider,
)
from runtime.db_lock import connect_read
from substrate.graph import default_db_path


def _client() -> TestClient:
    return TestClient(create_app(register_wrestling=False, register_providers=False))


def test_html_publish_chunker_indexes_visible_text_only() -> None:
    chunks = _chunk_book_html_for_research(
        "<article><h1>Wing sweep</h1><p>Delta wings delay shock formation.</p>"
        "<script>do not index this hidden prompt</script></article>"
    )

    assert chunks == ["Wing sweep\n\nDelta wings delay shock formation."]


def test_purchase_request_requires_manual_no_spend_ack() -> None:
    client = _client()

    resp = client.post(
        "/books/marketplace/purchase-request",
        json={
            "title": "The Dream Machine",
            "author": "M. Mitchell Waldrop",
            "max_price_usd_cents": 2_500,
            "acknowledge_manual_purchase_only": False,
        },
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "manual_purchase_ack_required"


def test_purchase_request_is_precheckout_no_external_action_contract() -> None:
    client = _client()

    resp = client.post(
        "/books/marketplace/purchase-request",
        json={
            "title": "The Dream Machine",
            "author": "M. Mitchell Waldrop",
            "source_url": "https://example.com/book",
            "store": "publisher",
            "max_price_usd_cents": 2_500,
            "desired_format": "epub",
            "acknowledge_manual_purchase_only": True,
        },
    )

    assert resp.status_code == 202
    body = resp.json()
    assert body["request_id"].startswith("bookreq-")
    assert body["status"] == "needs_operator_purchase"
    assert body["title"] == "The Dream Machine"
    assert body["import_target"] == "antiek_html"
    assert body["purchase_allowed"] is False
    assert body["external_call_performed"] is False
    assert body["spend_reserved_usd_cents"] == 0
    assert body["charge_attempted"] is False
    assert body["ingest_attempted"] is False
    assert body["html_hosting_required"] is True
    assert any("No checkout" in note for note in body["policy_notes"])


def test_html_import_preflight_requires_ack_and_legal_access() -> None:
    client = _client()

    missing_ack = client.post(
        "/books/import/html-preflight",
        json={
            "title": "The Dream Machine",
            "has_legal_access": True,
            "acknowledge_no_upload_or_ingest": False,
        },
    )
    assert missing_ack.status_code == 400
    assert missing_ack.json()["detail"] == "html_import_preflight_ack_required"

    missing_rights = client.post(
        "/books/import/html-preflight",
        json={
            "title": "The Dream Machine",
            "has_legal_access": False,
            "acknowledge_no_upload_or_ingest": True,
        },
    )
    assert missing_rights.status_code == 400
    assert missing_rights.json()["detail"] == "legal_access_required"


def test_html_import_preflight_is_no_upload_no_ingest_contract() -> None:
    client = _client()

    resp = client.post(
        "/books/import/html-preflight",
        json={
            "title": "The Dream Machine",
            "author": "M. Mitchell Waldrop",
            "source_request_id": "bookreq-safe123",
            "file_name": "dream-machine.epub",
            "file_format": "epub",
            "has_legal_access": True,
            "acknowledge_no_upload_or_ingest": True,
        },
    )

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["import_preflight_id"].startswith("bookimp-")
    assert body["status"] == "ready_for_operator_file"
    assert body["source_request_id"] == "bookreq-safe123"
    assert body["import_target"] == "antiek_html"
    assert body["external_call_performed"] is False
    assert body["file_uploaded"] is False
    assert body["file_read_attempted"] is False
    assert body["ingest_attempted"] is False
    assert body["graph_mutation_performed"] is False
    assert body["html_conversion_required"] is True
    assert body["html_hosting_required"] is True
    assert any("No upload" in note for note in body["policy_notes"])


def test_html_file_handoff_requires_valid_preflight_and_no_read_ack() -> None:
    client = _client()

    invalid_preflight = client.post(
        "/books/import/file-handoff",
        json={
            "import_preflight_id": "not-a-preflight",
            "file_name": "dream-machine.epub",
            "file_format": "epub",
            "storage_ref": "operator-vault://books/dream-machine.epub",
            "acknowledge_manual_storage_only": True,
            "acknowledge_no_file_read_or_conversion": True,
        },
    )
    assert invalid_preflight.status_code == 400
    assert invalid_preflight.json()["detail"] == "invalid_import_preflight_id"

    missing_manual_ack = client.post(
        "/books/import/file-handoff",
        json={
            "import_preflight_id": "bookimp-safe123",
            "file_name": "dream-machine.epub",
            "file_format": "epub",
            "storage_ref": "operator-vault://books/dream-machine.epub",
            "acknowledge_manual_storage_only": False,
            "acknowledge_no_file_read_or_conversion": True,
        },
    )
    assert missing_manual_ack.status_code == 400
    assert missing_manual_ack.json()["detail"] == "manual_storage_ack_required"

    missing_no_read_ack = client.post(
        "/books/import/file-handoff",
        json={
            "import_preflight_id": "bookimp-safe123",
            "file_name": "dream-machine.epub",
            "file_format": "epub",
            "storage_ref": "operator-vault://books/dream-machine.epub",
            "acknowledge_manual_storage_only": True,
            "acknowledge_no_file_read_or_conversion": False,
        },
    )
    assert missing_no_read_ack.status_code == 400
    assert missing_no_read_ack.json()["detail"] == "file_handoff_no_read_ack_required"


def test_html_file_handoff_records_metadata_without_reading_or_converting() -> None:
    client = _client()
    checksum = "a" * 64

    resp = client.post(
        "/books/import/file-handoff",
        json={
            "import_preflight_id": "bookimp-safe123",
            "file_name": "dream-machine.epub",
            "file_format": "epub",
            "storage_ref": "operator-vault://books/dream-machine.epub",
            "checksum_sha256": checksum,
            "acknowledge_manual_storage_only": True,
            "acknowledge_no_file_read_or_conversion": True,
        },
    )

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["handoff_id"].startswith("bookhand-")
    assert body["status"] == "ready_for_conversion_review"
    assert body["import_preflight_id"] == "bookimp-safe123"
    assert body["storage_ref_recorded"] is True
    assert body["upload_accepted"] is False
    assert body["external_call_performed"] is False
    assert body["file_read_attempted"] is False
    assert body["conversion_attempted"] is False
    assert body["ingest_attempted"] is False
    assert body["graph_mutation_performed"] is False
    assert body["html_conversion_required"] is True
    assert body["html_hosting_required"] is True
    assert body["checksum_sha256"] == checksum
    assert any("No upload bytes" in note for note in body["policy_notes"])


def test_html_conversion_review_requires_valid_ids_and_acknowledgements() -> None:
    client = _client()

    invalid_handoff = client.post(
        "/books/import/conversion-review",
        json={
            "handoff_id": "not-a-handoff",
            "import_preflight_id": "bookimp-safe123",
            "converter": "pandoc",
            "sandbox_profile": "locked_down",
            "acknowledge_sandbox_required": True,
            "acknowledge_no_conversion_run": True,
        },
    )
    assert invalid_handoff.status_code == 400
    assert invalid_handoff.json()["detail"] == "invalid_handoff_id"

    missing_sandbox_ack = client.post(
        "/books/import/conversion-review",
        json={
            "handoff_id": "bookhand-safe123",
            "import_preflight_id": "bookimp-safe123",
            "converter": "pandoc",
            "sandbox_profile": "locked_down",
            "acknowledge_sandbox_required": False,
            "acknowledge_no_conversion_run": True,
        },
    )
    assert missing_sandbox_ack.status_code == 400
    assert missing_sandbox_ack.json()["detail"] == "conversion_sandbox_ack_required"

    missing_no_run_ack = client.post(
        "/books/import/conversion-review",
        json={
            "handoff_id": "bookhand-safe123",
            "import_preflight_id": "bookimp-safe123",
            "converter": "pandoc",
            "sandbox_profile": "locked_down",
            "acknowledge_sandbox_required": True,
            "acknowledge_no_conversion_run": False,
        },
    )
    assert missing_no_run_ack.status_code == 400
    assert missing_no_run_ack.json()["detail"] == "conversion_no_run_ack_required"


def test_html_conversion_review_is_no_run_no_write_contract() -> None:
    client = _client()

    resp = client.post(
        "/books/import/conversion-review",
        json={
            "handoff_id": "bookhand-safe123",
            "import_preflight_id": "bookimp-safe123",
            "converter": "pandoc",
            "sandbox_profile": "locked_down",
            "acknowledge_sandbox_required": True,
            "acknowledge_no_conversion_run": True,
        },
    )

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["conversion_review_id"].startswith("bookconv-")
    assert body["status"] == "ready_for_explicit_conversion_job"
    assert body["handoff_id"] == "bookhand-safe123"
    assert body["import_preflight_id"] == "bookimp-safe123"
    assert body["converter"] == "pandoc"
    assert body["sandbox_profile"] == "locked_down"
    assert body["output_format"] == "antiek_html"
    assert body["storage_ref_read"] is False
    assert body["file_read_attempted"] is False
    assert body["conversion_attempted"] is False
    assert body["output_written"] is False
    assert body["ingest_attempted"] is False
    assert body["graph_mutation_performed"] is False
    assert body["html_hosting_required"] is True
    assert body["serve_gate_required"] is True
    assert any("No converter ran" in note for note in body["policy_notes"])


def test_html_conversion_result_requires_valid_ids_and_publish_ack() -> None:
    client = _client()

    invalid_review = client.post(
        "/books/import/conversion-result",
        json={
            "conversion_review_id": "not-a-review",
            "handoff_id": "bookhand-safe123",
            "html_output_ref": "operator-vault://books/dream-machine/index.html",
            "acknowledge_output_metadata_only": True,
            "acknowledge_no_publish_or_serve": True,
        },
    )
    assert invalid_review.status_code == 400
    assert invalid_review.json()["detail"] == "invalid_conversion_review_id"

    missing_metadata_ack = client.post(
        "/books/import/conversion-result",
        json={
            "conversion_review_id": "bookconv-safe123",
            "handoff_id": "bookhand-safe123",
            "html_output_ref": "operator-vault://books/dream-machine/index.html",
            "acknowledge_output_metadata_only": False,
            "acknowledge_no_publish_or_serve": True,
        },
    )
    assert missing_metadata_ack.status_code == 400
    assert missing_metadata_ack.json()["detail"] == "output_metadata_ack_required"

    missing_publish_ack = client.post(
        "/books/import/conversion-result",
        json={
            "conversion_review_id": "bookconv-safe123",
            "handoff_id": "bookhand-safe123",
            "html_output_ref": "operator-vault://books/dream-machine/index.html",
            "acknowledge_output_metadata_only": True,
            "acknowledge_no_publish_or_serve": False,
        },
    )
    assert missing_publish_ack.status_code == 400
    assert missing_publish_ack.json()["detail"] == "no_publish_or_serve_ack_required"


def test_html_conversion_result_records_output_metadata_without_publish_or_serve() -> None:
    client = _client()
    checksum = "b" * 64

    resp = client.post(
        "/books/import/conversion-result",
        json={
            "conversion_review_id": "bookconv-safe123",
            "handoff_id": "bookhand-safe123",
            "html_output_ref": "operator-vault://books/dream-machine/index.html",
            "html_checksum_sha256": checksum,
            "page_count_estimate": 340,
            "acknowledge_output_metadata_only": True,
            "acknowledge_no_publish_or_serve": True,
        },
    )

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["conversion_result_id"].startswith("bookout-")
    assert body["status"] == "ready_for_serve_gate_review"
    assert body["conversion_review_id"] == "bookconv-safe123"
    assert body["handoff_id"] == "bookhand-safe123"
    assert body["html_output_ref"] == "operator-vault://books/dream-machine/index.html"
    assert body["html_checksum_sha256"] == checksum
    assert body["page_count_estimate"] == 340
    assert body["output_metadata_recorded"] is True
    assert body["output_ref_fetched"] is False
    assert body["html_output_read"] is False
    assert body["ingest_attempted"] is False
    assert body["graph_mutation_performed"] is False
    assert body["shelf_publication_attempted"] is False
    assert body["full_text_served"] is False
    assert body["serve_gate_required"] is True
    assert any("metadata was recorded" in note for note in body["policy_notes"])


def test_html_serve_gate_review_requires_valid_result_and_acknowledgements() -> None:
    client = _client()

    invalid_result = client.post(
        "/books/import/serve-gate-review",
        json={
            "conversion_result_id": "not-a-result",
            "title": "The Dream Machine",
            "rights_basis": "personal_license",
            "servability_decision": "servable_full_text",
            "acknowledge_rights_reviewed": True,
            "acknowledge_no_publication": True,
        },
    )
    assert invalid_result.status_code == 400
    assert invalid_result.json()["detail"] == "invalid_conversion_result_id"

    missing_rights_ack = client.post(
        "/books/import/serve-gate-review",
        json={
            "conversion_result_id": "bookout-safe123",
            "title": "The Dream Machine",
            "rights_basis": "personal_license",
            "servability_decision": "servable_full_text",
            "acknowledge_rights_reviewed": False,
            "acknowledge_no_publication": True,
        },
    )
    assert missing_rights_ack.status_code == 400
    assert missing_rights_ack.json()["detail"] == "rights_review_ack_required"

    missing_publication_ack = client.post(
        "/books/import/serve-gate-review",
        json={
            "conversion_result_id": "bookout-safe123",
            "title": "The Dream Machine",
            "rights_basis": "personal_license",
            "servability_decision": "servable_full_text",
            "acknowledge_rights_reviewed": True,
            "acknowledge_no_publication": False,
        },
    )
    assert missing_publication_ack.status_code == 400
    assert missing_publication_ack.json()["detail"] == "no_publication_ack_required"


def test_html_serve_gate_review_records_rights_without_publishing() -> None:
    client = _client()

    resp = client.post(
        "/books/import/serve-gate-review",
        json={
            "conversion_result_id": "bookout-safe123",
            "title": "The Dream Machine",
            "author": "M. Mitchell Waldrop",
            "rights_basis": "personal_license",
            "servability_decision": "servable_full_text",
            "acknowledge_rights_reviewed": True,
            "acknowledge_no_publication": True,
        },
    )

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["serve_gate_review_id"].startswith("bookserve-")
    assert body["status"] == "ready_for_publication_request"
    assert body["conversion_result_id"] == "bookout-safe123"
    assert body["title"] == "The Dream Machine"
    assert body["rights_basis"] == "personal_license"
    assert body["servability_decision"] == "servable_full_text"
    assert body["rights_review_recorded"] is True
    assert body["html_output_read"] is False
    assert body["ingest_attempted"] is False
    assert body["graph_mutation_performed"] is False
    assert body["shelf_publication_attempted"] is False
    assert body["full_text_served"] is False
    assert body["publication_allowed_next"] is True
    assert any("servability review metadata" in note for note in body["policy_notes"])


def test_html_serve_gate_review_blocks_nonservable_decision() -> None:
    client = _client()

    resp = client.post(
        "/books/import/serve-gate-review",
        json={
            "conversion_result_id": "bookout-safe123",
            "title": "The Dream Machine",
            "rights_basis": "unknown",
            "servability_decision": "gated_metadata_only",
            "acknowledge_rights_reviewed": True,
            "acknowledge_no_publication": True,
        },
    )

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "blocked"
    assert body["publication_allowed_next"] is False
    assert body["shelf_publication_attempted"] is False
    assert body["full_text_served"] is False


def test_html_publication_request_requires_valid_ids_and_acknowledgements() -> None:
    client = _client()

    invalid_review = client.post(
        "/books/import/publication-request",
        json={
            "serve_gate_review_id": "not-a-serve-gate",
            "conversion_result_id": "bookout-safe123",
            "shelf_visibility": "private_library",
            "acknowledge_publication_intent": True,
            "acknowledge_no_ingest_or_serve": True,
        },
    )
    assert invalid_review.status_code == 400
    assert invalid_review.json()["detail"] == "invalid_serve_gate_review_id"

    missing_publication_ack = client.post(
        "/books/import/publication-request",
        json={
            "serve_gate_review_id": "bookserve-safe123",
            "conversion_result_id": "bookout-safe123",
            "shelf_visibility": "private_library",
            "acknowledge_publication_intent": False,
            "acknowledge_no_ingest_or_serve": True,
        },
    )
    assert missing_publication_ack.status_code == 400
    assert missing_publication_ack.json()["detail"] == "publication_intent_ack_required"

    missing_no_ingest_ack = client.post(
        "/books/import/publication-request",
        json={
            "serve_gate_review_id": "bookserve-safe123",
            "conversion_result_id": "bookout-safe123",
            "shelf_visibility": "private_library",
            "acknowledge_publication_intent": True,
            "acknowledge_no_ingest_or_serve": False,
        },
    )
    assert missing_no_ingest_ack.status_code == 400
    assert missing_no_ingest_ack.json()["detail"] == "no_ingest_or_serve_ack_required"


def test_html_publication_request_records_intent_without_ingest_or_serve() -> None:
    client = _client()

    resp = client.post(
        "/books/import/publication-request",
        json={
            "serve_gate_review_id": "bookserve-safe123",
            "conversion_result_id": "bookout-safe123",
            "document_id_hint": "book-dream-machine",
            "shelf_visibility": "private_library",
            "acknowledge_publication_intent": True,
            "acknowledge_no_ingest_or_serve": True,
        },
    )

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["publication_request_id"].startswith("bookpub-")
    assert body["status"] == "ready_for_explicit_publish_job"
    assert body["serve_gate_review_id"] == "bookserve-safe123"
    assert body["conversion_result_id"] == "bookout-safe123"
    assert body["document_id_hint"] == "book-dream-machine"
    assert body["shelf_visibility"] == "private_library"
    assert body["publication_intent_recorded"] is True
    assert body["ingest_attempted"] is False
    assert body["graph_mutation_performed"] is False
    assert body["shelf_publication_attempted"] is False
    assert body["full_text_served"] is False
    assert body["reader_route_created"] is False
    assert any("Publication intent" in note for note in body["policy_notes"])


def test_html_publish_job_requires_final_write_acknowledgements() -> None:
    client = _client()

    missing_write_ack = client.post(
        "/books/import/publish-job",
        json={
            "publication_request_id": "bookpub-safe123",
            "serve_gate_review_id": "bookserve-safe123",
            "document_id": "book-dream-machine",
            "title": "The Dream Machine",
            "html_body": "<article><h1>The Dream Machine</h1></article>",
            "rights_basis": "personal_license",
            "license_basis": "Operator-owned copy for private Antiek library.",
            "acknowledge_write_to_library": False,
            "acknowledge_full_text_servable": True,
        },
    )
    assert missing_write_ack.status_code == 400
    assert missing_write_ack.json()["detail"] == "write_to_library_ack_required"

    missing_servable_ack = client.post(
        "/books/import/publish-job",
        json={
            "publication_request_id": "bookpub-safe123",
            "serve_gate_review_id": "bookserve-safe123",
            "document_id": "book-dream-machine",
            "title": "The Dream Machine",
            "html_body": "<article><h1>The Dream Machine</h1></article>",
            "rights_basis": "personal_license",
            "license_basis": "Operator-owned copy for private Antiek library.",
            "acknowledge_write_to_library": True,
            "acknowledge_full_text_servable": False,
        },
    )
    assert missing_servable_ack.status_code == 400
    assert missing_servable_ack.json()["detail"] == "full_text_servable_ack_required"


def test_html_publish_job_writes_book_through_existing_serve_gate() -> None:
    client = _client()

    resp = client.post(
        "/books/import/publish-job",
        json={
            "publication_request_id": "bookpub-safe123",
            "serve_gate_review_id": "bookserve-safe123",
            "document_id": "book-dream-machine",
            "title": "The Dream Machine",
            "author": "M. Mitchell Waldrop",
            "html_body": "<article><h1>The Dream Machine</h1><p>Networked computing history.</p></article>",
            "rights_basis": "personal_license",
            "page_count": 340,
            "license_basis": "Operator-owned copy for private Antiek library.",
            "acknowledge_write_to_library": True,
            "acknowledge_full_text_servable": True,
        },
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["publish_job_id"].startswith("bookjob-")
    assert body["status"] == "published_to_private_library"
    assert body["document_id"] == "book-dream-machine"
    assert body["content_class"] == "user_owned"
    assert body["servable_full_text"] is True
    assert body["document_inserted"] is True
    assert body["book_asset_registered"] is True
    assert body["chunks_indexed"] == 1
    assert body["chunked_for_research"] is True
    assert body["graph_mutation_performed"] is True
    assert body["shelf_publication_attempted"] is True
    assert body["reader_route_created"] is True
    assert body["full_text_served"] is False
    assert body["open_route"] == "/read/book-dream-machine"

    detail = client.get("/books/book-dream-machine")
    assert detail.status_code == 200, detail.text
    detail_body = detail.json()
    assert detail_body["document_id"] == "book-dream-machine"
    assert detail_body["servable_full_text"] is True
    assert detail_body["page_count"] == 340
    assert detail_body["pagination_scheme"] == "html_section"

    served = client.get("/books/book-dream-machine/full-text")
    assert served.status_code == 200, served.text
    assert served.json()["full_text"].startswith("<article>")

    con = connect_read(default_db_path())
    try:
        chunks = con.execute(
            "SELECT section_path, text, token_count FROM chunks WHERE document_id = ?",
            ["book-dream-machine"],
        ).fetchall()
    finally:
        con.close()
    assert len(chunks) == 1
    assert chunks[0][0] == "HTML section 1"
    assert "Networked computing history." in chunks[0][1]
    assert chunks[0][2] >= 5
    served_body = served.json()
    assert served_body["servable"] is True
    assert served_body["reason"] == "servable"
    assert served_body["full_text"] == (
        "<article><h1>The Dream Machine</h1><p>Networked computing history.</p></article>"
    )


def test_html_index_job_embeds_published_book_chunks_explicitly() -> None:
    client = _client()
    provider = HashEmbedding(dimension=8)
    set_default_embedding_provider(provider)
    try:
        published = client.post(
            "/books/import/publish-job",
            json={
                "publication_request_id": "bookpub-index123",
                "serve_gate_review_id": "bookserve-index123",
                "document_id": "book-indexable",
                "title": "Indexable Book",
                "html_body": "<article><h1>Indexable</h1><p>Vector searchable passage.</p></article>",
                "rights_basis": "personal_license",
                "license_basis": "Operator-owned copy for private Antiek library.",
                "acknowledge_write_to_library": True,
                "acknowledge_full_text_servable": True,
            },
        )
        assert published.status_code == 201, published.text
        publish_job_id = published.json()["publish_job_id"]

        dry_run = client.post(
            "/books/import/index-job",
            json={
                "document_id": "book-indexable",
                "publish_job_id": publish_job_id,
            },
        )
        assert dry_run.status_code == 202, dry_run.text
        dry_body = dry_run.json()
        assert dry_body["status"] == "dry_run_ready"
        assert dry_body["applied"] is False
        assert dry_body["chunks_found"] == 1
        assert dry_body["chunks_embedded_before"] == 0
        assert dry_body["vectors_rewritten"] == 0
        assert dry_body["graph_mutation_performed"] is False

        missing_ack = client.post(
            "/books/import/index-job",
            json={
                "document_id": "book-indexable",
                "publish_job_id": publish_job_id,
                "apply": True,
            },
        )
        assert missing_ack.status_code == 400
        assert missing_ack.json()["detail"] == "embedding_compute_ack_required"

        hash_refused = client.post(
            "/books/import/index-job",
            json={
                "document_id": "book-indexable",
                "publish_job_id": publish_job_id,
                "apply": True,
                "acknowledge_embedding_compute": True,
            },
        )
        assert hash_refused.status_code == 400
        assert hash_refused.json()["detail"] == "hash_provider_refused"

        applied = client.post(
            "/books/import/index-job",
            json={
                "document_id": "book-indexable",
                "publish_job_id": publish_job_id,
                "apply": True,
                "acknowledge_embedding_compute": True,
                "allow_hash_provider": True,
            },
        )
        assert applied.status_code == 202, applied.text
        body = applied.json()
        assert body["index_job_id"].startswith("bookidx-")
        assert body["status"] == "indexed_for_vector_search"
        assert body["provider"] == "hash"
        assert body["model_name"] == "hash-dim-8"
        assert body["provider_is_hash"] is True
        assert body["applied"] is True
        assert body["chunks_found"] == 1
        assert body["chunks_embedded_before"] == 0
        assert body["vectors_rewritten"] == 1
        assert body["graph_mutation_performed"] is True
        assert body["count_preserved"] is True
        assert body["searchable_after_apply"] is True

        con = connect_read(default_db_path())
        try:
            row = con.execute(
                "SELECT c.embedding, m.provider, m.model_name, m.dimension, m.fingerprint "
                "FROM chunks c JOIN embeddings_meta m ON c.chunk_id = m.chunk_id "
                "WHERE c.document_id = ?",
                ["book-indexable"],
            ).fetchone()
        finally:
            con.close()
        assert row is not None
        assert len(row[0]) == 8
        assert row[1:] == (
            "hash",
            "hash-dim-8",
            8,
            embedding_provider_fingerprint(provider),
        )
    finally:
        _reset_default_provider()
