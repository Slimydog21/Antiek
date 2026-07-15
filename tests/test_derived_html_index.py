from __future__ import annotations

import pytest

from substrate.research_artifact.derived_html_index import (
    DerivedHtmlIndexError,
    chunk_canonical_html,
    chunks_for_policy,
    index_sha256,
    revision_chunk_id,
)


def canonical(body: str) -> str:
    return (
        '<article data-antiek-canonical-policy="antiek-derived-asset-merge" '
        'data-antiek-canonical-version="1"><section data-member-index="0">'
        + body + "</section></article>"
    )


def test_semantic_sections_are_deterministic_and_preserve_order() -> None:
    html = canonical(
        '<section><h1 id="aircraft">Aircraft</h1><p>Lift and drag.</p>'
        '<h2 id="engines">Engines &amp; thrust</h2><ul><li>Turbofan</li>'
        '<li><p>Turbojet</p></li></ul><table><tr><th>Type</th><td>High bypass</td>'
        '</tr></table></section>'
    )
    one = chunk_canonical_html(html)
    two = chunk_canonical_html(html)
    assert one == two
    assert [chunk.section_anchor for chunk in one] == ["aircraft", "engines"]
    assert [chunk.member_index for chunk in one] == [0, 0]
    assert one[0].section_path == "Aircraft"
    assert one[0].text == "Aircraft\n\nLift and drag."
    assert one[1].section_path == "Aircraft > Engines & thrust"
    assert one[1].text == "Engines & thrust\n\nTurbofan\n\nTurbojet\n\nType\n\nHigh bypass"
    assert index_sha256(one) == index_sha256(two)


def test_duplicate_unanchored_headings_receive_distinct_stable_anchors() -> None:
    chunks = chunk_canonical_html(canonical(
        "<h2>Repeated</h2><p>One</p><h2>Repeated</h2><p>Two</p>"
    ))
    assert len(chunks) == 2
    assert chunks[0].section_anchor != chunks[1].section_anchor
    assert chunks == chunk_canonical_html(canonical(
        "<h2>Repeated</h2><p>One</p><h2>Repeated</h2><p>Two</p>"
    ))


def test_oversized_block_splits_at_fixed_word_windows() -> None:
    chunks = chunk_canonical_html(canonical("<p>" + " ".join(["word"] * 1201) + "</p>"))
    assert [chunk.token_count for chunk in chunks] == [600, 600, 1]
    assert [chunk.ordinal for chunk in chunks] == [0, 1, 2]


def test_chunks_never_pack_across_member_boundaries() -> None:
    html = (
        '<article data-antiek-canonical-policy="antiek-derived-asset-merge" '
        'data-antiek-canonical-version="1"><section data-member-index="0"><p>First</p>'
        '</section><section data-member-index="1"><p>Second</p></section></article>'
    )
    chunks = chunk_canonical_html(html)
    assert [(chunk.member_index, chunk.text) for chunk in chunks] == [(0, "First"), (1, "Second")]


def test_indexes_inline_only_container_text() -> None:
    chunks = chunk_canonical_html(canonical("<div>Bare <span>inline</span> text</div>"))
    assert [chunk.text for chunk in chunks] == ["Bare inline text"]


def test_indexes_standalone_inline_after_heading_without_paragraph_duplication() -> None:
    chunks = chunk_canonical_html(canonical(
        '<h1 id="top">Ready</h1><a href="#top">up</a><p>Go <strong>now</strong></p>'
    ))
    assert [chunk.text for chunk in chunks] == ["Ready\n\nup\n\nGo now"]


def test_preserves_direct_text_around_nested_semantic_blocks() -> None:
    chunks = chunk_canonical_html(canonical(
        "leading<p>inside</p><div>before<p>nested</p>after</div>trailing"
    ))
    assert [chunk.text for chunk in chunks] == [
        "leading\n\ninside\n\nbefore\n\nnested\n\nafter\n\ntrailing"
    ]


def test_rejects_tag_outside_canonical_vocabulary() -> None:
    with pytest.raises(DerivedHtmlIndexError, match="element is forbidden"):
        chunk_canonical_html(canonical("<script>unsafe</script>"))


def test_chunk_identity_is_revision_scoped_even_for_identical_text() -> None:
    chunk = chunk_canonical_html(canonical("<p>Same text</p>"))[0]
    first = revision_chunk_id(
        asset_id="ast_" + "a" * 32,
        revision_id="rev_" + "b" * 32,
        content_sha256="c" * 64,
        chunker_policy="antiek-derived-html-sections",
        chunker_version="1",
        chunk=chunk,
    )
    second = revision_chunk_id(
        asset_id="ast_" + "a" * 32,
        revision_id="rev_" + "d" * 32,
        content_sha256="c" * 64,
        chunker_policy="antiek-derived-html-sections",
        chunker_version="1",
        chunk=chunk,
    )
    assert first != second
    assert first.startswith("dchunk_") and len(first) == 71
    assert first != revision_chunk_id(
        asset_id="ast_" + "a" * 32,
        revision_id="rev_" + "b" * 32,
        content_sha256="c" * 64,
        chunker_policy="antiek-derived-html-sections",
        chunker_version="2",
        chunk=chunk,
    )


@pytest.mark.parametrize("html", [
    "", "<p>missing wrapper</p>",
    '<article data-antiek-canonical-policy="wrong" '
    'data-antiek-canonical-version="1"><p>x</p></article>',
    canonical("<p>unclosed"),
])
def test_invalid_or_empty_canonical_html_fails_closed(html: str) -> None:
    with pytest.raises(DerivedHtmlIndexError):
        chunk_canonical_html(html)


def test_textless_canonical_revision_has_complete_empty_projection() -> None:
    assert chunk_canonical_html(canonical("<hr>")) == ()
    assert len(index_sha256(())) == 64
    assert chunks_for_policy("antiek-derived-html-sections", "1", canonical("<hr>")) == ()
    with pytest.raises(DerivedHtmlIndexError, match="unsupported"):
        chunks_for_policy("antiek-derived-html-sections", "2", canonical("<hr>"))
