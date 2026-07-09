"""Real-path tests: arxiv/substack reference attach on deep-research spawn.

Pure parse + store attach — no live HTTP. Residual after twin-promote (o).
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.engagement_spine import (  # noqa: E402
    HighlightSelection,
    InMemoryEngagementStore,
    attach_source_references,
    detect_source_kind,
    extract_arxiv_id,
    filter_references,
    get_spawn,
    list_source_references,
    parse_source_reference,
    parse_source_references,
    source_references_html,
    spawn_from_highlight,
    spawn_from_highlight_with_references,
)


@pytest.fixture
def store():
    return InMemoryEngagementStore()


def test_extract_arxiv_id_variants():
    assert extract_arxiv_id("https://arxiv.org/abs/2402.03300") == "2402.03300"
    assert extract_arxiv_id("https://arxiv.org/pdf/2402.03300v2") == "2402.03300"
    assert extract_arxiv_id("2402.03300v3") == "2402.03300"
    assert extract_arxiv_id("https://example.com/post") is None


def test_detect_source_kind():
    assert detect_source_kind("https://arxiv.org/abs/2402.03300") == "arxiv"
    assert detect_source_kind("2402.03300") == "arxiv"
    assert detect_source_kind("https://foo.substack.com/p/hello-world") == "substack"
    assert detect_source_kind("https://example.com/essay") == "url"
    assert detect_source_kind("arxiv:1706.03762") == "arxiv"


def test_parse_arxiv_and_substack_stable_ids():
    a1 = parse_source_reference("https://arxiv.org/abs/1706.03762v5")
    a2 = parse_source_reference("1706.03762")
    assert a1.kind == "arxiv"
    assert a1.external_id == "1706.03762"
    assert a1.canonical_url == "https://arxiv.org/abs/1706.03762"
    assert a1.ref_id == a2.ref_id  # version-stripped identity

    s = parse_source_reference("https://foo.substack.com/p/my-post")
    assert s.kind == "substack"
    assert s.external_id == "foo.substack.com/p/my-post"
    assert s.canonical_url == "https://foo.substack.com/p/my-post"
    assert s.ref_id.startswith("sref_")


def test_parse_references_dedupes():
    refs = parse_source_references(
        [
            "https://arxiv.org/abs/2402.03300",
            "2402.03300v1",
            "https://bar.substack.com/p/notes",
        ]
    )
    assert len(refs) == 2
    kinds = {r.kind for r in refs}
    assert kinds == {"arxiv", "substack"}


def test_attach_to_spawn_idempotent(store):
    spawn = spawn_from_highlight(
        HighlightSelection(
            asset_id="paper-1",
            selection_text="Attention is all you need.",
            region_id="r1",
        ),
        store=store,
    )
    spawn2, merged = attach_source_references(
        spawn.spawn_id,
        [
            "https://arxiv.org/abs/1706.03762",
            "https://research.substack.com/p/transformers",
        ],
        store=store,
    )
    assert spawn2.spawn_id == spawn.spawn_id
    assert len(merged) == 2
    assert len(spawn2.source_references) == 2

    # Re-attach same refs → stable, no dup
    spawn3, merged2 = attach_source_references(
        spawn.spawn_id,
        ["1706.03762", "https://research.substack.com/p/transformers"],
        store=store,
    )
    assert len(merged2) == 2
    assert {r["ref_id"] for r in spawn3.source_references} == {
        r["ref_id"] for r in spawn2.source_references
    }

    listed = list_source_references(spawn.spawn_id, store=store)
    assert len(listed) == 2
    arxiv = [r for r in listed if r.kind == "arxiv"][0]
    assert arxiv.external_id == "1706.03762"


def test_spawn_from_highlight_with_references_product(store):
    spawn = spawn_from_highlight_with_references(
        HighlightSelection(
            asset_id="asset-dr",
            selection_text="Deep residual learning for image recognition.",
            region_id="res-1",
            goal_hint="Cite arxiv + substack on residual nets",
        ),
        store=store,
        references=[
            "https://arxiv.org/abs/1512.03385",
            "https://lilianweng.substack.com/p/residual",
        ],
        model_id="glm-5.2",
    )
    assert spawn.model_id == "glm-5.2"
    assert len(spawn.source_references) == 2
    again = get_spawn(spawn.spawn_id, store=store)
    assert again is not None
    assert len(again.source_references) == 2


def test_double_run_attach_stable(store):
    sel = HighlightSelection(
        asset_id="a",
        selection_text="passage",
        region_id="reg-stable",
    )
    refs = ["arxiv:2401.00001", "https://x.substack.com/p/y"]
    s1 = spawn_from_highlight_with_references(sel, store=store, references=refs)
    s2 = spawn_from_highlight_with_references(sel, store=store, references=refs)
    assert s1.spawn_id == s2.spawn_id
    ids1 = sorted(r["ref_id"] for r in s1.source_references)
    ids2 = sorted(r["ref_id"] for r in s2.source_references)
    assert ids1 == ids2
    assert len(ids1) == 2


def test_filter_references_and_html(store):
    spawn = spawn_from_highlight_with_references(
        HighlightSelection(asset_id="z", selection_text="q", region_id="z1"),
        store=store,
        references=[
            "https://arxiv.org/abs/2301.00001",
            "https://news.substack.com/p/weekly",
            "https://example.com/other",
        ],
    )
    refs = list_source_references(spawn.spawn_id, store=store)
    only_arxiv = filter_references(refs, kind="arxiv")
    assert len(only_arxiv) == 1
    hit = filter_references(refs, query="substack")
    assert len(hit) == 1
    html = source_references_html(refs)
    assert html.strip()
    assert "2301.00001" in html or "arxiv" in html.lower()
    assert "application/pdf" not in html.lower()


def test_attach_unknown_spawn_raises(store):
    with pytest.raises(KeyError):
        attach_source_references("spn_missing", ["2402.03300"], store=store)


def test_parse_rejects_empty():
    with pytest.raises(ValueError):
        parse_source_reference("   ")
