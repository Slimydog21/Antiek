"""BYO-tools paste-a-key chassis tests (spec §5.0/§5.1, sprint S1).

The invariants, each asserted for real (rigor #3 — every guard ships a test
that would fail on a violating change):

  (a) STORE, NOT PLAINTEXT. ``attach_key`` seals the key in the byok store and
      the connector holds ONLY the non-secret ``cred_id``; the raw artifact
      bytes never contain the key.
  (b) SHAPE-VALIDATE WITHOUT ECHO. A malformed key is rejected BEFORE storing,
      and the rejection message never contains the submitted key substring
      (the settings_models_admin 422 bar — a byte assertion, not a vibe).
  (c) CALL-TIME RESOLUTION. The plaintext is decrypted only via
      ``_resolve_key()`` at the send seam, wrapped in a redacting
      ``SecretStr``; ``str()``/``repr()`` of everything on the connector
      redact.
  (d) LIST WITHOUT DECRYPTING. ``key_present()`` answers from non-secret
      metadata — proven by monkeypatching ``load_credential`` to explode and
      observing it never fires.
  (e) KEYLESS IS THE DEGENERATE CASE. A ``key_shape=None`` connector (EDGAR's
      shape) stores nothing, resolves None, and refuses ``attach_key``.

All offline: a test-injected 32-byte key + temp artifact (the
``test_byok_store.py`` posture), zero network.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

import nacl.secret  # noqa: E402
import pytest  # noqa: E402

import runtime.connectors.base as chassis  # noqa: E402
from runtime.byok.secret_str import SecretStr  # noqa: E402
from runtime.byok.store import list_credentials, load_credential  # noqa: E402
from runtime.connectors.base import (  # noqa: E402
    ConnectorDescriptor,
    KeyShape,
    KeyShapeError,
    PasteKeyConnector,
)

_TEST_KEY_BYTES = b"0" * nacl.secret.SecretBox.KEY_SIZE  # 32 bytes, test-injected
_SECRET = "tv-super-secret-vendor-key-0123456789abcdef"
_BAD_SECRET = "zz-this-key-is-not-the-right-shape-0000000000000000"


class _FakeVendorConnector(PasteKeyConnector):
    """A test-local concrete paste-a-key connector (chassis exercise only —
    NOT a catalog vendor)."""

    descriptor = ConnectorDescriptor(
        vendor="testvendor",
        chassis="paste_key",
        auth="bearer_token",
        key_shape=KeyShape(min_len=8, max_len=64, prefix="tv-"),
        rate=None,
        docs_url="https://example.com/testvendor-keys",
    )


class _KeylessConnector(PasteKeyConnector):
    """The keyless degenerate case (EDGAR's chassis shape)."""

    descriptor = ConnectorDescriptor(
        vendor="keylessvendor",
        chassis="paste_key",
        auth="none",
        key_shape=None,
        rate=None,
        docs_url="https://example.com/keyless",
    )


@pytest.fixture
def artifact(tmp_path: Path) -> str:
    return str(tmp_path / "byok_artifact.json")


def _connector(artifact: str) -> _FakeVendorConnector:
    return _FakeVendorConnector(artifact_path=artifact, key_bytes=_TEST_KEY_BYTES)


# ── (a) attach stores; the connector holds only the cred_id ──────────────


def test_attach_key_roundtrips_through_the_store(artifact: str) -> None:
    conn = _connector(artifact)
    cred_id = conn.attach_key(_SECRET)
    assert conn.cred_id == cred_id
    resolved = conn._resolve_key()
    assert isinstance(resolved, SecretStr)
    assert resolved.reveal() == _SECRET


def test_attach_key_stores_under_connector_pipeline_kind(artifact: str) -> None:
    conn = _connector(artifact)
    cred_id = conn.attach_key(_SECRET)
    metas = list_credentials(artifact_path=artifact)
    assert [m.cred_id for m in metas] == [cred_id]
    assert metas[0].pipeline_kind == "connector_testvendor"
    assert metas[0].account_handle == "connector-testvendor"


def test_raw_artifact_has_no_plaintext_key(artifact: str) -> None:
    conn = _connector(artifact)
    conn.attach_key(_SECRET)
    raw = Path(artifact).read_bytes()
    assert _SECRET.encode() not in raw


# ── (b) shape validation rejects before storing, and never echoes ─────────


@pytest.mark.parametrize(
    "bad",
    [
        "tv-shrt",  # 7 chars — below min_len 8
        "tv-" + "x" * 100,  # above max_len
        _BAD_SECRET,  # wrong prefix class
        "",  # empty
    ],
)
def test_attach_key_rejects_bad_shapes(artifact: str, bad: str) -> None:
    conn = _connector(artifact)
    with pytest.raises(KeyShapeError):
        conn.attach_key(bad)
    assert conn.cred_id is None
    assert list_credentials(artifact_path=artifact) == []


def test_shape_error_never_echoes_the_key(artifact: str) -> None:
    conn = _connector(artifact)
    with pytest.raises(KeyShapeError) as excinfo:
        conn.attach_key(_BAD_SECRET)
    rendered = str(excinfo.value) + repr(excinfo.value)
    assert _BAD_SECRET not in rendered


def test_length_error_names_the_range_not_the_value(artifact: str) -> None:
    conn = _connector(artifact)
    with pytest.raises(KeyShapeError) as excinfo:
        conn.attach_key("tv-" + "x" * 100)
    message = str(excinfo.value)
    assert "8-64" in message
    assert "x" * 20 not in message


# ── (c) redaction: nothing on the connector stringifies to the key ────────


def test_connector_repr_is_descriptor_only(artifact: str) -> None:
    conn = _connector(artifact)
    conn.attach_key(_SECRET)
    rendered = repr(conn) + str(conn)
    assert _SECRET not in rendered
    assert "testvendor" in rendered


def test_resolved_key_is_a_redacting_secretstr(artifact: str) -> None:
    conn = _connector(artifact)
    conn.attach_key(_SECRET)
    resolved = conn._resolve_key()
    assert resolved is not None
    assert str(resolved) != _SECRET
    assert _SECRET not in str(resolved) + repr(resolved)


def test_unknown_cred_id_raises_keyerror(artifact: str) -> None:
    conn = _FakeVendorConnector(
        cred_id="cred-x-does-not-exist",
        artifact_path=artifact,
        key_bytes=_TEST_KEY_BYTES,
    )
    with pytest.raises(KeyError):
        conn._resolve_key()


# ── (d) key_present lists without decrypting ──────────────────────────────


def test_key_present_never_decrypts(artifact: str, monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _connector(artifact)
    conn.attach_key(_SECRET)

    def _explode(*args: object, **kwargs: object) -> SecretStr:
        raise AssertionError("load_credential must not be called by key_present")

    monkeypatch.setattr(chassis, "load_credential", _explode)
    assert conn.key_present() is True


def test_key_present_false_for_unknown_cred_id(artifact: str) -> None:
    conn = _FakeVendorConnector(
        cred_id="cred-x-nope", artifact_path=artifact, key_bytes=_TEST_KEY_BYTES
    )
    assert conn.key_present() is False


# ── (e) the keyless degenerate case ───────────────────────────────────────


def test_keyless_connector_stores_and_resolves_nothing(artifact: str) -> None:
    conn = _KeylessConnector(artifact_path=artifact, key_bytes=_TEST_KEY_BYTES)
    assert conn.cred_id is None
    assert conn.key_present() is False
    assert conn._resolve_key() is None
    assert list_credentials(artifact_path=artifact) == []


def test_keyless_connector_refuses_attach_key(artifact: str) -> None:
    conn = _KeylessConnector(artifact_path=artifact, key_bytes=_TEST_KEY_BYTES)
    with pytest.raises(KeyShapeError):
        conn.attach_key(_SECRET)
    assert conn.cred_id is None


def test_load_credential_roundtrip_matches_store_directly(artifact: str) -> None:
    """The chassis's resolution path and the raw store agree on the plaintext
    (the one place a test MAY compare revealed values — equality, not print)."""
    conn = _connector(artifact)
    cred_id = conn.attach_key(_SECRET)
    direct = load_credential(cred_id, artifact_path=artifact, key_bytes=_TEST_KEY_BYTES)
    assert conn._resolve_key() == direct
