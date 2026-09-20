from __future__ import annotations

import duckdb
import pytest
from pydantic import ValidationError

from substrate.contracts.html_projection import (
    AnchorMapping,
    HtmlProjectionContract,
    PdfPageLocator,
    SemanticLocator,
    TextLocator,
    derive_anchor_id,
    derive_projection_id,
)
from substrate.reading.projection import ProjectionConflict, ProjectionStore

SHA = "a" * 64
HTML_SHA = "b" * 64
IDENTITY = {
    "source_asset_id": "asset-1", "source_document_id": "doc-1", "source_sha256": SHA,
    "converter_id": "pdfium", "converter_version": "1.2.3",
    "sanitizer_policy": "antiek-html", "sanitizer_version": "2",
}


def projection(status: str = "queued", **changes: object) -> HtmlProjectionContract:
    values: dict[str, object] = {
        **IDENTITY, "projection_id": derive_projection_id(**IDENTITY), "status": status,
        "anchor_mappings": (),
    }
    if status == "ready":
        values.update(hosted_html_locator="objects/projection.html", hosted_html_sha256=HTML_SHA)
    if status == "failed":
        values["reason_code"] = "conversion_failed"
    if status == "review_required":
        values["reason_code"] = "anchor_review_required"
    values.update(changes)
    return HtmlProjectionContract.model_validate(values)


def test_identity_is_deterministic_and_complete() -> None:
    assert projection().projection_id == projection().projection_id
    changed = {**IDENTITY, "converter_version": "1.2.4"}
    assert projection().projection_id != derive_projection_id(**changed)


@pytest.mark.parametrize("bad_hash", ["A" * 64, "a" * 63, "g" * 64])
def test_source_hash_requires_exact_lowercase_sha256(bad_hash: str) -> None:
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        derive_projection_id(**{**IDENTITY, "source_sha256": bad_hash})


def test_coordinates_are_canonical_in_models_and_anchor_ids() -> None:
    a = PdfPageLocator(page=2, x0="0.10", y0="0.20", x1="0.90", y1="1.0")
    b = PdfPageLocator(page=2, x0="0.1", y0="0.2", x1="0.9", y1="1")
    assert a == b
    assert (a.x0, a.y0, a.x1, a.y1) == ("0.1", "0.2", "0.9", "1")
    assert derive_anchor_id(projection().projection_id, a) == derive_anchor_id(
        projection().projection_id, b
    )


def test_mapping_duplicate_guards() -> None:
    locator = SemanticLocator(semantic_id="same")
    unresolved = AnchorMapping(source_locator=locator, state="unresolved")
    with pytest.raises(ValidationError, match="duplicate source locators"):
        projection(anchor_mappings=(unresolved, unresolved))
    with pytest.raises(ValidationError, match="must be unique"):
        AnchorMapping(
            source_locator=locator, state="ambiguous", candidates=("candidate-a", "candidate-a")
        )
    mappings = (
        AnchorMapping(
            source_locator=locator, state="ambiguous", candidates=("candidate-a", "candidate-b")
        ),
        AnchorMapping(
            source_locator=SemanticLocator(semantic_id="other"), state="ambiguous",
            candidates=("candidate-c", "candidate-a"),
        ),
    )
    with pytest.raises(ValidationError, match="resolved/candidate anchor ids"):
        projection(status="review_required", anchor_mappings=mappings)


@pytest.mark.parametrize("locator", [
    "", "/absolute/x.html", "https://host/x.html", "x\\y.html", "x.html?q=1",
    "x.html#frag", "./x.html", "a/../x.html", "a/./x.html", "%2e%2e/secret.html",
    "objects/%2E%2E/secret.html",
])
def test_unsafe_hosted_html_locator_is_rejected(locator: str) -> None:
    with pytest.raises(ValidationError, match="safe relative object key"):
        projection(status="ready", hosted_html_locator=locator)


def test_reason_code_is_closed_and_status_scoped() -> None:
    with pytest.raises(ValidationError):
        projection(status="failed", reason_code="provider_secret_payload")
    with pytest.raises(ValidationError, match="allowed only"):
        projection(reason_code="storage_failed")


def test_ordered_map_round_trip_and_single_row_storage() -> None:
    con = duckdb.connect(":memory:")
    store = ProjectionStore(con)
    item = projection(anchor_mappings=(
        AnchorMapping(source_locator=SemanticLocator(semantic_id="chapter-2"), state="unresolved"),
        AnchorMapping(
            source_locator=TextLocator(start=4, end=12, text_sha256=SHA), state="ambiguous",
            candidates=("match-a", "match-b"),
        ),
    ))
    assert store.claim(item) == item
    assert store.claim(item) == item
    assert store.load(item.projection_id) == item
    assert con.execute("SELECT COUNT(*) FROM html_projections").fetchone()[0] == 1
    tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
    assert "html_projection_anchors" not in tables


