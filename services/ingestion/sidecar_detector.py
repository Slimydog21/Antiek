"""Ingest-time sidecar detection + apply (SPR-10 / M4).

Detection sources
-----------------
1. **Zip upload** — when the uploaded file is a zip containing
   ``foo.pdf`` + ``foo.antiek``, the PDF is ingested via the normal
   pipeline AND the sidecar is applied after the substrate write
   completes.
2. **URL parameter** — when the ingest request carries
   ``source_metadata={"sidecar_url": "..."}`` (or the canonical
   ``?sidecar=`` query param the API exposes), we fetch the sidecar
   URL after the PDF ingest succeeds and apply.
3. **Adjacent-file path** — when both files arrive as a multi-file
   upload with the same basename, the dispatch logic at the upload
   handler resolves them and calls this module's
   ``apply_sidecar_for_pdf_after_ingest`` directly.

Insertion point
---------------
``pipeline.ingest`` calls ``apply_sidecar_for_pdf_after_ingest`` AFTER
the substrate write block (see ``pipeline.py`` step 5 → 6). The
sidecar's anchors must resolve against built chunks, so the apply
MUST follow chunking + embedding. Running before would resolve every
anchor to NULL.

Diligence (rigor #4): we deliberately do NOT run before substrate
writes; the SPR-03 pipeline's read of the docstring identifies this
ordering invariant.

Hash mismatch (rigor #1)
------------------------
A sidecar made for a different PDF revision will produce
``RestoredSidecar.hash_mismatch=True``. The detector surfaces this as
a structured event (``SidecarApplyOutcome``) but does NOT auto-apply.
The UI consumes the outcome and shows the documented warning text;
the operator decides whether to force-apply via a follow-up call.

Signature failures (rigor #5)
-----------------------------
Per SPEC.md §11.6, signature verification failure does NOT block the
restore — rows are flagged ``imported_from_unsigned_sidecar=true``.
The detector returns ``signature_valid=False`` in the outcome so the
UI can surface the appropriate ribbon.
"""

from __future__ import annotations

import io
import logging
import os
import sys
import zipfile
from dataclasses import dataclass, field
from typing import Optional

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


_log = logging.getLogger(__name__)


SIDECAR_EXTENSION = ".antiek"


# ── Outcome shape ──


@dataclass
class SidecarApplyOutcome:
    """What happened when the pipeline tried to apply a sidecar.

    The fields mirror the UX strings the surface needs ("Restored 24
    highlights + 5 voice notes from sidecar", "Sidecar was made for a
    different PDF — annotations not applied"). The handler renders the
    appropriate banner from these fields.
    """

    detected: bool = False
    applied: bool = False
    hash_mismatch: bool = False
    signature_valid: bool = True
    highlights_written: int = 0
    anchors_written: int = 0
    edges_written: int = 0
    audio_blobs_written: int = 0
    sidecar_source: Optional[str] = None  # "zip" | "url" | "adjacent"
    error: Optional[str] = None
    warnings: list[str] = field(default_factory=list)
    ui_message: Optional[str] = None  # ready-to-render summary line

    def to_dict(self) -> dict:
        return {
            "detected": self.detected,
            "applied": self.applied,
            "hash_mismatch": self.hash_mismatch,
            "signature_valid": self.signature_valid,
            "highlights_written": self.highlights_written,
            "anchors_written": self.anchors_written,
            "edges_written": self.edges_written,
            "audio_blobs_written": self.audio_blobs_written,
            "sidecar_source": self.sidecar_source,
            "error": self.error,
            "warnings": list(self.warnings),
            "ui_message": self.ui_message,
        }


# ── Zip-upload detection ──


@dataclass
class ZipUploadParse:
    """Result of parsing a multi-file zip upload."""

    pdf_bytes: Optional[bytes] = None
    sidecar_bytes: Optional[bytes] = None
    pdf_filename: Optional[str] = None
    sidecar_filename: Optional[str] = None


