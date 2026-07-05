"""SPR-01 — Notebook non-destructive persistence + substrate hydration.

The active data-loss bug (confirmed on main): a fresh browser opens an
existing notebook, the editor seeds a near-empty doc (``<p></p>``) because
it hydrates only from ``localStorage``, and the 1.5 s autosave PUTs that
near-empty doc. ``PUT /notebooks/{id}/content`` does
``DELETE FROM notebook_blocks`` then re-inserts the decomposed doc — so the
persisted blocks are destroyed.

M1 (this file's keystone) reproduces the loss as a RED test *before* any
fix: seed N>0 real blocks, fire the fresh-browser PUT, assert the blocks
SURVIVE. It fails on pre-fix code (blocks wiped) and passes once the guard
lands. The remaining tests prove the guard doesn't break a legitimate
full-doc replace (M3), and that the hydration GET (M4) composes a TipTap
doc that round-trips with decompose.
"""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app


@pytest.fixture()
def isolated_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-nb-guard-")
    db_path = os.path.join(tmpdir, "antiek.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    try:
        from substrate.graph import ensure_initialized

        ensure_initialized(db_path)
        yield db_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _client() -> TestClient:
    return TestClient(create_app(register_wrestling=False))


# The exact doc a fresh/unhydrated editor emits: TipTap seeds ``<p></p>``
# when localStorage is empty, whose getJSON() is a single empty paragraph.
FRESH_EDITOR_EMPTY_DOC = {"type": "doc", "content": [{"type": "paragraph"}]}


def _seed_notebook_with_blocks(client: TestClient, n: int) -> tuple[str, list[str]]:
    """Seed a notebook with ``n`` real prose blocks via the same path the
    app uses (POST /notebooks/{id}/blocks). Returns (notebook_id, texts)."""
    nb_id = client.post(
        "/notebooks", json={"title": "operator notes", "investigation_id": "inv-1"}
    ).json()["notebook_id"]
    texts = [f"Persisted paragraph {i} — real operator content." for i in range(n)]
    for text in texts:
        r = client.post(
            f"/notebooks/{nb_id}/blocks",
            json={
                "block_type": "prose",
                "content": {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": text}],
                },
            },
        )
        assert r.status_code == 201, r.text
    return nb_id, texts


def _block_texts(blocks: list[dict]) -> list[str]:
    out: list[str] = []
    for b in blocks:
        cj = b.get("content_json") or {}
        for child in cj.get("content") or []:
            if child.get("type") == "text":
                out.append(child.get("text", ""))
    return out


# ── Guard predicate (pure, no app boot) ────────────────────────────────


@pytest.mark.parametrize(
    "doc,expected_empty",
    [
        ({"type": "doc", "content": [{"type": "paragraph"}]}, True),
        ({"type": "doc", "content": []}, True),
        ({"type": "doc"}, True),
        ({"type": "doc", "content": [{"type": "paragraph"}, {"type": "paragraph"}]}, True),
        (
            {"type": "doc", "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": " \n\t"}]}]},
            True,
        ),
        (
            {"type": "doc", "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "real"}]}]},
            False,
        ),
        (
            {"type": "doc", "content": [
                {"type": "heading", "content": [{"type": "text", "text": "H"}]}]},
            False,
        ),
        # A substrate-citation block with no text is still real content.
        ({"type": "doc", "content": [{"type": "claim_card", "attrs": {"claim_id": "c1"}}]}, False),
    ],
)
def test_is_effectively_empty(doc, expected_empty):
    from substrate.notebooks.tiptap_codec import is_effectively_empty

    assert is_effectively_empty(doc) is expected_empty


# ── M1: reproduce the loss (RED on pre-fix code) ───────────────────────


