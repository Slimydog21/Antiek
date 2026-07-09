from __future__ import annotations

from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app


def _client() -> TestClient:
    return TestClient(create_app(register_wrestling=False, register_providers=False))


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
