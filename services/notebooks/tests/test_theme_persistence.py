"""SPR-11 M7 — server-side per-theme notebook tests.

Five acceptance scopes, mapped one-to-one to the sprint HTML M7
acceptance criteria + the rigor #3 stale-block gate:

- Unit: promote single block → theme_blocks row exists; multi-select
  promote → N rows.
- Unit: reorder → sort_order matches expected.
- Unit (rigor #3): create theme with 3 blocks → delete one source
  notebook row → reload theme → 2 live + 1 stale placeholder.
- Native save: round-trip via save_theme_as_antiek /
  load_theme_from_antiek with content_class="theme_notebook" +
  source_notebook_ids in manifest.
- Slug allocation: collision suffixes.

Per the rigor mandate in sprint HTML M7, these tests use REAL
DuckDB state (not in-memory dicts) — the conftest fixture spins
up a per-test DuckDB file with the substrate.behavior + notebooks
schemas applied. Identical fixture pattern to
test_auto_populate.py.
"""

from __future__ import annotations

import json
import os
from typing import Any

import duckdb
import pytest

from services.notebooks.persistence import (
    BlockRecord,
    JSONPersistence,
    new_block_id,
)
from services.notebooks.theme_persistence import (
    ThemePersistence,
    load_theme_from_antiek,
    save_theme_as_antiek,
    slugify,
)


USER = "__operator__"


# ── Helpers ──


def _seed_notebook(
    persistence: JSONPersistence,
    *,
    document_id: str,
    block_types: list[str],
) -> list[str]:
    """Seed a per-doc notebook with N blocks; return block_ids."""
    nb = persistence.get_or_create_notebook(
        user_id=USER, document_id=document_id
    )
    nb.title = f"Notebook for {document_id}"
    blocks: list[BlockRecord] = []
    ids: list[str] = []
    for i, bt in enumerate(block_types, start=1):
        bid = new_block_id()
        ids.append(bid)
        # Prose is allowed without source events; everything else
        # needs one (per services.notebooks.blocks invariant).
        source_event_ids = [] if bt == "prose" else [f"evt-{i}-{bid[-6:]}"]
        blocks.append(
            BlockRecord(
                block_id=bid,
                notebook_id=nb.notebook_id,
                block_type=bt,
                source_event_ids=source_event_ids,
                content_json={"sample_for_block": bid},
                position=float(i),
                document_id=document_id,
            )
        )
    nb.blocks = blocks
    persistence.save_notebook(nb)
    return ids


# ── Slugify ──


def test_slugify_basic() -> None:
    assert slugify("Quantum Computing") == "quantum-computing"
    assert slugify("Multi-Doc Themes!") == "multi-doc-themes"
    assert slugify("   ") == "theme"  # empty / whitespace falls back
    assert slugify("Special — chars & symbols") == "special-chars-symbols"


def test_allocate_slug_collisions(combined_db: str) -> None:
    tp = ThemePersistence(db_path=combined_db)
    tp.create_theme(user_id=USER, title="Same Title")
    s2 = tp.allocate_slug(user_id=USER, title="Same Title")
    assert s2 == "same-title-2"
    tp.create_theme(user_id=USER, title="Same Title", slug=s2)
    s3 = tp.allocate_slug(user_id=USER, title="Same Title")
    assert s3 == "same-title-3"


# ── Promote ──


def test_promote_single_block(
    combined_db: str, persistence: JSONPersistence
) -> None:
    """Acceptance: promote one block → exactly one theme_blocks row."""
    [source_block_id] = _seed_notebook(
        persistence, document_id="doc-A", block_types=["highlight_card"]
    )
    tp = ThemePersistence(db_path=combined_db)
    theme = tp.create_theme(user_id=USER, title="Solo Theme")
    tb = tp.promote_block(
        theme_id=theme.theme_id, source_block_id=source_block_id
    )
    assert tb.source_block_id == source_block_id
    assert tb.block_type == "highlight_card"
    # Cached content is preserved on the theme_block row.
    assert tb.content_json["sample_for_block"] == source_block_id

    loaded = tp.load_theme_by_id(theme.theme_id)
    assert loaded is not None
    assert len(loaded.blocks) == 1
    assert loaded.blocks[0].source_block_id == source_block_id


def test_promote_multi_select(
    combined_db: str, persistence: JSONPersistence
) -> None:
    """Acceptance: multi-select promote N blocks → N rows in order."""
    source_ids = _seed_notebook(
        persistence,
        document_id="doc-A",
        block_types=["highlight_card", "voice_block", "ai_qa"],
    )
    tp = ThemePersistence(db_path=combined_db)
    theme = tp.create_theme(user_id=USER, title="Multi")
    tbs = tp.promote_blocks(
        theme_id=theme.theme_id, source_block_ids=source_ids
    )
    assert len(tbs) == 3

    loaded = tp.load_theme_by_id(theme.theme_id)
    assert loaded is not None
    assert [b.source_block_id for b in loaded.blocks] == source_ids