def test_fresh_browser_autosave_does_not_destroy_persisted_blocks(isolated_db):
    """M1 keystone — the reproduced data-loss.

    Seed 5 real blocks, then fire the near-empty doc a fresh/unhydrated
    editor's first autosave sends. The 5 persisted blocks MUST survive.

    On pre-fix main this FAILS: the PUT DELETEs all 5 blocks and inserts
    one empty paragraph → the operator's notes are destroyed.
    """
    client = _client()
    nb_id, texts = _seed_notebook_with_blocks(client, 5)

    before = client.get(f"/notebooks/{nb_id}").json()["blocks"]
    assert len(before) == 5
    assert _block_texts(before) == texts

    # The fresh browser's first autosave: a near-empty doc.
    resp = client.put(
        f"/notebooks/{nb_id}/content", json={"doc": FRESH_EDITOR_EMPTY_DOC}
    )

    after = client.get(f"/notebooks/{nb_id}").json()["blocks"]
    # The load-bearing data-loss assertion: block count before vs after.
    assert len(after) == 5, (
        f"DATA LOSS: 5 persisted blocks → {len(after)} after a fresh-browser "
        f"empty-doc autosave (PUT status {resp.status_code})"
    )
    # And the actual content — not just the count — survives.
    assert _block_texts(after) == texts
    # The empty-doc PUT is rejected, not silently accepted.
    assert resp.status_code == 409, resp.text


@pytest.mark.parametrize(
    "empty_doc",
    [
        pytest.param({"type": "doc", "content": [{"type": "paragraph"}]}, id="bare-paragraph"),
        pytest.param({"type": "doc", "content": []}, id="no-content"),
        pytest.param({"type": "doc"}, id="missing-content-key"),
        pytest.param(
            {
                "type": "doc",
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": "   \n\t "}]}
                ],
            },
            id="whitespace-only",
        ),
        pytest.param(
            {
                "type": "doc",
                "content": [{"type": "paragraph"}, {"type": "paragraph"}],
            },
            id="multiple-empty-paragraphs",
        ),
    ],
)
def test_guard_rejects_every_empty_shape_over_persisted_blocks(isolated_db, empty_doc):
    """The loss-hunter lens: every 'looks empty' client doc a buggy/fresh
    editor could send is refused when the notebook has persisted blocks."""
    client = _client()
    nb_id, texts = _seed_notebook_with_blocks(client, 3)
    resp = client.put(f"/notebooks/{nb_id}/content", json={"doc": empty_doc})
    assert resp.status_code == 409, resp.text
    body = resp.json()["detail"]
    assert body["code"] == "empty_doc_would_destroy_blocks"
    assert body["existing_block_count"] == 3
    # Blocks fully intact.
    after = client.get(f"/notebooks/{nb_id}").json()["blocks"]
    assert _block_texts(after) == texts


def test_empty_doc_into_empty_notebook_is_allowed(isolated_db):
    """The floor only protects *persisted* blocks. An empty doc into a
    notebook with zero blocks is a legal no-op replace (nothing to lose)."""
    client = _client()
    nb_id = client.post(
        "/notebooks", json={"title": "blank", "investigation_id": "inv-1"}
    ).json()["notebook_id"]
    resp = client.put(
        f"/notebooks/{nb_id}/content", json={"doc": FRESH_EDITOR_EMPTY_DOC}
    )
    assert resp.status_code == 200, resp.text


# ── M3: the legitimate full-doc replace must still work (rigor #2) ──────


def test_legitimate_full_doc_replace_still_works(isolated_db):
    """Steelman the atomic-replace design: a client sending a complete doc
    with different, real blocks (N→M, both >0) must replace normally — the
    guard is not allowed to block the case the original design served."""
    client = _client()
    nb_id, _ = _seed_notebook_with_blocks(client, 5)  # N = 5

    # A real full-doc replace to M = 2 different real blocks.
    new_doc = {
        "type": "doc",
        "content": [
            {"type": "heading", "attrs": {"level": 2},
             "content": [{"type": "text", "text": "Rewritten section"}]},
            {"type": "paragraph",
             "content": [{"type": "text", "text": "Entirely new prose."}]},
        ],
    }
    resp = client.put(f"/notebooks/{nb_id}/content", json={"doc": new_doc})
    assert resp.status_code == 200, resp.text

    after = client.get(f"/notebooks/{nb_id}").json()["blocks"]
    assert len(after) == 2
    # Old content gone, new content present — this IS a replace, by design.
    assert _block_texts(after) == ["Rewritten section", "Entirely new prose."]


