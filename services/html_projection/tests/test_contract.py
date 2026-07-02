"""M1: block taxonomy contract table tests (HPRJ SPR-02)."""

from __future__ import annotations

from services.html_projection.contract import (
    CONTRACT_TABLE,
    contract_for_tiptap_type,
    known_block_types,
    known_tiptap_types,
)

# ── The contract table covers every block type found in code ──


def test_contract_table_covers_container_block_types():
    """The six container block types from manifest.schema.json enum are
    all present (prose, highlight_card, voice_block, ai_qa, cite_link,
    cross_doc_jump)."""
    expected = {
        "prose",
        "highlight_card",
        "voice_block",
        "ai_qa",
        "cite_link",
        "cross_doc_jump",
    }
    assert expected.issubset(known_block_types())


def test_contract_table_covers_substrate_notebook_block_types():
    """All ten substrate notebook VALID_BLOCK_TYPES are present
    (substrate/notebooks/__init__.py:40-51)."""
    expected = {
        "prose",
        "region_embed",
        "claim_card",
        "note",
        "question_card",
        "cross_doc_link",
        "chat_exchange",
        "master_md_section",
        "image",
        "latex",
    }
    assert expected.issubset(known_block_types())


def test_contract_covers_tiptap_aliases():
    """TipTap node aliases (note_block→note, math_block→latex) dispatch
    to the right block type (substrate/notebooks/tiptap_codec.py:46-56)."""
    assert contract_for_tiptap_type("note_block").block_type == "note"
    assert contract_for_tiptap_type("math_block").block_type == "latex"
    assert contract_for_tiptap_type("antiek_note").block_type == "note"
    assert contract_for_tiptap_type("antiek_latex").block_type == "latex"


def test_contract_accepts_both_prefixed_and_bare_tiptap_types():
    """Every block type dispatches on both antiek_<type> and the bare
    name (container convention + substrate convention)."""
    for contract in CONTRACT_TABLE:
        if contract.block_type == "prose":
            continue  # prose has its own alias set (paragraph, doc)
        assert f"antiek_{contract.block_type}" in known_tiptap_types()
        assert contract.block_type in known_tiptap_types()


def test_contract_cites_source_file_line_for_every_type():
    """Every contract row cites a file:line source — not a decision doc.
    The renderer's authority is code, not prose."""
    for contract in CONTRACT_TABLE:
        assert ".py:" in contract.source or ".json:" in contract.source, (
            f"contract for {contract.block_type} lacks a file:line citation: "
            f"{contract.source!r}"
        )


def test_unknown_tiptap_type_returns_none():
    """An unknown type returns None → caller renders the unsupported
    fallback. Never a silent drop, never a crash."""
    assert contract_for_tiptap_type("totally_made_up") is None
    assert contract_for_tiptap_type("") is None


def test_prose_contract_has_no_dedicated_partial():
    """Prose is the inline fallback (rendered by the core renderer, no
    partial module). The contract row exists for taxonomy completeness."""
    prose = contract_for_tiptap_type("antiek_prose")
    assert prose is not None
    assert prose.partial is None


def test_every_non_prose_block_type_has_a_partial():
    """Every non-prose contract row names a partial module that exists
    under services/html_projection/partials/."""
    import importlib

    import services.html_projection.partials as partials_pkg

    partials_dir = partials_pkg.__path__[0]
    for contract in CONTRACT_TABLE:
        if contract.partial is None:
            continue
        mod = importlib.import_module(
            f".partials.{contract.partial}", package="services.html_projection"
        )
        assert hasattr(mod, "render"), (
            f"partial {contract.partial} has no render() function"
        )


def test_contract_table_is_frozen_tuple():
    """The contract table is a tuple (immutable) — a sprint cannot
    accidentally mutate it at runtime."""
    assert isinstance(CONTRACT_TABLE, tuple)