def test_promote_unknown_source_raises(combined_db: str) -> None:
    tp = ThemePersistence(db_path=combined_db)
    theme = tp.create_theme(user_id=USER, title="Bad Source")
    with pytest.raises(KeyError, match="not found"):
        tp.promote_block(
            theme_id=theme.theme_id, source_block_id="blk-does-not-exist"
        )


# ── Reorder ──


def test_reorder_updates_sort_order(
    combined_db: str, persistence: JSONPersistence
) -> None:
    """Acceptance: reorder → sort_order matches expected (1, 2, 3, ...)."""
    source_ids = _seed_notebook(
        persistence,
        document_id="doc-A",
        block_types=["highlight_card", "voice_block", "ai_qa"],
    )
    tp = ThemePersistence(db_path=combined_db)
    theme = tp.create_theme(user_id=USER, title="Reorder")
    tbs = tp.promote_blocks(
        theme_id=theme.theme_id, source_block_ids=source_ids
    )

    # Reverse the order.
    new_order = [tbs[2].theme_block_id, tbs[1].theme_block_id, tbs[0].theme_block_id]
    tp.reorder_blocks(theme_id=theme.theme_id, ordered_theme_block_ids=new_order)

    loaded = tp.load_theme_by_id(theme.theme_id)
    assert loaded is not None
    assert [b.theme_block_id for b in loaded.blocks] == new_order
    assert [b.sort_order for b in loaded.blocks] == [1.0, 2.0, 3.0]


# ── Stale-block handling (rigor #3) ──


def test_stale_block_placeholder_after_source_delete(
    combined_db: str, persistence: JSONPersistence
) -> None:
    """Rigor #3 — sprint HTML calls this test out by name.

    Create theme with 3 blocks → delete one source notebook block →
    reload theme → 2 live + 1 stale (with cached content).
    The naive impl will crash or silently drop the row; both wrong.
    """
    source_ids = _seed_notebook(
        persistence,
        document_id="doc-A",
        block_types=["highlight_card", "voice_block", "ai_qa"],
    )
    tp = ThemePersistence(db_path=combined_db)
    theme = tp.create_theme(user_id=USER, title="Stale-test")
    tp.promote_blocks(theme_id=theme.theme_id, source_block_ids=source_ids)

    # Delete one source block directly in the DB (simulates source
    # document being removed / re-imported / auto-populator rebuild).
    con = duckdb.connect(combined_db)
    con.execute(
        "DELETE FROM per_doc_notebook_blocks WHERE block_id = ?", [source_ids[1]]
    )
    con.close()

    loaded = tp.load_theme_by_id(theme.theme_id)
    assert loaded is not None, "theme vanished on source delete (must NOT)"
    assert len(loaded.blocks) == 3, "row count must be unchanged"

    stale = [b for b in loaded.blocks if b.is_stale]
    live = [b for b in loaded.blocks if not b.is_stale]
    assert len(stale) == 1
    assert len(live) == 2

    # The cached content_json is what the stale placeholder renders.
    assert stale[0].content_json.get("sample_for_block") == source_ids[1]


def test_dismiss_stale_hides_row(
    combined_db: str, persistence: JSONPersistence
) -> None:
    [src_id] = _seed_notebook(
        persistence, document_id="doc-A", block_types=["highlight_card"]
    )
    tp = ThemePersistence(db_path=combined_db)
    theme = tp.create_theme(user_id=USER, title="Dismiss")
    tb = tp.promote_block(
        theme_id=theme.theme_id, source_block_id=src_id
    )
    # Delete source.
    con = duckdb.connect(combined_db)
    con.execute("DELETE FROM per_doc_notebook_blocks WHERE block_id = ?", [src_id])
    con.close()

    loaded = tp.load_theme_by_id(theme.theme_id)
    assert loaded is not None and len(loaded.blocks) == 1
    assert loaded.blocks[0].is_stale is True

    tp.dismiss_stale(theme_block_id=tb.theme_block_id)
    loaded2 = tp.load_theme_by_id(theme.theme_id)
    assert loaded2 is not None and len(loaded2.blocks) == 0


# ── Removing a theme block leaves source untouched ──


def test_remove_block_keeps_source(
    combined_db: str, persistence: JSONPersistence
) -> None:
    [src_id] = _seed_notebook(
        persistence, document_id="doc-A", block_types=["highlight_card"]
    )
    tp = ThemePersistence(db_path=combined_db)
    theme = tp.create_theme(user_id=USER, title="Remove")
    tb = tp.promote_block(theme_id=theme.theme_id, source_block_id=src_id)
    tp.remove_block(theme_block_id=tb.theme_block_id)

    # Source survives.
    con = duckdb.connect(combined_db)
    row = con.execute(
        "SELECT block_id FROM per_doc_notebook_blocks WHERE block_id = ?", [src_id]
    ).fetchone()
    con.close()
    assert row is not None, "remove_block must NOT cascade to source"


# ── Prose-inside-theme is allowed (Tier-3 framing) ──


