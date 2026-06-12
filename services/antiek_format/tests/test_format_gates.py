"""SPR-01 landing gates — each format gate proven GREEN **and** RED.

HTML-projection SPR-01 (M3). A gate that has only ever been green is
unproven: these tests pair every green path with a committed
seeded-poison fixture and an assertion that the gate actually turns
red on it. The three gates, per the sprint page's verification table:

1. **Determinism** (``-k determinism``)
   green: the same committed fixture written twice produces
   byte-identical containers (sha256-compared), and matches the
   COMMITTED container byte-for-byte.
   red:   ``fixtures/poison_wallclock.json`` (``created_at: null``)
   lets wall-clock time into the manifest — two writes at different
   instants produce different bytes, which the hash-compare detects.

2. **Signature** (``-k signature``)
   green: a freshly written container verifies; the committed clean
   container verifies.
   red:   ``fixtures/tampered_container.antiek`` — the committed clean
   container with ONE byte flipped inside ``content.tiptap.json``
   (a case-flip, so the JSON still parses) — fails verification. A
   dynamic single-byte tamper of a fresh container fails too.

3. **Forbidden substrate fields** (``-k forbidden``)
   green: the clean fixture's container greps clean against
   ``_FORBIDDEN_SUBSTRATE_FIELDS``.
   red:   ``fixtures/poison_embedding.json`` — an embedding vector
   smuggled into a highlight card's attrs — (a) the writer REFUSES to
   serialise it, and (b) a container built BYPASSING the writer's
   pre-flight is caught red by the byte-grep detection.

Fixture provenance (rigor #1 — honesty about regeneration)
-----------------------------------------------------------
The binary fixtures (``clean_container.antiek``,
``tampered_container.antiek``) and the pinned sha256 below were minted
once by running this module directly::

    .venv/bin/python -m services.antiek_format.tests.test_format_gates

from the repo root, using the all-zeros-plus-one TEST-ONLY signing seed
(``_GATE_SEED`` — a constant, not secret material; never use it outside
tests). If ``test_determinism_gate_green_*`` ever fails against the
committed bytes, the writer's byte-output has changed: that is a FORMAT
CHANGE, not a fixture refresh. Report it as one (it requires a
schema-version decision), do not silently re-mint.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from services.antiek_format import WriterInput, read_antiek, write_antiek
from services.antiek_format import native_writer as _native_writer_module
from services.antiek_format.native_writer import (
    _FORBIDDEN_SUBSTRATE_FIELDS,
    ENTRY_CONTENT,
    _build_deterministic_zip,
)
from services.antiek_format.signature import Keypair, canonical_json_bytes

FIXTURES = Path(__file__).parent / "fixtures"

# TEST-ONLY deterministic Ed25519 seed. A fixed public constant so the
# committed container fixtures are reproducible from source alone — no
# committed key material, nothing secret. NEVER use outside tests.
_GATE_SEED = b"\x01" * 32

# sha256 of fixtures/clean_container.antiek, pinned at mint time. If a
# fresh write of fixtures/clean_notebook.json stops matching this, the
# writer's byte-output changed => FORMAT CHANGE (see module docstring).
CLEAN_CONTAINER_SHA256 = (
    "6ed9e8d7a2e894ed4c96a11ebf5dbe2144426fc30d9ac2bf8bd8327743882c29"
)


def _gate_keypair() -> Keypair:
    sk = Ed25519PrivateKey.from_private_bytes(_GATE_SEED)
    return Keypair(
        user_id="user-gate-fixture",
        private_key=sk,
        public_key=sk.public_key(),
    )


def _load_writer_input(fixture_name: str) -> WriterInput:
    payload = json.loads((FIXTURES / fixture_name).read_text(encoding="utf-8"))
    created = payload.pop("created_at")
    return WriterInput(
        created_at=datetime.fromisoformat(created) if created else None,
        audio_blobs={},
        **payload,
    )


def _grep_forbidden_fields(container: bytes) -> list[str]:
    """The byte-grep detection from the M7 gate test
    (``test_no_substrate_data_in_file``), factored so the RED half can
    assert it fires: returns every forbidden field name found in any
    decompressed payload of ``container``."""
    payloads: list[bytes] = []
    with zipfile.ZipFile(io.BytesIO(container)) as zf:
        for info in zf.infolist():
            payloads.append(zf.read(info.filename))
    blob = b"\n".join(payloads)
    return [f for f in _FORBIDDEN_SUBSTRATE_FIELDS if f.encode("ascii") in blob]


def _tamper_one_byte(container: bytes) -> bytes:
    """Flip the case of one ASCII letter near the end of
    content.tiptap.json (JSON still parses; signed bytes change).
    Mirrors test_e2e.test_tamper_invalidates_signature."""
    with zipfile.ZipFile(io.BytesIO(container)) as zf:
        entries = []
        for info in zf.infolist():
            payload = zf.read(info.filename)
            if info.filename == ENTRY_CONTENT:
                arr = bytearray(payload)
                for i in range(len(arr) - 1, 0, -1):
                    c = arr[i]
                    if 65 <= c <= 90 or 97 <= c <= 122:
                        arr[i] ^= 0x20
                        break
                payload = bytes(arr)
            entries.append((info.filename, payload))
    return _build_deterministic_zip(entries)


# ── Gate 1: determinism ──────────────────────────────────────────────


def test_determinism_gate_green_double_write_byte_identical():
    """Same committed fixture written twice -> identical sha256, and the
    bytes match the COMMITTED container exactly (cross-run, cross-machine
    determinism — not just within-process)."""
    inp = _load_writer_input("clean_notebook.json")
    kp = _gate_keypair()
    a = write_antiek(inp, keypair=kp)
    b = write_antiek(inp, keypair=kp)
    assert hashlib.sha256(a).hexdigest() == hashlib.sha256(b).hexdigest()
    assert hashlib.sha256(a).hexdigest() == CLEAN_CONTAINER_SHA256, (
        "fresh write no longer matches the pinned fixture hash — the "
        "writer's byte-output CHANGED. That is a format change, not a "
        "fixture refresh; see module docstring before touching anything."
    )
    committed = (FIXTURES / "clean_container.antiek").read_bytes()
    assert a == committed


def test_determinism_gate_red_wallclock_injection(monkeypatch):
    """SEEDED POISON: fixtures/poison_wallclock.json carries
    ``created_at: null``, so the writer stamps now(). Simulate two write
    instants one second apart (deterministically, via monkeypatch) and
    assert the hash-compare gate goes RED — proof the gate can actually
    detect a wall-clock-injected container, not just bless green ones."""
    inp = _load_writer_input("poison_wallclock.json")
    assert inp.created_at is None  # the poison: wall-clock injection point
    kp = _gate_keypair()

    t0 = datetime(2026, 6, 12, 9, 0, 0, tzinfo=UTC)
    instants = [t0, t0 + timedelta(seconds=1)]

    class _WallClock:
        """Stand-in for native_writer's ``datetime`` symbol; each call
        to now() returns the next instant."""

        @staticmethod
        def now(tz):
            return instants.pop(0).astimezone(tz)

    monkeypatch.setattr(_native_writer_module, "datetime", _WallClock)
    a = write_antiek(inp, keypair=kp)
    b = write_antiek(inp, keypair=kp)
    assert hashlib.sha256(a).hexdigest() != hashlib.sha256(b).hexdigest(), (
        "determinism gate FAILED TO GO RED: two wall-clock writes "
        "produced identical bytes, so the hash-compare gate cannot "
        "detect timestamp nondeterminism"
    )


# ── Gate 2: signature ────────────────────────────────────────────────


def test_signature_gate_green_fresh_and_committed_verify():
    inp = _load_writer_input("clean_notebook.json")
    fresh = write_antiek(inp, keypair=_gate_keypair())
    assert read_antiek(fresh).signature_valid is True
    committed = (FIXTURES / "clean_container.antiek").read_bytes()
    assert read_antiek(committed).signature_valid is True


def test_signature_gate_red_committed_tampered_container():
    """SEEDED POISON: fixtures/tampered_container.antiek is the committed
    clean container with one byte flipped inside content.tiptap.json."""
    tampered = (FIXTURES / "tampered_container.antiek").read_bytes()
    clean = (FIXTURES / "clean_container.antiek").read_bytes()
    assert tampered != clean
    assert len(tampered) == len(clean)  # single-byte flip, not a rewrite
    assert read_antiek(tampered).signature_valid is False, (
        "signature gate FAILED TO GO RED on the committed tampered fixture"
    )


def test_signature_gate_red_single_byte_tamper_of_fresh_container():
    inp = _load_writer_input("clean_notebook.json")
    fresh = write_antiek(inp, keypair=_gate_keypair())
    assert read_antiek(_tamper_one_byte(fresh)).signature_valid is False


# ── Gate 3: forbidden substrate fields ───────────────────────────────


def test_forbidden_fields_gate_green_clean_fixture():
    inp = _load_writer_input("clean_notebook.json")
    container = write_antiek(inp, keypair=_gate_keypair())
    assert _grep_forbidden_fields(container) == []


def test_forbidden_fields_gate_red_writer_refuses_smuggled_embedding():
    """SEEDED POISON: fixtures/poison_embedding.json smuggles an
    ``embedding`` vector into a highlight card's attrs. The writer must
    REFUSE (not silently strip)."""
    inp = _load_writer_input("poison_embedding.json")
    with pytest.raises(ValueError, match="forbidden substrate-derived field"):
        write_antiek(inp, keypair=_gate_keypair())


def test_forbidden_fields_gate_red_bytegrep_detects_bypassed_poison():
    """Defence in depth: build a container BYPASSING the writer's
    pre-flight (straight to the deterministic zip builder) with the
    poisoned payload, and assert the byte-grep detection turns RED —
    proof the grep gate itself can fail, independent of the writer."""
    payload = json.loads(
        (FIXTURES / "poison_embedding.json").read_text(encoding="utf-8")
    )
    poisoned = _build_deterministic_zip(
        [
            ("manifest.json", canonical_json_bytes({"smuggled": True})),
            (ENTRY_CONTENT, canonical_json_bytes(payload["content_tiptap"])),
            ("signature.bin", b"\x00" * 64),
        ]
    )
    found = _grep_forbidden_fields(poisoned)
    assert "embedding" in found, (
        "forbidden-fields gate FAILED TO GO RED: the byte-grep did not "
        "detect the embedding vector smuggled past the writer"
    )


# ── Fixture minting (run directly; see module docstring) ─────────────


def _mint_fixtures() -> None:
    inp = _load_writer_input("clean_notebook.json")
    clean = write_antiek(inp, keypair=_gate_keypair())
    (FIXTURES / "clean_container.antiek").write_bytes(clean)
    (FIXTURES / "tampered_container.antiek").write_bytes(_tamper_one_byte(clean))
    print(f"clean_container.antiek    sha256 {hashlib.sha256(clean).hexdigest()}")
    print("tampered_container.antiek minted (one byte flipped in content)")
    print("Update CLEAN_CONTAINER_SHA256 if (and only if) this is a deliberate format change.")


if __name__ == "__main__":
    _mint_fixtures()
