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
from typing import Any, Final

from services.antiek_format import read_antiek
from services.antiek_format.single_file import verify_single_file_html
from services.demand_gate.roundtrip_detector import ExportRegistry, classify_roundtrip
from services.html_projection.island import extract_island

_DOC_ISLAND_MARKER = 'data-antiek="doc-model"'
_SIG_ISLAND_MARKER = 'data-antiek="signature"'

# ── the typed quarantine vocabulary ──
#
# The classification is the product. A caller has to tell a TAMPERED artifact —
# a real signature that does not verify over these bytes — from a MALFORMED one
# that was never a readable born-Antiek artifact, and it must be able to do that
# without pattern-matching on prose, because prose drifts and a route that reads
# it becomes a lie the first time someone rewords a message. So every quarantine
# path returns one of these codes next to its human-readable reason.
REASON_MALFORMED_CONTAINER: Final[str] = "malformed_container"
REASON_CONTAINER_SIGNATURE_INVALID: Final[str] = "container_signature_invalid"
REASON_NOT_ANTIEK_BYTES: Final[str] = "not_antiek_bytes"
REASON_NO_DOC_MODEL_ISLAND: Final[str] = "no_doc_model_island"
REASON_UNSIGNED_SINGLE_FILE: Final[str] = "unsigned_single_file"
REASON_SINGLE_FILE_SIGNATURE_INVALID: Final[str] = "single_file_signature_invalid"
REASON_ISLAND_UNREADABLE: Final[str] = "island_unreadable"

# The four dispositions a quarantine can carry. They answer different questions
# and deserve different words: `tampered` means the artifact carried a signature
# and the bytes no longer match it (someone edited a signed file); `unsigned`
# means a born-Antiek projection arrived with no signature island at all, which
# is a missing claim rather than a broken one; `not_antiek` means these bytes
# never claimed to be a born-Antiek artifact; `malformed` means they did claim
# it and the claim is unreadable.
DISPOSITION_TAMPERED: Final[str] = "tampered"
DISPOSITION_UNSIGNED: Final[str] = "unsigned"
DISPOSITION_NOT_ANTIEK: Final[str] = "not_antiek"
DISPOSITION_MALFORMED: Final[str] = "malformed"

QUARANTINE_DISPOSITIONS: Final[dict[str, str]] = {
    REASON_CONTAINER_SIGNATURE_INVALID: DISPOSITION_TAMPERED,
    REASON_SINGLE_FILE_SIGNATURE_INVALID: DISPOSITION_TAMPERED,
    REASON_UNSIGNED_SINGLE_FILE: DISPOSITION_UNSIGNED,
    REASON_NOT_ANTIEK_BYTES: DISPOSITION_NOT_ANTIEK,
    REASON_NO_DOC_MODEL_ISLAND: DISPOSITION_NOT_ANTIEK,
    REASON_MALFORMED_CONTAINER: DISPOSITION_MALFORMED,
    REASON_ISLAND_UNREADABLE: DISPOSITION_MALFORMED,
}


def quarantine_disposition(reason_code: str | None) -> str:
    """The disposition for a quarantine code.

    An unmapped code falls back to ``malformed``: every disposition refuses the
    artifact, so the fallback costs no safety, and naming an unknown failure
    "malformed" is the honest reading of "we could not make sense of this".
    """
    if reason_code is None:
        return DISPOSITION_MALFORMED
    return QUARANTINE_DISPOSITIONS.get(reason_code, DISPOSITION_MALFORMED)


@dataclass(frozen=True)
class IngestResult:
    """Outcome of ingesting a born-Antiek artifact. ``doc_model`` is the SIGNED
    structured payload (never parsed from rendered HTML); ``framing`` records
    that it enters any LLM context as quoted data, not instructions."""

    ok: bool
    doc_model: dict | None
    quarantined: bool
    reason: str | None
    framing: str = "quoted_payload"
    # SPR-08 M2: round-trip classification when an ExportRegistry is supplied —
    # "returned_unmodified" | "traveled_and_changed", else None (not a tracked
    # round-trip, or no registry passed).
    roundtrip: str | None = None
    # HPRJ SPR-4: the machine-readable half of ``reason``, one of the
    # ``REASON_*`` codes above. None on success.
    reason_code: str | None = None
    # The artifact's own identity, when it carries one. A container states it in
    # the signed manifest; a single-file states it only if the doc-model island
    # was built by an adapter that recorded a source document. A caller that
    # stores the returning artifact needs this to put it back where it came
    # from rather than minting a stranger.
    document_id: str | None = None
    title: str | None = None

    @property
    def disposition(self) -> str | None:
        """Why a quarantined artifact was refused, as a disposition word.
        None when the artifact was not quarantined."""
        if not self.quarantined:
            return None
        return quarantine_disposition(self.reason_code)


