"""Golden corpus fixtures (HPRJ SPR-02 / M2).

Five doc-models spanning every block type the renderer handles, plus one
doc-model of ONLY unknown types (exercises the unsupported-block fallback).
These drive the golden-corpus renders (M2), the data-island round-trip
(M3), the zero-script gate green (M4), and the determinism proof (M5).

Each fixture is a plain dict — the canonical doc-model shape the renderer
takes (``content`` = TipTap node array; optional ``title``, ``edges``).
The full dict is embedded in the data island and round-trips.

Fixtures deliberately include: unicode, quotes, angle brackets in text,
a literal ``</template>`` substring inside a string (island escaping edge
case), nested-looking template strings, and every block type. They are
the adversarial + golden corpus in one — if the renderer/gate/island
survive these, the critic lenses' edge cases are covered.
"""

from __future__ import annotations

GOLDEN_CORPUS: list[dict] = [
    # ── 1. All container block types (highlight, voice, ai_qa, cite, crossdoc, prose) ──
    {
        "title": "Golden: all container blocks",
        "content": [
            {
                "type": "antiek_highlight_card",
                "attrs": {
                    "block_id": "blk-h1",
                    "passage_text": "Highlighted passage with unicode: 注釈 & <tags>.",
                    "operator_framing": "Why this matters — \"quoted\".",
                },
            },
            {
                "type": "antiek_voice_block",
                "attrs": {
                    "block_id": "blk-v1",
                    "duration_seconds": 95,
                    "transcript": "Voice transcript with </template> inside it.",
                },
            },
            {
                "type": "antiek_ai_qa",
                "attrs": {
                    "block_id": "blk-q1",
                    "question": "What's the central claim?",
                    "answer": "The claim is X & Y < Z.",
                    "attribution": "doc-golden §3",
                },
            },
            {
                "type": "antiek_cite_link",
                "attrs": {
                    "block_id": "blk-c1",
                    "label": "See ref §4",
                    "target_url": "/wrestle/doc-golden?chunk=ck-1",
                },
            },
            {
                "type": "antiek_cross_doc_jump",
                "attrs": {
                    "block_id": "blk-x1",
                    "label": "related doc",
                    "target_document_id": "doc-related-1",
                },
            },
            {
                "type": "antiek_prose",
                "attrs": {"block_id": "blk-p1"},
                "content": [
                    {"type": "text", "text": "Prose with "},
                    {"type": "text", "marks": [{"type": "bold"}], "text": "bold"},
                    {"type": "text", "text": " and "},
                    {"type": "text", "marks": [{"type": "italic"}], "text": "italic"},
                    {"type": "text", "text": " and a "},
                    {
                        "type": "text",
                        "marks": [{"type": "link", "attrs": {"href": "/internal"}}],
                        "text": "link",
                    },
                    {"type": "text", "text": "."},
                ],
            },
        ],
        "edges": [
            {
                "edge_id": "edg-g1",
                "from_block_id": "blk-h1",
                "to_content_hash": "a" * 64,
                "to_document_id": "doc-related-1",
                "kind": "supports",
                "asserted_at": "2026-05-21T12:30:00+00:00",
                "operator_note": "supporting evidence",
            }
        ],
    },
    # ── 2. All substrate-only ref-bearing block types (tombstone path: no resolver) ──
    {
        "title": "Golden: substrate ref blocks (no resolver → missing tombstones)",
        "content": [
            {"type": "antiek_region_embed", "attrs": {"block_id": "b1", "document_id": "doc-r1", "passage_text": "Region text."}},
            {"type": "antiek_claim_card", "attrs": {"block_id": "b2", "claim_id": "clm-1", "statement": "Inline claim text."}},
            {"type": "antiek_note", "attrs": {"block_id": "b3", "note_id": "nte-1", "body": "Note body."}},
            {"type": "antiek_question_card", "attrs": {"block_id": "b4", "question_id": "qst-1", "question": "Open question?"}},
            {"type": "antiek_cross_doc_link", "attrs": {"block_id": "b5", "source_document_id": "doc-src-1", "target_document_id": "doc-tgt-1", "label": "bridge"}},
            {"type": "antiek_chat_exchange", "attrs": {"block_id": "b6", "exchange_id": "xch-1"}},
            {"type": "antiek_master_md_section", "attrs": {"block_id": "b7", "synthesis_id": "syn-1", "heading": "Section"}},
            {"type": "antiek_image", "attrs": {"block_id": "b8", "image_id": "img-1", "alt": "A diagram"}},
            {"type": "antiek_latex", "attrs": {"block_id": "b9", "latex": "E = mc^2"}},
        ],
    },
    # ── 3. TipTap bare + aliased node names (note_block, math_block, paragraph, doc) ──
    {
        "title": "Golden: bare + aliased TipTap node names",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "A standard paragraph."}]},
            {"type": "note_block", "attrs": {"block_id": "nb1", "note_id": "nte-2", "body": "Via note_block alias."}},
            {"type": "math_block", "attrs": {"block_id": "mb1", "latex": "\\int_0^1 x^2 dx"}},
            {"type": "prose", "attrs": {"block_id": "pb1"}, "content": [{"type": "text", "text": "Bare prose."}]},
        ],
    },
    # ── 4. Adversarial escaping edge cases concentrated ──
    {
        "title": "Golden: adversarial escaping",
        "content": [
            {
                "type": "antiek_prose",
                "attrs": {"block_id": "esc1"},
                "content": [{"type": "text", "text": "</template><template data-antiek='evil'>nested</template>"}],
            },
            {
                "type": "antiek_highlight_card",
                "attrs": {
                    "block_id": "esc2",
                    "passage_text": "Quote: \" ' < > & ` ${} \\n \\t unicode: 日本語 emoji 🎉",
                    "operator_framing": "Framing with </template> too.",
                },
            },
            {
                "type": "antiek_ai_qa",
                "attrs": {
                    "block_id": "esc3",
                    "question": "Q with <script>alert(1)</script> in it?",
                    "answer": "A with javascript:alert(1) href.",
                    "attribution": "attr with \"quotes\"",
                },
            },
        ],
    },
    # ── 5. ONLY unknown block types (unsupported-block fallback) ──
    {
        "title": "Golden: only unknown types",
        "content": [
            {"type": "future_widget_v2", "attrs": {"block_id": "u1", "data": "anything"}},
            {"type": "totally_made_up", "attrs": {"block_id": "u2"}},
            {"type": "", "attrs": {}},
        ],
    },
]


