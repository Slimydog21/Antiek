"""Reader: .antiek bytes → notebook (SPR-09 / M3).

The inverse of ``native_writer.write_antiek``. Parses the zip, validates
the manifest against the JSON schema, verifies the Ed25519 signature,
and returns a structured ``ReadResult`` the persistence layer hydrates
into substrate rows.

Round-trip identity (M3 + M7)
-----------------------------
``read_antiek(write_antiek(input)) == input`` is tested at the level of
**TipTap-canonical bytes equality**, not naive deep equality of the
dict — TipTap considers some shapes equivalent that naive Python
dict-equality does not. ``canonical_tiptap_bytes`` is the comparator
used by tests and by the persistence layer's migrate-forward path.

Version policy (SPEC.md §7)
---------------------------
- Major-version mismatch (file major != reader major) → raise
  ``UnsupportedVersion``.
- Minor-version mismatch (file minor > reader minor) → log a warning,
  proceed. The reader is allowed to ignore manifest keys it doesn't
  recognise; the writer preserves them on round-trip.
- Patch-version mismatch → silent.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any

try:
    from .native_writer import (
        BLOCKS_PREFIX,
        CONTENT_CLASSES,
        ENTRY_CONTENT,
        ENTRY_EDGES,
        ENTRY_MANIFEST,
        ENTRY_PROJECTION,
        ENTRY_SIGNATURE,
        SCHEMA_VERSION,
        _canonical_tiptap_node,
    )
    from .signature import (
        build_signing_input,
        canonical_edges_bytes,
        canonical_json_bytes,
        verify_bytes,
    )
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from services.antiek_format.native_writer import (
        BLOCKS_PREFIX,
        CONTENT_CLASSES,
        ENTRY_CONTENT,
        ENTRY_EDGES,
        ENTRY_MANIFEST,
        ENTRY_PROJECTION,
        ENTRY_SIGNATURE,
        SCHEMA_VERSION,
        _canonical_tiptap_node,
    )
    from services.antiek_format.signature import (
        build_signing_input,
        canonical_edges_bytes,
        canonical_json_bytes,
        verify_bytes,
    )


_log = logging.getLogger(__name__)

_SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "manifest.schema.json"
)


# ── Errors ──


class AntiekFormatError(Exception):
    """Base class for .antiek read errors."""


class MalformedAntiek(AntiekFormatError):
    """Zip structure is wrong (missing required entries, junk inside)."""


class ManifestValidationError(AntiekFormatError):
    """The manifest.json failed schema validation."""


class UnsupportedVersion(AntiekFormatError):
    """Major version mismatch — reader refuses to parse."""


# ── Output ──


@dataclass
class ReadResult:
    """The structured output of a `.antiek` read.

    The persistence layer hydrates the substrate from this. The
    rendering surface treats ``signature_valid=False`` as a UI flag,
    not a hard error — a tampered notebook is still readable; it just
    can't be republished.
    """

    schema_version: str
    content_class: str
    document_id: str
    parent_document_id: str | None
    notebook_id: str | None
    user_id: str
    creator_pubkey: str
    title: str | None
    format_version: int | None
    created_at: str  # ISO-8601 string as written
    content_tiptap: dict[str, Any]
    blocks_index: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    audio_blobs: dict[str, bytes]
    signature_valid: bool
    # Keys the reader didn't recognise. Carried forward on a round-trip
    # save so we don't strip newer-version metadata.
    manifest_unknown_keys: dict[str, Any] = field(default_factory=dict)
    # SPR-04: the raw projection.html shell bytes, or None for a pre-1.1.0
    # container that carries no shell. A DERIVED projection — never parse it
    # back as canonical; content_tiptap stays the source of truth.
    projection_html: bytes | None = None


# ── Public API ──


def read_antiek(data: bytes) -> ReadResult:
    """Parse and validate a `.antiek` file.

    Parameters
    ----------
    data : bytes
        The full archive bytes.

    Returns
    -------
    ReadResult

    Raises
    ------
    MalformedAntiek
        On zip structure problems (not a zip, missing required entries,
        unexpected entries on same-major version are warned, not raised).
    ManifestValidationError
        On schema validation failure.
    UnsupportedVersion
        On major-version mismatch.
    """
    try:
        zf = zipfile.ZipFile(BytesIO(data), mode="r")
    except zipfile.BadZipFile as e:
        raise MalformedAntiek(f"not a zip file: {e}") from e

    with zf:
        names = set(zf.namelist())
        for required in (ENTRY_MANIFEST, ENTRY_CONTENT, ENTRY_SIGNATURE):
            if required not in names:
                raise MalformedAntiek(
                    f"required entry {required!r} missing from .antiek "
                    f"(found: {sorted(names)})"
                )

        manifest_bytes = zf.read(ENTRY_MANIFEST)
        content_bytes = zf.read(ENTRY_CONTENT)
        edges_bytes = zf.read(ENTRY_EDGES) if ENTRY_EDGES in names else b""
        signature_bytes = zf.read(ENTRY_SIGNATURE)
        # SPR-04: the self-render shell is OPTIONAL (pre-1.1.0 containers
        # carry none). Read it if present; its integrity is checked below
        # against the signed manifest's projection_sha256.
        projection_bytes = (
            zf.read(ENTRY_PROJECTION) if ENTRY_PROJECTION in names else None
        )

        # Collect blocks/ entries.
        audio_blobs: dict[str, bytes] = {}
        for n in sorted(names):
            if n.startswith(BLOCKS_PREFIX) and n != BLOCKS_PREFIX:
                bid = _block_id_from_audio_path(n)
                if bid is not None:
                    audio_blobs[bid] = zf.read(n)
                else:
                    _log.warning(
                        "read_antiek: unrecognised entry under blocks/: %r — ignoring",
                        n,
                    )

        # Unknown entries (same-major): warn, ignore.
        known_prefixes = {
            ENTRY_MANIFEST,
            ENTRY_CONTENT,
            ENTRY_PROJECTION,
            ENTRY_EDGES,
            ENTRY_SIGNATURE,
        }
        for n in names:
            if n in known_prefixes:
                continue
            if n.startswith(BLOCKS_PREFIX):
                continue
            _log.warning(
                "read_antiek: unknown top-level entry %r — ignoring on "
                "same-major-version file. If this file is a different "
                "major version, UnsupportedVersion will fire first.",
                n,
            )

    # ── Parse + validate manifest ──

    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise MalformedAntiek(f"manifest.json is not UTF-8 JSON: {e}") from e

    _validate_manifest(manifest)

    file_version = manifest["schema_version"]
    _check_version_policy(file_version)

    # ── Parse content ──

    try:
        content_tiptap = json.loads(content_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise MalformedAntiek(f"content.tiptap.json is not UTF-8 JSON: {e}") from e

    # ── Parse edges ──

    edges: list[dict[str, Any]] = []
    if edges_bytes:
        for i, line in enumerate(edges_bytes.decode("utf-8").splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                edges.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise MalformedAntiek(
                    f"edges.jsonl line {i + 1} is not JSON: {e}"
                ) from e

    # ── Verify signature ──
    #
    # We RECOMPUTE the canonical bytes from the parsed objects rather
    # than re-using the on-disk bytes verbatim. That's the
    # belt-and-braces check: if a tampered file passes JSON parsing
    # but doesn't survive canonicalisation, the signature catches it.

    canon_manifest = canonical_json_bytes(manifest)
    canon_content = canonical_json_bytes(_canonical_tiptap_node(content_tiptap))
    canon_edges = canonical_edges_bytes(edges)
    signing_input = build_signing_input(
        manifest_bytes=canon_manifest,
        content_bytes=canon_content,
        edges_bytes=canon_edges,
    )

    signature_valid = verify_bytes(
        creator_pubkey_b64=manifest["creator_pubkey"],
        signing_input=signing_input,
        signature=signature_bytes,
    )

    # ── Per-audio integrity ──
    #
    # Hashes are inside the signed manifest, so a tampered audio file
    # is caught here without breaking the top-level signature scope.
    blocks_index = list(manifest.get("blocks_index") or [])
    for entry in blocks_index:
        if not isinstance(entry, dict):
            continue
        expected = entry.get("audio_sha256")
        path = entry.get("audio_path")
        if not (expected and path):
            continue
        bid = _block_id_from_audio_path(path)
        if bid is None:
            signature_valid = False
            _log.warning(
                "read_antiek: blocks_index references audio_path %r outside "
                "blocks/; treating as tampered.",
                path,
            )
            continue
        blob = audio_blobs.get(bid)
        if blob is None:
            signature_valid = False
            _log.warning(
                "read_antiek: blocks_index references block %r audio but no "
                "blob in archive; treating as tampered.",
                bid,
            )
            continue
        import hashlib
        actual = hashlib.sha256(blob).hexdigest()
        if actual != expected:
            signature_valid = False
            _log.warning(
                "read_antiek: block %r audio SHA-256 mismatch (expected %s, "
                "got %s); treating as tampered.",
                bid,
                expected,
                actual,
            )

    # ── Per-shell integrity (SPR-04) ──
    # Same mechanism as audio: the shell's sha256 is in the SIGNED manifest,
    # so a mutated shell is caught here (signature_valid -> False) without
    # widening the Ed25519 scope. A manifest that declares a projection_sha256
    # but ships no shell (or a mismatching one) is treated as tampered.
    expected_projection = manifest.get("projection_sha256")
    if expected_projection:
        if projection_bytes is None:
            signature_valid = False
            _log.warning(
                "read_antiek: manifest declares projection_sha256 but no "
                "projection.html entry is present; treating as tampered."
            )
        else:
            import hashlib

            actual_projection = hashlib.sha256(projection_bytes).hexdigest()
            if actual_projection != expected_projection:
                signature_valid = False
                _log.warning(
                    "read_antiek: projection.html SHA-256 mismatch (expected "
                    "%s, got %s); treating as tampered.",
                    expected_projection,
                    actual_projection,
                )

    # ── Surface unknown manifest keys ──
    known_top = {
        "schema_version", "content_class", "document_id", "parent_document_id",
        "created_at", "creator_user_id", "creator_pubkey",
        "title", "notebook_id", "format_version", "edges_present",
        "projection_sha256",
        "blocks_index",
    }
    unknown = {k: v for k, v in manifest.items() if k not in known_top}
    if unknown:
        _log.info(
            "read_antiek: preserving %d unknown manifest key(s): %s",
            len(unknown),
            sorted(unknown.keys()),
        )

    return ReadResult(
        schema_version=file_version,
        content_class=manifest["content_class"],
        document_id=manifest["document_id"],
        parent_document_id=manifest.get("parent_document_id"),
        notebook_id=manifest.get("notebook_id"),
        user_id=manifest["creator_user_id"],
        creator_pubkey=manifest["creator_pubkey"],
        title=manifest.get("title"),
        format_version=manifest.get("format_version"),
        created_at=manifest["created_at"],
        content_tiptap=content_tiptap,
        blocks_index=blocks_index,
        edges=edges,
        audio_blobs=audio_blobs,
        signature_valid=signature_valid,
        manifest_unknown_keys=unknown,
        projection_html=projection_bytes,
    )


# ── Round-trip identity helper ──


def canonical_tiptap_bytes(doc: dict[str, Any]) -> bytes:
    """Public helper for round-trip identity tests.

    Two TipTap docs are considered round-trip-equivalent iff their
    ``canonical_tiptap_bytes`` are byte-equal. This is more permissive
    than ``dict ==``: it drops null attrs, sorts marks, and ignores
    empty content arrays — all of which TipTap treats as equivalent.
    """
    return canonical_json_bytes(_canonical_tiptap_node(doc))


# ── Internals ──


def _block_id_from_audio_path(path: str) -> str | None:
    if not path.startswith(BLOCKS_PREFIX):
        return None
    tail = path[len(BLOCKS_PREFIX):]
    if not tail.endswith(".audio"):
        return None
    return tail[: -len(".audio")]


def _parse_semver(v: str) -> tuple[int, int, int]:
    parts = v.split(".")
    if len(parts) != 3:
        raise ManifestValidationError(
            f"schema_version {v!r} is not semver M.m.p"
        )
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError as e:
        raise ManifestValidationError(
            f"schema_version {v!r} has non-integer components: {e}"
        ) from e


def _check_version_policy(file_version: str) -> None:
    file_major, file_minor, _file_patch = _parse_semver(file_version)
    reader_major, reader_minor, _reader_patch = _parse_semver(SCHEMA_VERSION)
    if file_major != reader_major:
        raise UnsupportedVersion(
            f"read_antiek: file schema_version {file_version!r} major != "
            f"reader {SCHEMA_VERSION!r}. Reader refuses to parse; caller "
            f"may fall back to markdown projection."
        )
    if file_minor > reader_minor:
        _log.warning(
            "read_antiek: file schema_version %s minor > reader %s minor; "
            "unknown manifest keys are preserved on round-trip but unknown "
            "block types may render as prose. (SPEC.md §7)",
            file_version,
            SCHEMA_VERSION,
        )


def _validate_manifest(manifest: dict[str, Any]) -> None:
    """Validate against the checked-in JSON schema.

    Uses ``jsonschema`` if installed, falls back to a hand-rolled
    requirement check otherwise. We don't want a hard dep on
    jsonschema for the read path — every other consumer of this
    module already pulls in 5 things; adding a sixth for a 10-line
    validation isn't worth it. When jsonschema is available we use
    it (tighter validation); when it isn't, we still enforce the
    must-have invariants.
    """
    if not isinstance(manifest, dict):
        raise ManifestValidationError("manifest must be a JSON object")

    try:
        # jsonschema is an OPTIONAL tightener (manual fallback below);
        # installed without stubs in the gate env.
        import jsonschema  # type: ignore[import-untyped]
    except ImportError:
        _manual_validate_manifest(manifest)
        return

    with open(_SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)
    try:
        jsonschema.validate(manifest, schema)
    except jsonschema.ValidationError as e:
        raise ManifestValidationError(f"manifest schema validation: {e.message}") from e


def _manual_validate_manifest(manifest: dict[str, Any]) -> None:
    """Fallback validation when ``jsonschema`` isn't installed.

    Enforces the REQUIRED keys + the closed enum on ``content_class``
    + the semver-shape on ``schema_version``. Permissive on optional
    fields; this is the safety net, not the full validator.
    """
    required = [
        "schema_version", "content_class", "document_id", "parent_document_id",
        "created_at", "creator_user_id", "creator_pubkey",
    ]
    for k in required:
        if k not in manifest:
            raise ManifestValidationError(
                f"manifest missing required key {k!r}"
            )
    if manifest["content_class"] not in CONTENT_CLASSES:
        raise ManifestValidationError(
            f"manifest content_class {manifest['content_class']!r} not in "
            f"{sorted(CONTENT_CLASSES)}"
        )
    _parse_semver(manifest["schema_version"])  # raises ManifestValidationError on bad shape


__all__ = [
    "AntiekFormatError",
    "ManifestValidationError",
    "MalformedAntiek",
    "ReadResult",
    "UnsupportedVersion",
    "canonical_tiptap_bytes",
    "read_antiek",
]
