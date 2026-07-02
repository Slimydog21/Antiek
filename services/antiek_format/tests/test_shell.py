"""SPR-04: the .antiek self-render shell — adversarial gates.

The sprint's harness hint puts the energy in the verifier lenses, not in
fan-out. These prove, mechanically:

- M2: the shell rides in deterministic position, the format version bumped,
  byte-identical writes are preserved, and a pre-shell (1.0.0) container
  still reads.
- M3: the Ed25519 signature covers the shell — a single mutated shell byte,
  a removed shell with a claimed hash, and a mutated manifest hash each fail
  verification.
- M4: the forbidden-substrate byte-grep bites on HTML (attribute, comment,
  embedding float array) at write time, without false-positiving on prose.
"""

from __future__ import annotations

import dataclasses
import io
import json
import zipfile

import pytest

from services.antiek_format.native_reader import read_antiek
from services.antiek_format.native_writer import (
    ENTRY_CONTENT,
    ENTRY_MANIFEST,
    ENTRY_PROJECTION,
    ENTRY_SIGNATURE,
    _assert_no_forbidden_bytes,
    _build_deterministic_zip,
    _canonical_tiptap_node,
    write_antiek,
)
from services.antiek_format.signature import (
    build_signing_input,
    canonical_edges_bytes,
    canonical_json_bytes,
    sign_bytes,
)


def _entries(data: bytes) -> list[tuple[str, bytes]]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return [(n, zf.read(n)) for n in zf.namelist()]


def _names(data: bytes) -> list[str]:
    return [n for n, _ in _entries(data)]


