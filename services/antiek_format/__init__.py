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
from .sidecar_reader import (
    HASH_MISMATCH_WARNING,
    ApplyReport,
    MissingSidecarFields,
    NotASidecar,
    RestoredSidecar,
    SidecarHashMismatch,
    apply_sidecar,
    read_sidecar,
)
from .sidecar_writer import (
    SIDECAR_CONTENT_CLASS,
    AnchorRow,
    HighlightRow,
    SidecarInput,
    build_sidecar_input_for_document,
    write_sidecar,
)
from .signature import Keypair, ensure_keypair, sign_bytes, verify_bytes

__all__ = [
    "AnchorRow",
    "AntiekFormatError",
    "ApplyReport",
    "BLOCKS_PREFIX",
    "CONTENT_CLASSES",
    "HASH_MISMATCH_WARNING",
    "HEADER_COMMENT",
    "HighlightRow",
    "Keypair",
    "MalformedAntiek",
    "ManifestValidationError",
    "MissingSidecarFields",
    "NotASidecar",
    "ReadResult",
    "RestoredSidecar",
    "SCHEMA_VERSION",
    "SIDECAR_CONTENT_CLASS",
    "SidecarHashMismatch",
    "SidecarInput",
    "UnsupportedVersion",
    "WriterInput",
    "apply_sidecar",
    "build_sidecar_input_for_document",
    "canonical_tiptap_bytes",
    "ensure_keypair",
    "project_to_markdown",
    "read_antiek",
    "read_sidecar",
    "sign_bytes",
    "verify_bytes",
    "write_antiek",
    "write_sidecar",
]
