"""`.antiek` native container for born-Antiek content (SPR-09).

Public API entry points:

- ``write_antiek(WriterInput, keypair=...) -> bytes`` — produce a
  signed, deterministic ``.antiek`` archive.
- ``read_antiek(bytes) -> ReadResult`` — parse + validate + verify.
- ``project_to_markdown(bytes) -> str`` — universal-fallback
  markdown projection (one-way, lossy).
- ``ensure_keypair(user_id, db_path=...) -> Keypair`` — manage the
  long-lived Ed25519 keypair.

See ``SPEC.md`` for the wire format and ``SIGNATURE_NOTES.md`` for the
key-management decisions.

Sidecar variant (SPEC.md §11): NOT yet present on main. The sidecar
overlay (``sidecar_writer`` / ``sidecar_reader``) is functionally wired
to the voice-anchor + behavior-taxonomy substrate, which has not landed
on main; it is SEQUENCED behind that substrate landing, not dropped.
See ``docs/decisions/antiek-html-shell-amendment-DRAFT.md`` for the
sequencing record. (Decision lineage: binding decision #2 in
``docs/decisions/wrestle-evolution-spec-2026-05-23.md``.)
"""

from __future__ import annotations

from .markdown_projector import HEADER_COMMENT, project_to_markdown
from .native_reader import (
    AntiekFormatError,
    MalformedAntiek,
    ManifestValidationError,
    ReadResult,
    UnsupportedVersion,
    canonical_tiptap_bytes,
    read_antiek,
)
from .native_writer import (
    BLOCKS_PREFIX,
    CONTENT_CLASSES,
    SCHEMA_VERSION,
    WriterInput,
    write_antiek,
)
from .signature import Keypair, ensure_keypair, sign_bytes, verify_bytes

__all__ = [
    "AntiekFormatError",
    "BLOCKS_PREFIX",
    "CONTENT_CLASSES",
    "HEADER_COMMENT",
    "Keypair",
    "MalformedAntiek",
    "ManifestValidationError",
    "ReadResult",
    "SCHEMA_VERSION",
    "UnsupportedVersion",
    "WriterInput",
    "canonical_tiptap_bytes",
    "ensure_keypair",
    "project_to_markdown",
    "read_antiek",
    "sign_bytes",
    "verify_bytes",
    "write_antiek",
]
