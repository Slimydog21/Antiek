from substrate.write.provenance_validity import (
    edited_provenance,
    generated_validity,
    read_validity,
)


def test_partial_schema_is_repaired(tmp_path):
    import duckdb

    from substrate.graph import schema

    db_path = str(tmp_path / "graph.duckdb")
    schema.init_database_at_path(db_path)
    con = duckdb.connect(db_path)
    con.execute("DROP TABLE deliverable_section_provenance_validity")
    con.close()
    schema._INITIALIZED_PATHS.discard(db_path)
    assert schema._schema_is_present(db_path) is False
    schema.init_database_at_path(db_path)
    con = duckdb.connect(db_path, read_only=True)
    try:
        assert con.execute(
            "SELECT COUNT(*) FROM information_schema.columns WHERE "
            "table_name='deliverable_section_provenance_validity' AND "
            "column_name='validity_json'"
        ).fetchone()[0] == 1
    finally:
        con.close()


def test_malformed_structural_binding_fails_closed():
    validity = generated_validity(
        "Grounded.", {"0": ["oblk-1"]}, outline_sha256="0" * 64
    )
    validity["outline_sha256"] = "not-a-digest"
    result = read_validity("Grounded.", {"0": ["oblk-1"]}, validity)
    assert result["status"] == "legacy_unverified"


def test_prose_edit_preserves_structural_binding_for_current_mapping():
    old = generated_validity(
        "Grounded.\n\nSecond.",
        {"0": ["oblk-1"], "1": ["oblk-2"]},
        outline_sha256="a" * 64,
    )
    provenance, validity = edited_provenance(
        old_prose="Grounded.\n\nSecond.",
        new_prose="Grounded.\n\nChanged second.",
        old_provenance={"0": ["oblk-1"], "1": ["oblk-2"]},
        old_validity=old,
        origin="manual",
    )
    assert provenance == {"0": ["oblk-1"]}
    assert validity["outline_sha256"] == "a" * 64


def test_insert_before_unique_paragraphs_remaps_current_provenance():
    old = "Alpha.\n\nBeta."
    provenance = {"0": ["a"], "1": ["b"]}
    validity = generated_validity(old, provenance)
    new_provenance, new_validity = edited_provenance(
        old_prose=old,
        new_prose="New.\n\nAlpha.\n\nBeta.",
        old_provenance=provenance,
        old_validity=validity,
        origin="manual",
    )
    assert new_provenance == {"1": ["a"], "2": ["b"]}
    assert new_validity["paragraphs"]["0"]["status"] == "ungrounded"
    assert new_validity["paragraphs"]["1"]["status"] == "current"


def test_duplicate_paragraphs_are_never_matched_by_guess():
    old = "Same.\n\nSame."
    provenance = {"0": ["a"], "1": ["b"]}
    new_provenance, validity = edited_provenance(
        old_prose=old,
        new_prose="Same.\n\nSame.\n\nNew.",
        old_provenance=provenance,
        old_validity=generated_validity(old, provenance),
        origin="manual",
    )
    assert new_provenance is None
    assert [item["status"] for item in validity["paragraphs"].values()] == [
        "stale", "stale", "ungrounded"
    ]


def test_legacy_provenance_fails_closed():
    validity = read_validity("Legacy paragraph.", {"0": ["node"]}, None)
    assert validity["status"] == "legacy_unverified"
    assert validity["paragraphs"]["0"]["status"] == "legacy_unverified"


def test_generated_unsupported_paragraph_is_explicit():
    validity = generated_validity(
        "Grounded.\n\nUnsupported.",
        {"0": ["node"]},
        unsupported_paragraphs={1},
    )
    assert validity["status"] == "partial"
    assert validity["paragraphs"]["1"]["status"] == "unsupported"