def parse_zip_upload(zip_bytes: bytes) -> ZipUploadParse:
    """Parse a zip upload looking for a PDF + same-basename sidecar.

    Detection rule: the zip MUST contain exactly one ``.pdf`` AND one
    ``.antiek`` with the same basename (e.g., ``foo.pdf`` +
    ``foo.antiek``). Multiple PDFs / multiple sidecars → both are
    surfaced as ``None`` (the upload handler raises a 400 in that
    case — caller can disambiguate).

    Returns
    -------
    ZipUploadParse
        Both fields set when the detection succeeds; either may be
        None when the zip doesn't carry the expected pair.
    """
    out = ZipUploadParse()
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes), mode="r")
    except zipfile.BadZipFile:
        return out

    pdf_candidates: list[tuple[str, bytes]] = []
    sidecar_candidates: list[tuple[str, bytes]] = []
    with zf:
        for n in zf.namelist():
            lower = n.lower()
            if lower.endswith("/"):
                continue
            # Skip macOS-style metadata entries.
            base = os.path.basename(n)
            if base.startswith("._") or "__MACOSX" in n:
                continue
            if lower.endswith(".pdf"):
                pdf_candidates.append((n, zf.read(n)))
            elif lower.endswith(SIDECAR_EXTENSION):
                sidecar_candidates.append((n, zf.read(n)))

    if len(pdf_candidates) != 1 or len(sidecar_candidates) > 1:
        # Too many PDFs or too many sidecars — caller disambiguates.
        if len(pdf_candidates) >= 1:
            out.pdf_filename, out.pdf_bytes = pdf_candidates[0]
        return out

    pdf_name, pdf_data = pdf_candidates[0]
    out.pdf_filename = pdf_name
    out.pdf_bytes = pdf_data

    if not sidecar_candidates:
        return out

    sidecar_name, sidecar_data = sidecar_candidates[0]
    # Basename match (ignore directory + case).
    pdf_basename = os.path.splitext(os.path.basename(pdf_name))[0].lower()
    sc_basename = os.path.splitext(os.path.basename(sidecar_name))[0].lower()
    if pdf_basename != sc_basename:
        # We still surface the sidecar — sometimes the user pairs by
        # intent ("highlights.antiek" + "paper.pdf"). The reader's
        # parent_pdf_sha256 check is the authoritative pair test;
        # basename is heuristic. Log + proceed.
        _log.info(
            "parse_zip_upload: PDF basename %r differs from sidecar "
            "basename %r; relying on parent_pdf_sha256 to verify pair.",
            pdf_basename, sc_basename,
        )
    out.sidecar_filename = sidecar_name
    out.sidecar_bytes = sidecar_data
    return out


