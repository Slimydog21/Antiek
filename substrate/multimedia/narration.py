"""Narration script normalization (multimedia SPR-04, milestone 1).

Convert a planner's cited :class:`~substrate.multimedia.planner.MultimediaPlan`
script lines into speech-ready narration text WITHOUT severing source alignment.

The grounding invariant from the planner (every factual ``ScriptLine`` carries
citations, and unsourced factual lines are explicitly enumerated) is preserved
verbatim here: a :class:`NarrationParagraph` keeps the originating ``line_id``
and the citation ``chunk_ids`` so a downstream player can surface source cards
for every spoken paragraph. Normalization only touches the *spoken surface*:

* abbreviation expansion (e.g. ``"e.g."`` -> ``"for example"``) so a TTS engine
  never reads initializer letters aloud;
* pronunciation-note passthrough (operator-supplied ``pronunciation_notes`` map
  term -> spoken form; unrecognized terms pass through unchanged);
* whitespace / markdown-artefact collapse so synthesized audio has no stuttered
  pauses from ``**bold**`` residue or doubled spaces.

Normalization is PURE and DETERMINISTIC: identical input always yields identical
output, which is what lets CI assert ``sha256``-stable audio manifests from the
fake TTS provider. No provider key is required.
"""

from __future__ import annotations

import re

from ..contracts.multimedia import ScriptLine

# Abbreviations a TTS engine would otherwise read as letters. Lowercase-keyed,
# case-insensitive match, but the replacement preserves sentence position via the
# surrounding tokenizer (word-boundary regex). Curated, not exhaustive: each entry
# has a defensible "this reads wrong aloud" justification.
_DEFAULT_ABBREVIATIONS: dict[str, str] = {
    "e.g.": "for example",
    "eg.": "for example",
    "i.e.": "that is",
    "ie.": "that is",
    "etc.": "and so on",
    "vs.": "versus",
    "v.": "versus",
    "approx.": "approximately",
    "max.": "maximum",
    "min.": "minimum",
    "fig.": "figure",
    "ref.": "reference",
    "no.": "number",
    "pp.": "pages",
    "p.": "page",
    "dept.": "department",
    "inc.": "incorporated",
    "corp.": "corporation",
    "ltd.": "limited",
    "Dr.": "Doctor",
    "Mr.": "Mister",
    "Mrs.": "Missus",
    "Ms.": "Miss",
    "Prof.": "Professor",
    "Jan.": "January",
    "Feb.": "February",
    "Aug.": "August",
    "Sept.": "September",
    "Oct.": "October",
    "Nov.": "November",
    "Dec.": "December",
}

# Markdown / typographic artefacts that produce audible stutter or dead air.
_MARKDOWN_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\*\*(.+?)\*\*"), r"\1"),  # **bold** -> bold
    (re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)"), r"\1"),  # *italic* -> italic
    (re.compile(r"__([^_]+?)__"), r"\1"),  # __underline__ -> underline
    (re.compile(r"`([^`]+?)`"), r"\1"),  # `code` -> code
    (re.compile(r"\[([^\]]+?)\]\([^)]+?\)"), r"\1"),  # [text](url) -> text
    (re.compile(r"\s+"), " "),  # collapse all whitespace runs to one space
)


class NarrationParagraph:
    """One speech-ready paragraph, fully traceable to its source script line.

    ``line_id`` and ``source_chunk_ids`` are copied straight off the originating
    :class:`~substrate.planner.ScriptLine` so the grounding map is never lost in
    the transform to spoken text. ``unsourced`` mirrors the planner's
    ``unsourced_line_ids`` discipline: a factual paragraph with no citations is
    flagged, never silently hidden."""

    __slots__ = ("para_id", "line_id", "text", "kind", "source_chunk_ids", "unsourced")

    def __init__(
        self,
        *,
        para_id: str,
        line_id: str,
        text: str,
        kind: str,
        source_chunk_ids: tuple[str, ...],
        unsourced: bool,
    ) -> None:
        if not text.strip():
            raise ValueError(
                f"narration paragraph {para_id!r} has empty spoken text; "
                "a spoken paragraph must say something"
            )
        self.para_id = para_id
        self.line_id = line_id
        self.text = text
        self.kind = kind
        self.source_chunk_ids = source_chunk_ids
        self.unsourced = unsourced

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"NarrationParagraph(para_id={self.para_id!r}, line_id={self.line_id!r}, kind={self.kind!r}, unsourced={self.unsourced}, chunks={len(self.source_chunk_ids)})"


def _expand_abbreviations(text: str, notes: dict[str, str]) -> str:
    """Replace abbreviation + pronunciation-note tokens with their spoken form.

    Operator ``notes`` take precedence over the default abbreviation table so a
    domain term (``"SiC"`` -> ``"silicon carbide"``) can override a default.
    Matching is case-insensitive on the key but only replaces token-equal spans
    (word boundaries), so ``"etc."`` expands but ``"etcetera"`` is untouched."""
    table: dict[str, str] = {**_DEFAULT_ABBREVIATIONS, **(notes or {})}
    if not table:
        return text
    out = text
    for token, spoken in table.items():
        # Escape the token for regex; boundary match prevents mid-word hits.
        pattern = re.compile(rf"(?<!\w){re.escape(token)}(?!\w)", re.IGNORECASE)
        out = pattern.sub(spoken, out)
    return out


def _strip_markdown(text: str) -> str:
    for pattern, replacement in _MARKDOWN_PATTERNS:
        text = pattern.sub(replacement, text)
    return text.strip()


def normalize_line(
    line: ScriptLine,
    *,
    pronunciation_notes: dict[str, str] | None = None,
) -> NarrationParagraph:
    """Normalize a single script line into one speech-ready paragraph.

    Source alignment (``line_id`` + citation ``chunk_ids``) is carried through
    unchanged; only the spoken surface is transformed. A factual line with no
    citations is marked ``unsourced=True`` (mirroring the planner's discipline)
    rather than dropped — the listener still hears it, and the player still
    surfaces the gap honestly."""
    text = _strip_markdown(line.text)
    text = _expand_abbreviations(text, pronunciation_notes or {})
    text = _strip_markdown(text)  # abbreviation expansion can re-introduce doubles
    if not text:
        raise ValueError(
            f"script line {line.line_id!r} normalized to empty spoken text; "
            "every cited line must carry speakable content"
        )
    chunk_ids = tuple(c.chunk_id for c in line.citations)
    return NarrationParagraph(
        para_id=f"para-{line.line_id}",
        line_id=line.line_id,
        text=text,
        kind=line.kind,
        source_chunk_ids=chunk_ids,
        unsourced=(line.kind == "factual" and not chunk_ids),
    )


def normalize_script(
    script_lines: tuple[ScriptLine, ...],
    *,
    pronunciation_notes: dict[str, str] | None = None,
) -> tuple[NarrationParagraph, ...]:
    """Normalize an ordered script into speech-ready paragraphs.

    Order is preserved exactly (paragraphs narrate in script order). The returned
    tuple is the input to chapter assembly: each paragraph is one TTS unit and
    carries its own source-alignment, so a chapter's audio file can be rebuilt
    deterministically from its paragraphs alone."""
    if not script_lines:
        raise ValueError(
            "cannot normalize an empty script; a narration requires >=1 script line"
        )
    return tuple(
        normalize_line(line, pronunciation_notes=pronunciation_notes)
        for line in script_lines
    )