def test_prose_block_inside_theme(combined_db: str) -> None:
    tp = ThemePersistence(db_path=combined_db)
    theme = tp.create_theme(user_id=USER, title="Prose")
    prose = tp.insert_prose_block(
        theme_id=theme.theme_id,
        content_json={"text": "operator framing"},
    )
    assert prose.block_type == "prose"
    assert prose.source_block_id is None  # prose has no source

    loaded = tp.load_theme_by_id(theme.theme_id)
    assert loaded is not None
    assert any(b.block_type == "prose" for b in loaded.blocks)


# ── .antiek round-trip ──


def test_save_theme_as_antiek_roundtrip(
    combined_db: str, persistence: JSONPersistence, tmp_path: Any
) -> None:
    """M5 acceptance: save → reload → equivalent. Manifest carries
    content_class='theme_notebook' + source_notebook_ids."""
    source_ids = _seed_notebook(
        persistence,
        document_id="doc-A",
        block_types=["highlight_card", "voice_block"],
    )
    source_notebook_id = (
        persistence.load_notebook(user_id=USER, document_id="doc-A")
        .notebook_id
    )
    tp = ThemePersistence(db_path=combined_db)
    theme = tp.create_theme(user_id=USER, title="Round Trip")
    tp.promote_blocks(theme_id=theme.theme_id, source_block_ids=source_ids)
    loaded = tp.load_theme_by_id(theme.theme_id)
    assert loaded is not None

    out = str(tmp_path / "rt.antiek")
    save_theme_as_antiek(loaded, out_path=out)

    re = load_theme_from_antiek(out)
    assert re["content_class"] == "theme_notebook"
    assert re["antiek_format_version"] == 1
    assert re["manifest"]["theme_id"] == theme.theme_id
    assert re["manifest"]["slug"] == "round-trip"
    assert re["manifest"]["source_notebook_ids"] == [source_notebook_id]
    assert len(re["blocks"]) == 2
    # Block ordering preserved.
    assert [b["source_block_id"] for b in re["blocks"]] == source_ids


def test_save_theme_as_antiek_rejects_wrong_content_class(
    tmp_path: Any,
) -> None:
    bad = tmp_path / "bad.antiek"
    bad.write_text(
        json.dumps(
            {
                "antiek_format_version": 1,
                "content_class": "per_doc_notebook",
                "manifest": {},
                "blocks": [],
            }
        )
    )
    with pytest.raises(ValueError, match="content_class"):
        load_theme_from_antiek(str(bad))


# ── List for index page ──


def test_list_themes_sort_orders(
    combined_db: str, persistence: JSONPersistence
) -> None:
    tp = ThemePersistence(db_path=combined_db)
    # Insert in non-alphabetical order so the title_asc sort is
    # observable.
    tp.create_theme(user_id=USER, title="Zeta")
    tp.create_theme(user_id=USER, title="Alpha")
    tp.create_theme(user_id=USER, title="Mu")
    by_title = tp.list_themes(user_id=USER, sort="title_asc")
    assert [t.title for t in by_title] == ["Alpha", "Mu", "Zeta"]

    by_last_edited = tp.list_themes(user_id=USER, sort="last_edited_desc")
    # Most-recently-created is last_edited-most-recent (created_at
    # also stamps last_edited_at on insert).
    assert by_last_edited[0].title == "Mu"


def test_list_themes_unknown_sort_raises(combined_db: str) -> None:
    tp = ThemePersistence(db_path=combined_db)
    with pytest.raises(ValueError, match="unknown sort"):
        tp.list_themes(user_id=USER, sort="random")


def test_get_or_create_theme_idempotent(combined_db: str) -> None:
    tp = ThemePersistence(db_path=combined_db)
    t1 = tp.get_or_create_theme(user_id=USER, title="Same")
    t2 = tp.get_or_create_theme(user_id=USER, title="Same")
    assert t1.theme_id == t2.theme_id


def test_list_themes_for_source_block(
    combined_db: str, persistence: JSONPersistence
) -> None:
    """Reverse lookup powers the "in theme: <title>" indicator on
    the Tier-2 surface (SPR-11 M2 acceptance)."""
    [src_id] = _seed_notebook(
        persistence, document_id="doc-A", block_types=["highlight_card"]
    )
    tp = ThemePersistence(db_path=combined_db)
    t = tp.create_theme(user_id=USER, title="Reverse")
    tp.promote_block(theme_id=t.theme_id, source_block_id=src_id)

    found = tp.list_themes_for_source_block(source_block_id=src_id)
    assert len(found) == 1
    assert found[0].theme_id == t.theme_id


def test_count_theme_blocks_excludes_dismissed(
    combined_db: str, persistence: JSONPersistence
) -> None:
    [src_id] = _seed_notebook(
        persistence, document_id="doc-A", block_types=["highlight_card"]
    )
    tp = ThemePersistence(db_path=combined_db)
    t = tp.create_theme(user_id=USER, title="Count")
    tb = tp.promote_block(theme_id=t.theme_id, source_block_id=src_id)
    assert tp.count_theme_blocks(t.theme_id) == 1
    tp.dismiss_stale(theme_block_id=tb.theme_block_id)
    assert tp.count_theme_blocks(t.theme_id) == 0