def test_replace_with_single_real_block_works(isolated_db):
    """Edge of the floor: replacing many blocks with exactly one *real*
    block is allowed — 'real' is about content, not count."""
    client = _client()
    nb_id, _ = _seed_notebook_with_blocks(client, 4)
    one_real = {
        "type": "doc",
        "content": [
            {"type": "paragraph",
             "content": [{"type": "text", "text": "The one surviving idea."}]}
        ],
    }
    resp = client.put(f"/notebooks/{nb_id}/content", json={"doc": one_real})
    assert resp.status_code == 200, resp.text
    after = client.get(f"/notebooks/{nb_id}").json()["blocks"]
    assert _block_texts(after) == ["The one surviving idea."]


# ── M4: hydration GET + compose∘decompose round-trip ───────────────────


# A doc spanning the block-type space the round-trip-corruption lens
# targets: prose, heading, code, nested lists, and a substrate-citation
# block (claim_card) carrying attrs.
RICH_DOC = {
    "type": "doc",
    "content": [
        {"type": "heading", "attrs": {"level": 1},
         "content": [{"type": "text", "text": "Title"}]},
        {"type": "paragraph",
         "content": [{"type": "text", "text": "Some prose with "},
                     {"type": "text", "marks": [{"type": "bold"}], "text": "bold"},
                     {"type": "text", "text": "."}]},
        {"type": "codeBlock", "attrs": {"language": "python"},
         "content": [{"type": "text", "text": "print('hi')"}]},
        {"type": "bulletList", "content": [
            {"type": "listItem", "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "a"}]},
                {"type": "bulletList", "content": [
                    {"type": "listItem", "content": [
                        {"type": "paragraph",
                         "content": [{"type": "text", "text": "nested"}]}]}]}]}]},
        {"type": "claim_card", "attrs": {"claim_id": "claim-42"},
         "content": [{"type": "text", "text": "A cited claim."}]},
    ],
}


def test_compose_decompose_round_trip_preserves_content():
    """compose(decompose(doc)) is content-equivalent to doc across block
    types (rigor #4: use the built codec; don't reinvent a composer)."""
    from substrate.notebooks.tiptap_codec import compose, decompose

    decomposed = decompose(RICH_DOC)
    recomposed = compose(
        [{"content_json": b.content_json} for b in decomposed]
    )
    assert recomposed == RICH_DOC


def test_hydration_get_returns_composed_doc(isolated_db):
    """M4: GET /notebooks/{id}/content composes the persisted rows back into
    a TipTap doc. Written via PUT (decompose) → read via GET (compose) must
    round-trip the content."""
    client = _client()
    nb_id = client.post(
        "/notebooks", json={"title": "rich", "investigation_id": "inv-1"}
    ).json()["notebook_id"]
    # Persist the rich doc through the real PUT path (decompose).
    put = client.put(f"/notebooks/{nb_id}/content", json={"doc": RICH_DOC})
    assert put.status_code == 200, put.text

    # Hydrate through the new GET (compose).
    got = client.get(f"/notebooks/{nb_id}/content")
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["notebook_id"] == nb_id
    assert body["doc"] == RICH_DOC


def test_hydration_get_missing_notebook_is_404(isolated_db):
    """Access gating matches GET /notebooks/{id}: 404 for a missing notebook."""
    client = _client()
    assert client.get("/notebooks/does-not-exist/content").status_code == 404


def test_hydration_get_empty_notebook_returns_empty_doc(isolated_db):
    """A notebook with no blocks hydrates to an empty (but valid) doc."""
    client = _client()
    nb_id = client.post(
        "/notebooks", json={"title": "blank", "investigation_id": "inv-1"}
    ).json()["notebook_id"]
    got = client.get(f"/notebooks/{nb_id}/content")
    assert got.status_code == 200, got.text
    assert got.json()["doc"] == {"type": "doc", "content": []}