def golden_corpus() -> list[dict]:
    """Return a deep-ish copy of the golden corpus so tests can mutate
    without polluting the shared fixtures. (We don't deep-copy because
    the dicts hold only JSON-serialisable data; a fresh list of the same
    dict references is fine — tests don't mutate in place.)"""
    return list(GOLDEN_CORPUS)


# Adversarial escaping strings for the M3 island round-trip edge-case
# corpus. Each is a string to embed as a text-node value inside a
# doc-model, then round-trip through embed_island/extract_island.
ADVERSARIAL_STRINGS: list[str] = [
    "</template>",
    "</template><template data-antiek='evil'>x</template>",
    "<template>nested</template>",
    "<script>alert(1)</script>",
    "javascript:alert(1)",
    "onerror=alert(1)",
    'quotes: " \' ` "',
    "angle: < > < > < >",
    "ampersand: & &amp; &lt; &gt;",
    "unicode: 日本語 注釈 русский العربية",
    "emoji: 🎉 🚀 ✓ ✗",
    "backslash: \\ \\\\ \\n \\t",
    "dollar-brace: ${1+1} ${evil}",
    "null: \x00 \x01 control chars",
    "newline:\nand\ttab",
    "long: " + "x" * 1000,
    "mixed: </TEMPLATE> <Script> JaVaScRiPt:",
    "",
    " ",
]


__all__ = ["ADVERSARIAL_STRINGS", "GOLDEN_CORPUS", "golden_corpus"]