def ingest_antiek(
    data: bytes, *, export_registry: ExportRegistry | None = None
) -> IngestResult:
    """Ingest a returning born-Antiek artifact, island-only.

    - ``.antiek`` container: read the SIGNED ``content.tiptap.json`` structured
      doc-model; the rendered ``projection.html`` is NEVER parsed for content.
    - single-file ``.antiek.html``: verify the whole-file signature, then
      extract the doc-model island. The visible markup is never parsed.

    A signature that does not verify (or a malformed/unsigned artifact)
    QUARANTINES with a logged reason — it is never silently ingested.

    SPR-08 M2: when ``export_registry`` is supplied, a verified container is
    classified against prior exports (returned_unmodified / traveled_and_changed)
    — the only admissible demand signal — and the classification is recorded on
    the result. Detection NEVER changes the ingest decision; a quarantined
    artifact is never classified.
    """
    # 1. .antiek container — a deterministic ZIP (PK magic).
    if data[:2] == b"PK":
        try:
            result = read_antiek(data)
        except Exception as exc:  # noqa: BLE001 — an ingestion boundary must
            # NEVER crash on malformed/hostile bytes. ANY read failure (bad zip,
            # bad CRC-32, missing/extra entry, an unverifiable signature that
            # raises) quarantines with a reason — it is never silently ingested
            # and never propagates an exception to the caller.
            return IngestResult(
                False,
                None,
                True,
                f"malformed .antiek container: {exc}",
                reason_code=REASON_MALFORMED_CONTAINER,
            )
        if not result.signature_valid:
            return IngestResult(
                False,
                None,
                True,
                "container signature did not verify; quarantined",
                reason_code=REASON_CONTAINER_SIGNATURE_INVALID,
            )
        roundtrip = None
        if export_registry is not None:
            rt = classify_roundtrip(
                result.document_id, result.content_tiptap, export_registry
            )
            roundtrip = rt.classification if rt.is_roundtrip else None
        # The SIGNED structured content — NOT the rendered projection.html.
        return IngestResult(
            True,
            result.content_tiptap,
            False,
            None,
            roundtrip=roundtrip,
            document_id=result.document_id,
            title=result.title,
        )

    # 2. single-file .antiek.html — verify the whole-file signature, then
    #    extract the doc-model island. Never parse the visible markup.
    try:
        html = data.decode("utf-8")
    except UnicodeDecodeError:
        return IngestResult(
            False,
            None,
            True,
            "not a .antiek container nor a UTF-8 .antiek.html",
            reason_code=REASON_NOT_ANTIEK_BYTES,
        )
    if _DOC_ISLAND_MARKER not in html:
        return IngestResult(
            False,
            None,
            True,
            "no .antiek doc-model island; not a born-Antiek artifact",
            reason_code=REASON_NO_DOC_MODEL_ISLAND,
        )
    if _SIG_ISLAND_MARKER not in html:
        return IngestResult(
            False,
            None,
            True,
            "single-file artifact carries no signature island; quarantined",
            reason_code=REASON_UNSIGNED_SINGLE_FILE,
        )
    if not verify_single_file_html(html):
        return IngestResult(
            False,
            None,
            True,
            "single-file signature did not verify; quarantined",
            reason_code=REASON_SINGLE_FILE_SIGNATURE_INVALID,
        )
    try:
        doc_model = extract_island(html)
    except Exception as exc:  # extractor raises on a malformed/absent island
        return IngestResult(
            False,
            None,
            True,
            f"doc-model island unreadable: {exc}",
            reason_code=REASON_ISLAND_UNREADABLE,
        )
    return IngestResult(
        True,
        doc_model,
        False,
        None,
        document_id=_island_document_id(doc_model),
        title=_island_title(doc_model),
    )


def _island_document_id(doc_model: dict[str, Any]) -> str | None:
    """The source document a single-file artifact names, if it names one.

    ``adapt_document_for_projection`` records the substrate document in the
    doc-model's ``source`` block precisely so the island still names its own
    origin after the artifact has left Antiek. A projection built some other way
    carries no ``source``, and that absence is honest: the artifact genuinely
    does not know where it came from, and a caller must mint an identity rather
    than guess at one.
    """
    source = doc_model.get("source")
    if not isinstance(source, dict):
        return None
    value = source.get("document_id")
    return value if isinstance(value, str) and value else None


def _island_title(doc_model: dict[str, Any]) -> str | None:
    value = doc_model.get("title")
    return value if isinstance(value, str) and value else None


__all__ = [
    "DISPOSITION_MALFORMED",
    "DISPOSITION_NOT_ANTIEK",
    "DISPOSITION_TAMPERED",
    "DISPOSITION_UNSIGNED",
    "QUARANTINE_DISPOSITIONS",
    "REASON_CONTAINER_SIGNATURE_INVALID",
    "REASON_ISLAND_UNREADABLE",
    "REASON_MALFORMED_CONTAINER",
    "REASON_NOT_ANTIEK_BYTES",
    "REASON_NO_DOC_MODEL_ISLAND",
    "REASON_SINGLE_FILE_SIGNATURE_INVALID",
    "REASON_UNSIGNED_SINGLE_FILE",
    "IngestResult",
    "ingest_antiek",
    "quarantine_disposition",
]
