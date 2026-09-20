from __future__ import annotations

import hashlib
import hmac
import json
import os
import struct
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from runtime.db_lock import connect_write
from substrate.multimedia.artifact_quarantine import (
    ArtifactQuarantineError,
    ArtifactQuarantineReceipt,
    TransportResponse,
    quarantine_artifact,
)

KEY = b"artifact-quarantine-test-signing-key"
NOW = datetime(2026, 7, 11, tzinfo=UTC)


def _png(width: int = 1, height: int = 1) -> bytes:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    scanline = zlib.compress(b"\x00\x00\x00\x00\x00" * height)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", scanline)
        + chunk(b"IEND", b"")
    )


def _jpeg(width: int = 1, height: int = 1) -> bytes:
    sof = b"\x08" + struct.pack(">HH", height, width) + b"\x01\x01\x11\x00"
    sos = b"\x01\x01\x00\x00\x3f\x00"
    return (
        b"\xff\xd8\xff\xc0"
        + struct.pack(">H", len(sof) + 2)
        + sof
        + b"\xff\xda"
        + struct.pack(">H", len(sos) + 2)
        + sos
        + b"\x00\xff\xd9"
    )


def _mp4(duration: int = 60, timescale: int = 1) -> bytes:
    def box(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload) + 8) + kind + payload

    mvhd = box(b"mvhd", b"\x00\x00\x00\x00" + b"\x00" * 8 + struct.pack(">II", timescale, duration))
    return box(b"ftyp", b"isom\x00\x00\x02\x00isom") + box(b"moov", mvhd) + box(b"mdat", b"\x00")


PNG = _png()


@dataclass
class FakeResolver:
    answers: tuple[str, ...]

    def resolve(self, hostname: str) -> tuple[str, ...]:
        assert hostname == "cdn.example.test"
        return self.answers


@dataclass
class FakeTransport:
    response: TransportResponse
    calls: int = 0

    def get(self, **kwargs: object) -> TransportResponse:
        self.calls += 1
        assert kwargs["tls_hostname"] == "cdn.example.test"
        return self.response


def _call(
    tmp_path: Path, resolver: FakeResolver, transport: FakeTransport, **kwargs: object
) -> ArtifactQuarantineReceipt:
    db_path = str(tmp_path / "db.duckdb")
    _seed_candidate(db_path, "exec", "candidate", "https://cdn.example.test/a.png")
    return quarantine_artifact(
        db_path=db_path,
        execution_id="exec",
        candidate_id="candidate",
        url="https://cdn.example.test/a.png",
        allowlisted_hosts=frozenset({"cdn.example.test"}),
        resolver=resolver,
        transport=transport,
        quarantine_dir=str(tmp_path / "quarantine"),
        signing_key=KEY,
        now=NOW,
        **kwargs,
    )


