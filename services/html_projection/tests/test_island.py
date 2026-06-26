"""M3: data island + round-trip tests (HPRJ SPR-02).

Round-trip property: extract_island(render(d)) == d, over the golden
corpus AND an adversarial escaping corpus (</template> in strings, nested
templates, unicode, quotes). The extractor rejects unknown schema
versions with a typed error.
"""

from __future__ import annotations

import pytest

from services.html_projection import (
    ISLAND_SCHEMA_VERSION,
    IslandNotFound,
    MalformedIsland,
    Provenance,
    RenderContext,
    UnknownIslandSchemaVersion,
    embed_island,
    extract_island,
    render,
)
from services.html_projection.tests.fixtures.golden import (
    ADVERSARIAL_STRINGS,
    golden_corpus,
)


# ── Round-trip over golden corpus ──


@pytest.mark.parametrize("idx", range(len(golden_corpus())))
def test_roundtrip_golden_corpus(ctx, idx):
    """extract_island(render(d)) == d for every golden doc-model."""
    doc = golden_corpus()[idx]
    html = render(doc, ctx)
    recovered = extract_island(html)
    assert recovered == doc


# ── Round-trip over adversarial escaping edge cases ──


@pytest.mark.parametrize("s", ADVERSARIAL_STRINGS)
def test_roundtrip_adversarial_string_in_text_node(ctx, s):
    """An adversarial string embedded as a text-node value round-trips
    exactly. Covers </template> in strings, nested templates, unicode,
    quotes, control chars, empty strings."""
    doc = {
        "content": [
            {"type": "antiek_prose", "attrs": {"block_id": "x"}},
            {"type": "text", "text": s},
        ]
    }
    html = render(doc, ctx)
    recovered = extract_island(html)
    assert recovered == doc
    # Specifically the adversarial string survived.
    assert recovered["content"][1]["text"] == s


@pytest.mark.parametrize("s", ADVERSARIAL_STRINGS)
def test_roundtrip_adversarial_string_in_attr(ctx, s):
    """An adversarial string in an attribute value round-trips exactly."""
    doc = {
        "content": [
            {
                "type": "antiek_highlight_card",
                "attrs": {"block_id": "x", "passage_text": s},
            }
        ]
    }
    html = render(doc, ctx)
    recovered = extract_island(html)
    assert recovered == doc


def test_roundtrip_template_closing_tag_in_string(ctx):
    """The canonical edge case: a literal </template> inside a string
    must NOT prematurely close the island template."""
    s = "</template>"
    doc = {"content": [{"type": "text", "text": s}]}
    island = embed_island(doc)
    # The island must contain the ESCAPED form, not a raw </template>
    # that would close the template early.
    assert "</template>" not in island.replace(
        "</template>", "", 1
    )  # only the real closing tag
    recovered = extract_island("<html>" + island + "</html>")
    assert recovered == doc


def test_roundtrip_nested_template_looking_substring(ctx):
    """A string that looks like nested template tags round-trips."""
    s = "<template>nested</template><template data-antiek='evil'>x</template>"
    doc = {"content": [{"type": "text", "text": s}]}
    html = render(doc, ctx)
    recovered = extract_island(html)
    assert recovered == doc


def test_island_uses_template_not_script():
    """The island is a <template>, never a <script> (script-free
    invariant). <script type="application/json"> is rejected."""
    doc = {"content": []}
    island = embed_island(doc)
    assert '<template data-antiek="doc-model"' in island
    assert "<script" not in island.lower()


# ── Schema versioning ──


def test_island_carries_schema_version():
    """The island stamps data-schema-version."""
    doc = {"content": []}
    island = embed_island(doc)
    assert 'data-schema-version="1"' in island


def test_island_default_schema_version_is_one():
    assert ISLAND_SCHEMA_VERSION == "1"


def test_extractor_rejects_unknown_schema_version():
    """An island with an unsupported schema version raises the typed
    UnknownIslandSchemaVersion error — never silently mis-parsed."""
    doc = {"content": []}
    island = embed_island(doc, schema_version="99")
    with pytest.raises(UnknownIslandSchemaVersion) as exc_info:
        extract_island("<html>" + island + "</html>")
    assert exc_info.value.version == "99"


def test_extractor_rejects_missing_schema_version():
    """An island with no data-schema-version is refused (a writer must
    stamp one)."""
    island = '<template data-antiek="doc-model">{"content":[]}</template>'
    with pytest.raises(UnknownIslandSchemaVersion):
        extract_island("<html>" + island + "</html>")


def test_typed_error_is_island_error_subclass():
    """UnknownIslandSchemaVersion is a typed error (subclass of
    IslandError) so callers can catch the family."""
    from services.html_projection.island import IslandError

    assert issubclass(UnknownIslandSchemaVersion, IslandError)
    assert issubclass(IslandNotFound, IslandError)
    assert issubclass(MalformedIsland, IslandError)


# ── Extractor error cases ──


def test_extractor_raises_island_not_found_when_absent():
    """HTML with no island raises IslandNotFound."""
    with pytest.raises(IslandNotFound):
        extract_island("<html><body>no island here</body></html>")


def test_extractor_raises_malformed_on_bad_json():
    """Island present but content not JSON → MalformedIsland."""
    island = '<template data-antiek="doc-model" data-schema-version="1">not json</template>'
    with pytest.raises(MalformedIsland):
        extract_island("<html>" + island + "</html>")


def test_extractor_raises_malformed_on_non_object_json():
    """Island content parses to a non-object (array/scalar) → MalformedIsland."""
    island = '<template data-antiek="doc-model" data-schema-version="1">[1,2,3]</template>'
    with pytest.raises(MalformedIsland):
        extract_island("<html>" + island + "</html>")


# ── Island escaping invertibility ──


def test_island_escape_unescape_are_inverse():
    """island_unescape(island_escape(s)) == s for every adversarial
    string. This is the mechanical heart of the round-trip."""
    from services.html_projection.escape import island_escape, island_unescape

    for s in ADVERSARIAL_STRINGS:
        assert island_unescape(island_escape(s)) == s


def test_island_escape_handles_ampersand_first():
    """The critical ordering: & is escaped first so a literal &lt; in the
    source becomes &amp;lt; and round-trips (doesn't get double-decoded)."""
    from services.html_projection.escape import island_escape, island_unescape

    s = "&lt; &gt; &amp;"
    escaped = island_escape(s)
    assert escaped == "&amp;lt; &amp;gt; &amp;amp;"
    assert island_unescape(escaped) == s


# ── Island is inert (not rendered) ──


def test_island_content_does_not_appear_in_visible_surface(ctx):
    """The data-island content is inside <template> (inert) — it should
    not appear as visible text in the reading surface. The adversarial
    </template> string in particular must not leak into visible text."""
    doc = {
        "content": [
            {
                "type": "antiek_prose",
                "attrs": {"block_id": "x"},
                "content": [{"type": "text", "text": "visible prose"}],
            }
        ]
    }
    # Inject an adversarial string into the doc-model that the island
    # carries but the visible surface does not show.
    doc["secret"] = "</template><script>evil</script>"
    html = render(doc, ctx)
    visible = html.split('<template data-antiek="doc-model">')[0]
    assert "</template><script>evil</script>" not in visible
    # And the round-trip preserves the secret.
    assert extract_island(html)["secret"] == "</template><script>evil</script>"
