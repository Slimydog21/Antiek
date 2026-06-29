"""Island-only ingest for returning born-Antiek artifacts (HPRJ SPR-07 M2).

When a ``.antiek`` container or single-file ``name.antiek.html`` comes back to
Antiek, ingestion reads ONLY the signed structured doc-model — never the
rendered HTML — and quarantines on a signature that does not verify. The
structured payload is framed as quoted DATA, never instructions, on its way
into any LLM context.

Scope (honest, per the sprint's M5 discipline): this closes the
ARTIFACT-shaped slice — island-only ingest + signature gating for born-Antiek
files. It does NOT verify the §7 daemon's general data/instruction boundary;
every non-artifact path (tool outputs, web fetches outside acquisition,
model-generated text re-entering packs) is out of scope and stays open.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from services.antiek_format import AntiekFormatError, read_antiek
from services.antiek_format.single_file import verify_single_file_html
from services.html_projection.island import extract_island

_DOC_ISLAND_MARKER = 'data-antiek="doc-model"'
_SIG_ISLAND_MARKER = 'data-antiek="signature"'


@dataclass(frozen=True)
class IngestResult:
    """Outcome of ingesting a born-Antiek artifact. ``doc_model`` is the SIGNED
    structured payload (never parsed from rendered HTML); ``framing`` records
    that it enters any LLM context as quoted data, not instructions."""

    ok: bool
    doc_model: Optional[dict]
    quarantined: bool
    reason: Optional[str]
    framing: str = "quoted_payload"


def ingest_antiek(data: bytes) -> IngestResult:
    """Ingest a returning born-Antiek artifact, island-only.

    - ``.antiek`` container: read the SIGNED ``content.tiptap.json`` structured
      doc-model; the rendered ``projection.html`` is NEVER parsed for content.
    - single-file ``.antiek.html``: verify the whole-file signature, then
      extract the doc-model island. The visible markup is never parsed.

    A signature that does not verify (or a malformed/unsigned artifact)
    QUARANTINES with a logged reason — it is never silently ingested.
    """
    # 1. .antiek container — a deterministic ZIP (PK magic).
    if data[:2] == b"PK":
        try:
            result = read_antiek(data)
        except AntiekFormatError as exc:
            return IngestResult(False, None, True, f"malformed .antiek container: {exc}")
        if not result.signature_valid:
            return IngestResult(
                False, None, True, "container signature did not verify; quarantined"
            )
        # The SIGNED structured content — NOT the rendered projection.html.
        return IngestResult(True, result.content_tiptap, False, None)

    # 2. single-file .antiek.html — verify the whole-file signature, then
    #    extract the doc-model island. Never parse the visible markup.
    try:
        html = data.decode("utf-8")
    except UnicodeDecodeError:
        return IngestResult(
            False, None, True, "not a .antiek container nor a UTF-8 .antiek.html"
        )
    if _DOC_ISLAND_MARKER not in html:
        return IngestResult(
            False, None, True, "no .antiek doc-model island; not a born-Antiek artifact"
        )
    if _SIG_ISLAND_MARKER not in html:
        return IngestResult(
            False, None, True, "single-file artifact carries no signature island; quarantined"
        )
    if not verify_single_file_html(html):
        return IngestResult(
            False, None, True, "single-file signature did not verify; quarantined"
        )
    try:
        doc_model = extract_island(html)
    except Exception as exc:  # extractor raises on a malformed/absent island
        return IngestResult(False, None, True, f"doc-model island unreadable: {exc}")
    return IngestResult(True, doc_model, False, None)


__all__ = ["IngestResult", "ingest_antiek"]
