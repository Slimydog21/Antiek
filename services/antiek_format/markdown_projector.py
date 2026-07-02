"""Markdown projection — universal-fallback shield (SPR-09 / M4).

A `.antiek` file projected to ``.md`` opens in Obsidian, iA Writer,
Cursor, GitHub web preview, and anything else that handles standard
markdown. The projection is **lossy** and **one-way**:

- Block-level affordances (claim cards, AI Q&A panels) flatten to
  quoted prose.
- Voice-note playback is replaced with a link to the extracted audio
  blob (sibling ``blocks/`` directory).
- User-asserted edges become an "Asserted edges" appendix section.
- The signature is NOT projected (markdown has no canonical-bytes
  primitive; signing markdown would be meaningless).

If you find yourself wanting to round-trip markdown ↔ .antiek: STOP.
That's a different feature, an order of magnitude more work, and
documented as out-of-scope in SPEC.md §10. The projection is a fallback
shield for tools without Antiek — not a sync format.
"""

from __future__ import annotations

import os
import sys
from typing import Any

try:
    from .native_reader import ReadResult, read_antiek
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from services.antiek_format.native_reader import (  # type: ignore[no-redef]
        ReadResult,
        read_antiek,
    )


HEADER_COMMENT: str = (
    "<!-- Projected from .antiek (SPR-09 universal-fallback). Lossy: "
    "blocks, voice playback, and signed edges are rendered as best-effort "
    "prose. Round-trip is NOT supported. Open the .antiek in Antiek to "
    "edit. -->"
)


def project_to_markdown(data: bytes) -> str:
    """Convert `.antiek` bytes to a readable markdown string.

    The audio blobs are NOT extracted by this function — that is the
    caller's job (so projection-to-string doesn't have a filesystem
    side effect). See ``project_to_markdown_with_blocks`` for the
    filesystem-side variant the CLI uses.
    """
    result = read_antiek(data)
    return _render_markdown(result, audio_dir=None)


def project_to_markdown_with_blocks(
    data: bytes,
    *,
    output_md_path: str,
) -> str:
    """Project bytes to markdown AND extract audio blobs to a sibling
    ``blocks/`` directory next to ``output_md_path``.

    Returns the markdown string AND writes audio bytes to disk. Used
    by the CLI / save-as-Markdown export menu (M6).
    """
    result = read_antiek(data)
    output_dir = os.path.dirname(os.path.abspath(output_md_path)) or "."
    blocks_dir: str | None = None
    if result.audio_blobs:
        blocks_dir = os.path.join(output_dir, "blocks")
        os.makedirs(blocks_dir, exist_ok=True)
        for block_id, blob in result.audio_blobs.items():
            with open(os.path.join(blocks_dir, f"{block_id}.audio"), "wb") as f:
                f.write(blob)
    return _render_markdown(result, audio_dir="blocks" if blocks_dir else None)


def _render_markdown(result: ReadResult, *, audio_dir: str | None) -> str:
    """Internal renderer. ``audio_dir`` is the relative path (from the
    .md location) where audio blobs live, or None to inline the
    block_id without a working link."""
    out: list[str] = []
    out.append(HEADER_COMMENT)
    out.append("")
    if result.title:
        out.append(f"# {result.title}")
        out.append("")
    out.append(f"_Projected from a `.antiek` file (schema {result.schema_version})._")
    if not result.signature_valid:
        out.append(
            "_**Warning:** signature does not verify. Treat the content as "
            "potentially tampered._"
        )
    out.append("")

    # Walk the TipTap doc top-level nodes. Each is a block (per the
    # antiek_<block_type> node naming convention).
    doc = result.content_tiptap or {}
    nodes = doc.get("content") if isinstance(doc, dict) else None
    if not isinstance(nodes, list):
        nodes = []

    # Index blocks_index by block_id so we can resolve audio paths /
    # demoted state without scanning each time.
    by_id: dict[str, dict] = {}
    for entry in result.blocks_index or []:
        if isinstance(entry, dict) and "block_id" in entry:
            by_id[entry["block_id"]] = entry

    for node in nodes:
        block_md = _render_block(node, by_id, audio_dir=audio_dir)
        if block_md:
            out.append(block_md)
            out.append("")

    if result.edges:
        out.append("---")
        out.append("")
        out.append("## Asserted edges")
        out.append("")
        out.append(
            "_User-asserted links to other content. The substrate may also "
            "infer cross-content edges; those are not exported here — "
            "consult the live graph._"
        )
        out.append("")
        for edge in result.edges:
            kind = edge.get("kind", "references")
            to_doc = edge.get("to_document_id", "?")
            to_hash = edge.get("to_content_hash", "?")
            note = edge.get("operator_note")
            line = f"- **{kind}** → `{to_doc}` (content-hash: `{to_hash[:12]}…`)"
            if note:
                line += f" — {note}"
            out.append(line)
        out.append("")

    return "\n".join(out).rstrip() + "\n"