def _seed_candidate(db_path: str, execution_id: str, candidate_id: str, url: str) -> None:
    values: list[object] = [
        candidate_id,
        execution_id,
        0,
        hashlib.sha256(url.encode()).hexdigest(),
        "unknown",
    ]
    payload = json.dumps(values, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    mac = hmac.new(KEY, payload, hashlib.sha256).hexdigest()
    with connect_write(db_path, purpose="test.seed_artifact_candidate") as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS multimedia_provider_artifact_candidates ("
            "candidate_id TEXT PRIMARY KEY, execution_id TEXT NOT NULL, ordinal INTEGER NOT NULL, "
            "source_locator_digest TEXT NOT NULL, declared_media_type TEXT NOT NULL, "
            "candidate_mac TEXT NOT NULL, UNIQUE(execution_id, ordinal))"
        )
        connection.execute(
            "INSERT INTO multimedia_provider_artifact_candidates VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT DO NOTHING",
            [*values, mac],
        )


@pytest.mark.parametrize(
    "answers",
    [
        ("127.0.0.1",),
        ("10.0.0.1",),
        ("169.254.1.1",),
        ("224.0.0.1",),
        ("192.0.2.1",),
        ("0.0.0.0",),
        ("8.8.8.8", "127.0.0.1"),
        ("8.8.8.8", "2001:4860:4860::8888"),
    ],
)
def test_rejects_ssrf_and_mixed_dns_before_transport(
    tmp_path: Path, answers: tuple[str, ...]
) -> None:
    transport = FakeTransport(TransportResponse(200, {}, "8.8.8.8", [PNG]))
    with pytest.raises(ArtifactQuarantineError):
        _call(tmp_path, FakeResolver(answers), transport)
    assert transport.calls == 0


@pytest.mark.parametrize(
    "response",
    [
        TransportResponse(302, {"Location": "https://elsewhere/a"}, "8.8.8.8", []),
        TransportResponse(200, {"Content-Type": "image/png"}, "1.1.1.1", [PNG]),
        TransportResponse(200, {"Content-Type": "text/html"}, "8.8.8.8", [PNG]),
        TransportResponse(200, {"Content-Type": "image/png"}, "8.8.8.8", [b"truncated"]),
    ],
)
def test_rejects_redirect_rebind_mime_and_truncation(
    tmp_path: Path, response: TransportResponse
) -> None:
    with pytest.raises(ArtifactQuarantineError):
        _call(tmp_path, FakeResolver(("8.8.8.8",)), FakeTransport(response))


def test_bounded_quarantine_receipt_and_expiry(tmp_path: Path) -> None:
    transport = FakeTransport(
        TransportResponse(
            200, {"Content-Type": "image/png", "Content-Length": str(len(PNG))}, "8.8.8.8", [PNG]
        )
    )
    receipt = _call(tmp_path, FakeResolver(("8.8.8.8",)), transport)
    assert Path(receipt.quarantine_path).read_bytes() == PNG
    assert receipt.sha256
    assert _call(tmp_path, FakeResolver(("8.8.8.8",)), transport) == receipt
    assert (
        _call(
            tmp_path,
            FakeResolver(("8.8.8.8",)),
            transport,
            expires_at=NOW - timedelta(seconds=1),
        )
        == receipt
    )


def test_rejects_non_private_and_symlink_quarantine_roots(tmp_path: Path) -> None:
    transport = FakeTransport(
        TransportResponse(200, {"Content-Type": "image/png"}, "8.8.8.8", [PNG])
    )
    public = tmp_path / "quarantine"
    public.mkdir(mode=0o755)
    with pytest.raises(ArtifactQuarantineError, match="directory"):
        _call(tmp_path, FakeResolver(("8.8.8.8",)), transport)
    public.rmdir()
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    public.symlink_to(target, target_is_directory=True)
    with pytest.raises(ArtifactQuarantineError, match="directory"):
        _call(tmp_path, FakeResolver(("8.8.8.8",)), transport)


@pytest.mark.parametrize(
    ("media_type", "payload", "suffix"),
    [("image/png", PNG, "png"), ("image/jpeg", _jpeg(), "jpg"), ("video/mp4", _mp4(), "mp4")],
)
def test_real_valid_media_fixtures(
    tmp_path: Path, media_type: str, payload: bytes, suffix: str
) -> None:
    db_path = str(tmp_path / f"valid-{suffix}.duckdb")
    url = f"https://cdn.example.test/a.{suffix}"
    _seed_candidate(db_path, "exec", f"candidate-{suffix}", url)
    receipt = quarantine_artifact(
        db_path=db_path,
        execution_id="exec",
        candidate_id=f"candidate-{suffix}",
        url=url,
        allowlisted_hosts=frozenset({"cdn.example.test"}),
        resolver=FakeResolver(("8.8.8.8",)),
        transport=FakeTransport(
            TransportResponse(200, {"Content-Type": media_type}, "8.8.8.8", [payload])
        ),
        quarantine_dir=str(tmp_path / "quarantine"),
        signing_key=KEY,
        now=NOW,
    )
    assert receipt.byte_count == len(payload)


@pytest.mark.parametrize(
    ("media_type", "payload"),
    [
        ("image/png", PNG[:-1]),
        ("image/png", _png(100_000, 100_000)),
        ("image/jpeg", _jpeg()[:-2]),
        ("image/jpeg", _jpeg(20_000, 20_000)),
        ("video/mp4", _mp4()[:-1]),
        ("video/mp4", _mp4(duration=21_601)),
        ("video/mp4", struct.pack(">I", 99) + b"ftyp" + b"x"),
    ],
)
def test_rejects_malformed_dimension_pixel_box_and_duration_bombs(
    tmp_path: Path, media_type: str, payload: bytes
) -> None:
    db_path = str(tmp_path / (hashlib.sha256(payload).hexdigest() + ".duckdb"))
    url = "https://cdn.example.test/bomb"
    _seed_candidate(db_path, "exec", "candidate", url)
    with pytest.raises(ArtifactQuarantineError):
        quarantine_artifact(
            db_path=db_path,
            execution_id="exec",
            candidate_id="candidate",
            url=url,
            allowlisted_hosts=frozenset({"cdn.example.test"}),
            resolver=FakeResolver(("8.8.8.8",)),
            transport=FakeTransport(
                TransportResponse(200, {"Content-Type": media_type}, "8.8.8.8", [payload])
            ),
            quarantine_dir=str(tmp_path / "quarantine"),
            signing_key=KEY,
            now=NOW,
        )


def test_receipt_replay_rejects_missing_corrupt_and_public_mode_file(tmp_path: Path) -> None:
    transport = FakeTransport(
        TransportResponse(200, {"Content-Type": "image/png"}, "8.8.8.8", [PNG])
    )
    receipt = _call(tmp_path, FakeResolver(("8.8.8.8",)), transport)
    path = Path(receipt.quarantine_path)
    path.unlink()
    with pytest.raises(ArtifactQuarantineError, match="receipt file"):
        _call(tmp_path, FakeResolver(("8.8.8.8",)), transport)
    path.write_bytes(b"corrupt")
    os.chmod(path, 0o600)
    with pytest.raises(ArtifactQuarantineError, match="receipt file"):
        _call(tmp_path, FakeResolver(("8.8.8.8",)), transport)
    path.write_bytes(PNG)
    os.chmod(path, 0o644)
    with pytest.raises(ArtifactQuarantineError, match="receipt file"):
        _call(tmp_path, FakeResolver(("8.8.8.8",)), transport)


def test_file_before_db_crash_is_recoverable_and_idempotent(tmp_path: Path) -> None:
    resolver = FakeResolver(("8.8.8.8",))
    transport = FakeTransport(
        TransportResponse(200, {"Content-Type": "image/png"}, "8.8.8.8", [PNG])
    )
    with pytest.raises(RuntimeError, match="injected"):
        _call(
            tmp_path,
            resolver,
            transport,
            after_replace=lambda: (_ for _ in ()).throw(RuntimeError("injected")),
        )
    receipt = _call(tmp_path, resolver, transport)
    assert Path(receipt.quarantine_path).read_bytes() == PNG


def test_candidate_row_tamper_fails_before_network(tmp_path: Path) -> None:
    db_path = str(tmp_path / "tamper.duckdb")
    url = "https://cdn.example.test/a.png"
    _seed_candidate(db_path, "exec", "candidate", url)
    with connect_write(db_path, purpose="test.tamper") as connection:
        connection.execute("UPDATE multimedia_provider_artifact_candidates SET ordinal=9")
    transport = FakeTransport(
        TransportResponse(200, {"Content-Type": "image/png"}, "8.8.8.8", [PNG])
    )
    with pytest.raises(ArtifactQuarantineError, match="binding"):
        quarantine_artifact(
            db_path=db_path,
            execution_id="exec",
            candidate_id="candidate",
            url=url,
            allowlisted_hosts=frozenset({"cdn.example.test"}),
            resolver=FakeResolver(("8.8.8.8",)),
            transport=transport,
            quarantine_dir=str(tmp_path / "q"),
            signing_key=KEY,
            now=NOW,
        )
    assert transport.calls == 0


def test_expired_candidate_is_unavailable_before_first_fetch(tmp_path: Path) -> None:
    db_path = str(tmp_path / "expired.duckdb")
    url = "https://cdn.example.test/a.png"
    _seed_candidate(db_path, "exec", "expired-candidate", url)
    transport = FakeTransport(
        TransportResponse(
            200, {"Content-Type": "image/png", "Content-Length": str(len(PNG))}, "8.8.8.8", [PNG]
        )
    )
    with pytest.raises(ArtifactQuarantineError, match="expired"):
        quarantine_artifact(
            db_path=db_path,
            execution_id="exec",
            candidate_id="expired-candidate",
            url=url,
            allowlisted_hosts=frozenset({"cdn.example.test"}),
            resolver=FakeResolver(("8.8.8.8",)),
            transport=transport,
            quarantine_dir=str(tmp_path / "quarantine"),
            signing_key=KEY,
            now=NOW,
            expires_at=NOW - timedelta(seconds=1),
        )
    assert transport.calls == 0


def test_candidate_binding_is_required_before_network(tmp_path: Path) -> None:
    db_path = str(tmp_path / "unbound.duckdb")
    transport = FakeTransport(
        TransportResponse(200, {"Content-Type": "image/png"}, "8.8.8.8", [PNG])
    )
    with pytest.raises(ArtifactQuarantineError, match="candidate"):
        quarantine_artifact(
            db_path=db_path,
            execution_id="exec",
            candidate_id="forged",
            url="https://cdn.example.test/a.png",
            allowlisted_hosts=frozenset({"cdn.example.test"}),
            resolver=FakeResolver(("8.8.8.8",)),
            transport=transport,
            quarantine_dir=str(tmp_path / "quarantine"),
            signing_key=KEY,
            now=NOW,
        )
    assert transport.calls == 0
