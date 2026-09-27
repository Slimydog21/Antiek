"""Format reads while the same process holds a DuckDB write handle."""

from __future__ import annotations

from pathlib import Path

from runtime.db_lock import connect_write
from services.antiek_format.signature import ensure_keypair


def test_keypair_read_with_local_writer_open(tmp_path: Path) -> None:
    db_path = str(tmp_path / "format-read-coexistence.duckdb")
    original = ensure_keypair("user-A", db_path=db_path)

    with connect_write(db_path, purpose="format-keypair-read-test"):
        loaded = ensure_keypair("user-A", db_path=db_path)
        assert loaded.private_key_b64 == original.private_key_b64
        assert loaded.public_key_b64 == original.public_key_b64

    assert (
        ensure_keypair("user-A", db_path=db_path).public_key_b64
        == original.public_key_b64
    )