def test_real_transition_constraint_failure_preserves_prior_record_and_anchor_map() -> None:
    con = duckdb.connect(":memory:")
    con.execute("""
        CREATE TABLE html_projections (
            projection_id TEXT PRIMARY KEY,
            identity_json JSON NOT NULL UNIQUE,
            projection_json JSON NOT NULL,
            CHECK (json_extract_string(projection_json, '$.status') != 'ready')
        )
    """)
    store = ProjectionStore(con)
    store.claim(projection())
    store.transition(projection("extracting"))
    unresolved = AnchorMapping(
        source_locator=SemanticLocator(semantic_id="chapter"), state="unresolved"
    )
    sanitizing = projection("sanitizing", anchor_mappings=(unresolved,))
    store.transition(sanitizing)
    resolved = AnchorMapping(
        source_locator=unresolved.source_locator,
        state="resolved",
        html_anchor_id=derive_anchor_id(projection().projection_id, unresolved.source_locator),
    )
    with pytest.raises(duckdb.ConstraintException):
        store.transition(projection("ready", anchor_mappings=(resolved,)))
    assert store.load(sanitizing.projection_id) == sanitizing


def test_store_composes_inside_caller_transaction_and_rollback() -> None:
    con = duckdb.connect(":memory:")
    store = ProjectionStore(con)
    store.ensure_tables()
    con.execute("BEGIN TRANSACTION")
    store.claim(projection())
    store.transition(projection("extracting"))
    con.execute("ROLLBACK")
    assert con.execute("SELECT COUNT(*) FROM html_projections").fetchone()[0] == 0


def test_complete_lifecycle_and_exact_replay() -> None:
    store = ProjectionStore(duckdb.connect(":memory:"))
    states = [projection(), projection("extracting"), projection("ocr_required"),
              projection("extracting"), projection("sanitizing"), projection("review_required"),
              projection("sanitizing"), projection("ready")]
    store.claim(states[0])
    for state in states[1:]:
        assert store.transition(state) == state
        assert store.transition(state) == state
    assert store.load(states[-1].projection_id).status == "ready"


def test_invalid_transition_identity_change_and_terminal_ready() -> None:
    store = ProjectionStore(duckdb.connect(":memory:"))
    store.claim(projection())
    with pytest.raises(ProjectionConflict, match="invalid.*queued->ready"):
        store.transition(projection("ready"))
    store.transition(projection("extracting"))
    changed = {**IDENTITY, "source_document_id": "other-doc"}
    forged = projection("sanitizing", source_document_id="other-doc",
                        projection_id=derive_projection_id(**changed)).model_copy(
                            update={"projection_id": projection().projection_id}
                        )
    with pytest.raises(ProjectionConflict, match="identity is immutable"):
        store.transition(forged)
    store.transition(projection("sanitizing"))
    store.transition(projection("ready"))
    with pytest.raises(ProjectionConflict, match="invalid.*ready->failed"):
        store.transition(projection("failed"))


def test_failed_retry_requires_same_identity_and_clean_queued_state() -> None:
    store = ProjectionStore(duckdb.connect(":memory:"))
    store.claim(projection())
    store.transition(projection("extracting"))
    store.transition(projection("failed"))
    assert store.transition(projection()) == projection()


def test_resolved_anchors_are_ready_only_and_review_is_unresolved() -> None:
    locator = SemanticLocator(semantic_id="chapter")
    anchor = derive_anchor_id(projection().projection_id, locator)
    resolved = AnchorMapping(source_locator=locator, state="resolved", html_anchor_id=anchor)
    with pytest.raises(ValidationError, match="allowed only for ready"):
        projection("sanitizing", anchor_mappings=(resolved,))
    unresolved = AnchorMapping(source_locator=locator, state="unresolved")
    assert projection("review_required", anchor_mappings=(unresolved,)).anchor_mappings
    assert projection("ready", anchor_mappings=(resolved,)).anchor_mappings
    forged = AnchorMapping(source_locator=locator, state="resolved", html_anchor_id="forged-anchor")
    with pytest.raises(ValidationError, match="canonical derived anchor"):
        projection("ready", anchor_mappings=(forged,))