def _read(data: bytes, name: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return zf.read(name)


# ── M2: shell entry, version bump, determinism, pre-shell read ──


def test_shell_present_in_deterministic_order(simple_notebook_input, keypair):
    names = _names(write_antiek(simple_notebook_input, keypair=keypair))
    assert ENTRY_PROJECTION in names
    assert names[0] == ENTRY_MANIFEST
    assert names[1] == ENTRY_CONTENT
    assert names[2] == ENTRY_PROJECTION  # right after the content it derives from
    assert names[-1] == ENTRY_SIGNATURE  # signature stays last


def test_version_bumped_and_hash_stamped(simple_notebook_input, keypair):
    manifest = json.loads(
        _read(write_antiek(simple_notebook_input, keypair=keypair), ENTRY_MANIFEST)
    )
    assert manifest["schema_version"] == "1.1.0"
    assert len(manifest["projection_sha256"]) == 64


def test_shell_write_is_byte_deterministic(simple_notebook_input, keypair):
    a = write_antiek(simple_notebook_input, keypair=keypair)
    b = write_antiek(simple_notebook_input, keypair=keypair)
    assert a == b


def test_shell_round_trips_and_verifies(simple_notebook_input, keypair):
    result = read_antiek(write_antiek(simple_notebook_input, keypair=keypair))
    assert result.signature_valid is True
    assert result.projection_html is not None
    assert result.projection_html.startswith(b"<!DOCTYPE html>")
    assert result.schema_version == "1.1.0"


def test_shell_is_gate_clean(simple_notebook_input, keypair):
    from services.html_projection.gate import assert_script_free

    shell = _read(
        write_antiek(simple_notebook_input, keypair=keypair), ENTRY_PROJECTION
    ).decode("utf-8")
    assert_script_free(shell)  # raises ScriptViolation on any violation


def test_pre_shell_container_still_reads(simple_notebook_input, keypair):
    # A hand-built 1.0.0 container: no projection.html, manifest without
    # projection_sha256, signed over manifest+content+edges (the pre-SPR-04
    # shape). The new reader must still verify it and report no shell.
    inp = simple_notebook_input
    content_bytes = canonical_json_bytes(_canonical_tiptap_node(inp.content_tiptap))
    edges_bytes = canonical_edges_bytes(inp.edges)
    manifest = {
        "schema_version": "1.0.0",
        "content_class": inp.content_class,
        "document_id": inp.document_id,
        "parent_document_id": inp.parent_document_id,
        "created_at": "2026-05-21T12:00:00+00:00",
        "creator_user_id": inp.user_id,
        "creator_pubkey": keypair.public_key_b64,
        "notebook_id": inp.notebook_id,
        "title": inp.title,
        "format_version": inp.format_version,
        "edges_present": bool(inp.edges),
        "blocks_index": [],
    }
    manifest_bytes = canonical_json_bytes(manifest)
    sig = sign_bytes(
        keypair,
        build_signing_input(
            manifest_bytes=manifest_bytes,
            content_bytes=content_bytes,
            edges_bytes=edges_bytes,
        ),
    )
    entries = [(ENTRY_MANIFEST, manifest_bytes), (ENTRY_CONTENT, content_bytes)]
    if edges_bytes:
        entries.append(("edges.jsonl", edges_bytes))
    entries.append((ENTRY_SIGNATURE, sig))
    result = read_antiek(_build_deterministic_zip(entries))
    assert result.signature_valid is True
    assert result.projection_html is None
    assert result.schema_version == "1.0.0"


# ── M3: signature coverage of the shell ──


def test_mutated_shell_byte_fails_verification(simple_notebook_input, keypair):
    entries = _entries(write_antiek(simple_notebook_input, keypair=keypair))
    tampered = []
    for name, payload in entries:
        if name == ENTRY_PROJECTION:
            mut = bytearray(payload)
            mut[len(mut) // 2] ^= 0x20  # flip a bit in the shell
            payload = bytes(mut)
        tampered.append((name, payload))
    assert read_antiek(_build_deterministic_zip(tampered)).signature_valid is False


def test_removed_shell_with_claimed_hash_fails(simple_notebook_input, keypair):
    # Attacker swaps the shell out of the signed set: drop projection.html
    # but keep the manifest's projection_sha256.
    entries = [
        (n, p)
        for n, p in _entries(write_antiek(simple_notebook_input, keypair=keypair))
        if n != ENTRY_PROJECTION
    ]
    assert read_antiek(_build_deterministic_zip(entries)).signature_valid is False


def test_mutated_manifest_hash_fails(simple_notebook_input, keypair):
    # Mutating projection_sha256 changes the signed manifest bytes, so the
    # top-level Ed25519 signature no longer verifies.
    entries = []
    for name, payload in _entries(write_antiek(simple_notebook_input, keypair=keypair)):
        if name == ENTRY_MANIFEST:
            m = json.loads(payload)
            m["projection_sha256"] = "0" * 64
            payload = canonical_json_bytes(m)
        entries.append((name, payload))
    assert read_antiek(_build_deterministic_zip(entries)).signature_valid is False


# ── M4: forbidden-substrate byte-grep over the HTML shell ──


def test_byte_grep_catches_each_placement():
    floats = ", ".join(f"{i / 100:.4f}" for i in range(20))  # 20 inline floats
    poisons = [
        b'<div data-embedding="x">y</div>',  # forbidden name as attribute
        b"<!-- chunk_id: leaked-abc -->",  # forbidden name in a comment
        f'<span data-x="[{floats}]"></span>'.encode(),  # embedding float array
    ]
    for p in poisons:
        with pytest.raises(ValueError):
            _assert_no_forbidden_bytes(p, where=ENTRY_PROJECTION)


def test_byte_grep_no_false_positive_on_prose():
    # Prose that merely MENTIONS the terms (no structural :/= after the token,
    # no float array) must pass — the gate bites on leaks, not on writing.
    clean = (
        b"<p>Word embeddings are useful; the document chunks into pieces "
        b"and attribution matters more than any reward.</p>"
    )
    _assert_no_forbidden_bytes(clean, where=ENTRY_PROJECTION)  # no raise


def test_poisoned_doc_model_raises_at_write_via_shell(simple_notebook_input, keypair):
    # A forbidden token in a TEXT VALUE (not a key) passes the JSON key check
    # but is caught by the shell byte-grep at write time — proving the grep
    # runs over the generated HTML, before bytes hit disk.
    poisoned = dataclasses.replace(
        simple_notebook_input,
        content_tiptap={
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "leak chunk_id: abc-123"}],
                }
            ],
        },
    )
    with pytest.raises(ValueError) as ei:
        write_antiek(poisoned, keypair=keypair)
    assert ENTRY_PROJECTION in str(ei.value)  # the SHELL grep, not the key check
