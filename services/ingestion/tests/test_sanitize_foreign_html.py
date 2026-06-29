"""SPR-07 M3: foreign-HTML sanitizer — the hostile corpus.

Each vector is proven failing-before (the raw foreign HTML carries a
detectable vector) / passing-after (the sanitizer quarantines it, never passes
it through). Clean HTML — even prose that mentions vector keywords — passes.
"""

from __future__ import annotations

import pytest

from services.ingestion.sanitize_foreign_html import (
    find_foreign_violations,
    sanitize_foreign_html,
)

# One fixture per attack bucket (D9-style). Includes the buckets the SPR-02
# gate already covers AND the foreign-only buckets this sanitizer adds.
HOSTILE_CORPUS = {
    "script_tag": "<p>ok</p><script>steal()</script>",
    "script_upcase": "<SCRIPT>steal()</SCRIPT>",
    "event_handler": "<div onclick='steal()'>x</div>",
    "javascript_uri": "<a href='javascript:steal()'>x</a>",
    "javascript_uri_obfuscated": "<a href='java\tscript:steal()'>x</a>",
    "external_img": "<img src='http://evil.example/beacon.gif'>",
    "external_iframe": "<iframe src='https://evil.example'></iframe>",
    "css_remote_url": "<style>body{background:url(http://evil.example/x)}</style>",
    "meta_refresh": "<meta http-equiv='refresh' content='0;url=http://evil.example'>",
    # foreign-only buckets the gate does not target:
    "data_uri_html": "<a href='data:text/html,<script>steal()</script>'>x</a>",
    "data_uri_svg": "<img src='data:image/svg+xml,<svg onload=steal()>'>",
    "svg_foreign_object": "<svg><foreignObject><b onmouseover='steal()'>x</b></foreignObject></svg>",
    "iframe_srcdoc": "<iframe srcdoc='&lt;script&gt;steal()&lt;/script&gt;'></iframe>",
    "spoofed_antiek_marker": '<template data-antiek="doc-model">{"content":[]}</template>',
}


@pytest.mark.parametrize("name,html", sorted(HOSTILE_CORPUS.items()))
def test_hostile_corpus_failing_before_passing_after(name, html):
    # failing-before: the vector is detectable in the raw foreign HTML.
    detected = find_foreign_violations(html)
    assert detected, f"{name}: corpus fixture carries no detectable vector"
    # passing-after: the sanitizer quarantines it — it never passes through.
    result = sanitize_foreign_html(html)
    assert result.quarantined and not result.safe
    assert result.reason and "vectors" in result.reason


def test_clean_foreign_html_passes_including_vector_keyword_prose():
    # Prose that MENTIONS vectors (no actual scheme/marker/tag) must pass —
    # the gate's checks are tag/attribute-scoped, not substring panic.
    clean = (
        "<h1>On script injection</h1>"
        "<p>This article discusses the javascript scheme and data uris as "
        "prose. It mentions onerror and foreignObject by name. None are live.</p>"
        "<p>A relative <a href='/local/page'>link</a> is fine.</p>"
    )
    result = sanitize_foreign_html(clean)
    assert result.safe and not result.quarantined
    assert result.violations == []


def test_inert_data_image_is_not_quarantined():
    # A plain raster data: image is inert (never executed by ingest); it must
    # NOT trip the data-payload bucket (which targets html/svg/application).
    result = sanitize_foreign_html("<img src='data:image/png;base64,iVBORw0KGgo='>")
    assert result.safe and not result.quarantined