def _render_block(
    node: Any, by_id: dict[str, dict], *, audio_dir: str | None
) -> str:
    """Render one TipTap block as markdown.

    The block_type drives the rendering. Unknown types fall back to a
    JSON code block — they at least surface; nothing crashes.
    """
    if not isinstance(node, dict):
        return ""
    block_type = node.get("type", "")
    attrs = node.get("attrs", {}) or {}
    block_id = attrs.get("block_id") or ""
    inner = _inline_from_content(node.get("content", []))

    if block_type in ("antiek_highlight_card", "highlight_card"):
        passage = attrs.get("passage_text") or inner or "(empty highlight)"
        framing = attrs.get("operator_framing")
        out = "\n".join(f"> {line}" for line in str(passage).splitlines())
        if framing:
            out += f"\n\n_{framing}_"
        return out

    if block_type in ("antiek_voice_block", "voice_block"):
        duration = attrs.get("duration_seconds") or attrs.get("duration") or 0
        try:
            duration = int(float(duration))
        except (TypeError, ValueError):
            duration = 0
        mins, secs = divmod(duration, 60)
        transcript = attrs.get("transcript") or inner or ""
        audio_entry = by_id.get(block_id, {})
        audio_path = audio_entry.get("audio_path")
        prefix = f"(voice note: {mins}:{secs:02d})"
        if audio_path and audio_dir:
            # Rewrite the in-zip path to the on-disk relative path.
            rel = audio_path
            if rel.startswith("blocks/"):
                rel = os.path.join(audio_dir, rel[len("blocks/"):])
            prefix = f"[{prefix}]({rel})"
        elif audio_path:
            prefix = f"{prefix} (`{audio_path}`)"
        out = prefix
        if transcript:
            out += f"\n\n> {transcript}"
        return out

    if block_type in ("antiek_ai_qa", "ai_qa"):
        question = attrs.get("question") or ""
        answer = attrs.get("answer") or inner or ""
        attribution = attrs.get("attribution") or ""
        out_parts: list[str] = []
        if question:
            out_parts.append(f"**Q:** {question}")
        if answer:
            out_parts.append(f"**A:** {answer}")
        if attribution:
            out_parts.append(f"_Source: {attribution}_")
        return "\n\n".join(out_parts) if out_parts else ""

    if block_type in ("antiek_cite_link", "cite_link"):
        label = attrs.get("label") or inner or "cite"
        target = attrs.get("target_url") or attrs.get("deeplink") or ""
        return f"[{label}]({target})"

    if block_type in ("antiek_cross_doc_jump", "cross_doc_jump"):
        label = attrs.get("label") or inner or "cross-document jump"
        target_doc = attrs.get("target_document_id") or ""
        return f"[{label}][{target_doc}]"

    if block_type in ("antiek_prose", "prose", "paragraph", "doc"):
        # Pass-through for paragraphs / generic prose nodes.
        return inner

    # Unknown block type — render as a fenced code block of the raw
    # JSON so the reader can at least see what was there.
    import json
    return "```json\n" + json.dumps(node, indent=2, sort_keys=True) + "\n```"


def _inline_from_content(content: Any) -> str:
    """Flatten a TipTap content array to a markdown string. Handles
    text nodes + a couple of common inline mark types (bold, italic,
    link). Unknown marks pass through their text without decoration."""
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for node in content:
        if not isinstance(node, dict):
            continue
        if node.get("type") == "text":
            text = node.get("text", "") or ""
            marks = node.get("marks") or []
            for mark in marks:
                mt = mark.get("type") if isinstance(mark, dict) else ""
                if mt == "bold":
                    text = f"**{text}**"
                elif mt == "italic":
                    text = f"_{text}_"
                elif mt == "code":
                    text = f"`{text}`"
                elif mt == "link" and isinstance(mark.get("attrs"), dict):
                    href = mark["attrs"].get("href", "")
                    text = f"[{text}]({href})"
            parts.append(text)
        elif isinstance(node.get("content"), list):
            parts.append(_inline_from_content(node["content"]))
    return "".join(parts)


__all__ = [
    "HEADER_COMMENT",
    "project_to_markdown",
    "project_to_markdown_with_blocks",
]