def is_antiek_sidecar_bytes(data: bytes) -> bool:
    """Cheap check: does the data look like an .antiek archive carrying
    a sidecar? We open the zip and peek at the manifest's content_class.

    Used by the upload handler to disambiguate "this is a sidecar I
    should apply after the PDF" vs "this is a notebook .antiek the
    user dropped in".
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(data), mode="r")
    except zipfile.BadZipFile:
        return False
    try:
        names = set(zf.namelist())
        if "manifest.json" not in names:
            return False
        import json
        with zf.open("manifest.json") as f:
            manifest = json.loads(f.read().decode("utf-8"))
    except (json.JSONDecodeError, OSError, KeyError):
        return False
    finally:
        zf.close()
    return manifest.get("content_class") == "pdf_sidecar"


# ── Apply hook (post-substrate-write) ──


def apply_sidecar_for_pdf_after_ingest(
    *,
    sidecar_bytes: bytes,
    pdf_bytes: bytes,
    document_id: str,
    user_id: str,
    db_path: str,
    sidecar_source: str = "zip",
    audio_storage_root: Optional[str] = None,
) -> SidecarApplyOutcome:
    """Apply a sidecar after the PDF has finished ingesting.

    Caller contract: the PDF row + chunks + embeddings + edges have
    already been written via the standard pipeline. Anchors will be
    re-resolved against the live chunker.

    Parameters
    ----------
    sidecar_bytes : bytes
        The ``.antiek`` sidecar archive.
    pdf_bytes : bytes
        The PDF bytes that were ingested. Used for the
        parent_pdf_sha256 check (rigor #1).
    document_id : str
        The substrate document_id assigned to the PDF by the
        ingest pipeline.
    user_id : str
        The user attempting the restore.
    db_path : str
        Path to the substrate DuckDB.
    sidecar_source : str
        Free-form label ("zip" | "url" | "adjacent") carried into
        the outcome for UI rendering.

    Returns
    -------
    SidecarApplyOutcome
        Always returns; never raises for normal failure modes. A
        substrate-write crash is treated as "applied=False, error=...".
    """
    from services.antiek_format import (
        HASH_MISMATCH_WARNING,
        MissingSidecarFields,
        NotASidecar,
        apply_sidecar,
        read_sidecar,
    )
    from services.antiek_format.sidecar_reader import (
        SidecarHashMismatch,
        AntiekFormatError,
    )
    import hashlib

    outcome = SidecarApplyOutcome(
        detected=True, sidecar_source=sidecar_source,
    )

    imported_pdf_sha = hashlib.sha256(pdf_bytes).hexdigest()
    try:
        restored = read_sidecar(
            sidecar_bytes,
            imported_pdf_sha256=imported_pdf_sha,
            strict=False,
        )
    except MissingSidecarFields as e:
        outcome.applied = False
        outcome.error = f"sidecar_missing_required_field: {e}"
        outcome.ui_message = (
            "Sidecar file is missing required fields and was not applied."
        )
        return outcome
    except NotASidecar as e:
        outcome.applied = False
        outcome.error = f"not_a_sidecar: {e}"
        outcome.ui_message = (
            "Attached .antiek is a notebook, not a sidecar; not applied."
        )
        return outcome
    except AntiekFormatError as e:
        outcome.applied = False
        outcome.error = f"sidecar_parse_failed: {e}"
        outcome.ui_message = "Sidecar file could not be parsed; not applied."
        return outcome

    outcome.signature_valid = restored.signature_valid
    outcome.hash_mismatch = restored.hash_mismatch

    if restored.hash_mismatch:
        # Rigor #1: do NOT silently apply. Surface the documented
        # warning text verbatim so the UX matches SPEC.md §11.7.
        outcome.applied = False
        outcome.ui_message = HASH_MISMATCH_WARNING
        outcome.warnings.append(HASH_MISMATCH_WARNING)
        return outcome

    try:
        report = apply_sidecar(
            restored,
            db_path=db_path,
            user_id=user_id,
            audio_storage_root=audio_storage_root,
        )
    except Exception as e:  # noqa: BLE001
        outcome.applied = False
        outcome.error = f"sidecar_apply_failed: {e!r}"
        outcome.ui_message = "Sidecar parse OK but substrate write failed."
        return outcome

    outcome.applied = True
    outcome.highlights_written = report.highlights_written
    outcome.anchors_written = report.anchors_written
    outcome.edges_written = report.edges_written
    outcome.audio_blobs_written = report.audio_blobs_written
    outcome.warnings.extend(report.warnings)

    # UI message: the sprint HTML names the format
    # "Restored 24 highlights + 5 voice notes from sidecar".
    parts: list[str] = []
    if outcome.highlights_written:
        parts.append(f"{outcome.highlights_written} highlight"
                     + ("s" if outcome.highlights_written != 1 else ""))
    if outcome.anchors_written:
        parts.append(f"{outcome.anchors_written} voice note"
                     + ("s" if outcome.anchors_written != 1 else ""))
    if outcome.edges_written:
        parts.append(f"{outcome.edges_written} user-asserted edge"
                     + ("s" if outcome.edges_written != 1 else ""))
    if not parts:
        outcome.ui_message = "Sidecar applied: no new rows (already imported)."
    else:
        joined = " + ".join(parts)
        suffix = ""
        if not outcome.signature_valid:
            suffix = " (signature did not verify — rows flagged)"
        outcome.ui_message = f"Restored {joined} from sidecar{suffix}."

    return outcome


# ── URL fetch helper (for ?sidecar=<url> path) ──


def fetch_sidecar_from_url(
    sidecar_url: str, *, timeout_s: float = 30.0,
) -> Optional[bytes]:
    """Fetch a sidecar from a URL (the ``?sidecar=...`` flow).

    Uses httpx with a tight timeout — sidecars are KB-MB, not GB.
    Returns None on any failure rather than raising; the caller
    rolls the failure into a SidecarApplyOutcome with an error.

    Out of scope (per the sprint page): URL-pattern conventions (e.g.
    auto-discovering ``foo.antiek`` next to a fetched ``foo.pdf``).
    The URL must be supplied explicitly.
    """
    try:
        import httpx
    except ImportError:  # pragma: no cover
        _log.warning("fetch_sidecar_from_url: httpx not available")
        return None
    try:
        with httpx.Client(timeout=timeout_s, follow_redirects=True) as client:
            resp = client.get(sidecar_url)
            resp.raise_for_status()
            return resp.content
    except Exception as e:  # noqa: BLE001
        _log.warning("fetch_sidecar_from_url(%r) failed: %s", sidecar_url, e)
        return None


__all__ = [
    "SIDECAR_EXTENSION",
    "SidecarApplyOutcome",
    "ZipUploadParse",
    "apply_sidecar_for_pdf_after_ingest",
    "fetch_sidecar_from_url",
    "is_antiek_sidecar_bytes",
    "parse_zip_upload",
]
