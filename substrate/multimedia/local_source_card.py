"""Deterministic graph-grounded source-card PNGs for zero-network documentaries."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
import tempfile
import textwrap
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from PIL import __version__ as pillow_version

from runtime.db_lock import FlockWriteCoordinator, connect_read

from .diagram_evidence_authority import DiagramAttestation, attest_diagram
from .visual_selection import ReviewedVisualSelection

DatabaseRow = tuple[object, ...]

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_CHUNKS = 16
_MAX_TEXT_BYTES = 1024 * 1024
_MAX_CARD_BYTES = 16 * 1024 * 1024
_RENDERER_VERSION = f"antiek.source-card.v1+pillow-{pillow_version}"

_DDL = """
CREATE TABLE IF NOT EXISTS multimedia_local_source_cards (
 card_id TEXT PRIMARY KEY, owner_identity_digest TEXT NOT NULL,
 asset_id TEXT NOT NULL, revision_id TEXT NOT NULL, chapter_id TEXT NOT NULL,
 scene_id TEXT NOT NULL, input_digest TEXT NOT NULL, snapshot_digest TEXT NOT NULL,
 renderer_version TEXT NOT NULL, font_digest TEXT NOT NULL,
 width_px INTEGER NOT NULL, height_px INTEGER NOT NULL,
 output_path TEXT NOT NULL, output_sha256 TEXT NOT NULL,
 created_at TEXT NOT NULL, row_mac TEXT NOT NULL,
 UNIQUE(owner_identity_digest, asset_id, revision_id, scene_id))
"""


class LocalSourceCardError(RuntimeError):
    """A source card cannot be derived or reopened from canonical evidence."""


def _integer(value: object) -> int:
    if not isinstance(value, (str, int, float)):
        raise LocalSourceCardError("stored local source-card dimensions are invalid")
    return int(value)


@dataclass(frozen=True)
class LocalSourceCardRequest:
    asset_id: str
    revision_id: str
    chapter_id: str
    scene_id: str
    title: str
    information_purpose: str
    source_chunk_ids: tuple[str, ...]


@dataclass(frozen=True)
class LocalSourceCardArtifact:
    card_id: str
    asset_id: str
    revision_id: str
    chapter_id: str
    scene_id: str
    source_chunk_ids: tuple[str, ...]
    output_path: str
    output_sha256: str
    input_digest: str
    snapshot_digest: str
    renderer_version: str
    font_digest: str
    width_px: int
    height_px: int
    created_at: str

    def selection(self) -> ReviewedVisualSelection:
        return ReviewedVisualSelection(
            scene_id=self.scene_id,
            path=self.output_path,
            expected_sha256=self.output_sha256,
            visual_label="diagram",
            source_chunk_ids=self.source_chunk_ids,
        )


class LocalSourceCardRegistry:
    def __init__(
        self,
        *,
        db_path: str,
        output_dir: str,
        font_path: str,
        integrity_key: bytes,
        width_px: int = 1280,
        height_px: int = 720,
    ) -> None:
        if not db_path or not isinstance(integrity_key, bytes) or len(integrity_key) < 32:
            raise ValueError("local source-card persistence configuration is invalid")
        if width_px != 1280 or height_px != 720:
            raise ValueError("local source-card dimensions must be 1280x720")
        self._db_path = db_path
        self._root = _private_directory(output_dir)
        self._font_path, self._font_digest = _font(font_path)
        self._key = integrity_key
        self._width = width_px
        self._height = height_px

    def create(
        self,
        request: LocalSourceCardRequest,
        *,
        owner_id: str,
        now: datetime,
    ) -> LocalSourceCardArtifact:
        request = _request(request)
        self._verify_font()
        owner_digest = hashlib.sha256(_identifier(owner_id, "owner_id").encode()).hexdigest()
        snapshot = _snapshot(
            self._db_path, request.source_chunk_ids, expected_owner_id=owner_id
        )
        snapshot_digest = hashlib.sha256(_canonical(snapshot)).hexdigest()
        render_input = {
            "asset_id": request.asset_id,
            "chapter_id": request.chapter_id,
            "height_px": self._height,
            "information_purpose": request.information_purpose,
            "renderer_version": _RENDERER_VERSION,
            "revision_id": request.revision_id,
            "scene_id": request.scene_id,
            "snapshot": snapshot,
            "title": request.title,
            "width_px": self._width,
        }
        input_digest = hashlib.sha256(_canonical(render_input)).hexdigest()
        card_id = "mmsourcecard_" + hashlib.sha256(
            f"{owner_digest}\0{input_digest}\0{self._font_digest}".encode()
        ).hexdigest()
        existing = self._load(card_id)
        if existing is not None:
            return self._reopen(existing, request, owner_digest, snapshot_digest, input_digest)
        output = self._root / f"{card_id}.png"
        payload = _render_png(
            request,
            snapshot=snapshot,
            font_path=self._font_path,
            width=self._width,
            height=self._height,
        )
        if len(payload) > _MAX_CARD_BYTES:
            raise LocalSourceCardError("local source-card output exceeds its byte ceiling")
        digest = hashlib.sha256(payload).hexdigest()
        if output.is_symlink():
            raise LocalSourceCardError("local source-card output conflicts")
        if output.exists():
            if not hmac.compare_digest(_private_png(output), digest):
                raise LocalSourceCardError("local source-card output conflicts")
        else:
            _publish(self._root, output.name, payload)
            if not hmac.compare_digest(_private_png(output), digest):
                raise LocalSourceCardError("local source-card publication conflicts")
        timestamp = _timestamp(now)
        values: list[object] = [
            card_id, owner_digest, request.asset_id, request.revision_id,
            request.chapter_id, request.scene_id, input_digest, snapshot_digest,
            _RENDERER_VERSION, self._font_digest, self._width, self._height,
            str(output), digest, timestamp,
        ]
        coordinator = FlockWriteCoordinator(self._db_path)
        with coordinator.acquire_write_context("multimedia.local_source_card.create") as connection:
            connection.execute(_DDL)
            current = connection.execute(
                "SELECT * FROM multimedia_local_source_cards WHERE card_id=?", [card_id]
            ).fetchone()
            if current is None:
                connection.execute(
                    "INSERT INTO multimedia_local_source_cards VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [*values, _mac(values, self._key)],
                )
            else:
                return self._reopen(
                    current, request, owner_digest, snapshot_digest, input_digest
                )
        return self._reopen(tuple([*values, _mac(values, self._key)]), request, owner_digest, snapshot_digest, input_digest)

    def reopen(
        self,
        card_id: str,
        request: LocalSourceCardRequest,
        *,
        owner_id: str,
    ) -> LocalSourceCardArtifact:
        request = _request(request)
        self._verify_font()
        card_id = _identifier(card_id, "card_id")
        owner_digest = hashlib.sha256(_identifier(owner_id, "owner_id").encode()).hexdigest()
        snapshot = _snapshot(
            self._db_path, request.source_chunk_ids, expected_owner_id=owner_id
        )
        snapshot_digest = hashlib.sha256(_canonical(snapshot)).hexdigest()
        input_digest = hashlib.sha256(
            _canonical(
                {
                    "asset_id": request.asset_id,
                    "chapter_id": request.chapter_id,
                    "height_px": self._height,
                    "information_purpose": request.information_purpose,
                    "renderer_version": _RENDERER_VERSION,
                    "revision_id": request.revision_id,
                    "scene_id": request.scene_id,
                    "snapshot": snapshot,
                    "title": request.title,
                    "width_px": self._width,
                }
            )
        ).hexdigest()
        row = self._load(card_id)
        if row is None:
            raise LocalSourceCardError("local source card is unavailable")
        return self._reopen(row, request, owner_digest, snapshot_digest, input_digest)

    def attest(
        self,
        card_id: str,
        request: LocalSourceCardRequest,
        *,
        owner_id: str,
        reviewer_id: str,
        operator_signing_key: bytes,
        attested_at: datetime,
    ) -> DiagramAttestation:
        if reviewer_id != owner_id:
            raise LocalSourceCardError("source-card reviewer does not own the evidence")
        verified = self.reopen(card_id, request, owner_id=owner_id)
        return attest_diagram(
            db_path=self._db_path,
            diagram_path=verified.output_path,
            content_sha256=verified.output_sha256,
            source_chunk_ids=verified.source_chunk_ids,
            reviewer_id=reviewer_id,
            operator_signing_key=operator_signing_key,
            attested_at=attested_at,
        )

    def _verify_font(self) -> None:
        if not hmac.compare_digest(
            hashlib.sha256(Path(self._font_path).read_bytes()).hexdigest(),
            self._font_digest,
        ):
            raise LocalSourceCardError("local source-card font identity changed")

    def _load(self, card_id: str) -> DatabaseRow | None:
        try:
            with connect_read(self._db_path) as connection:
                return connection.execute(
                    "SELECT * FROM multimedia_local_source_cards WHERE card_id=?",
                    [card_id],
                ).fetchone()
        except Exception:
            return None

    def _reopen(
        self,
        row: DatabaseRow,
        request: LocalSourceCardRequest,
        owner_digest: str,
        snapshot_digest: str,
        input_digest: str,
    ) -> LocalSourceCardArtifact:
        if (
            row is None or len(row) != 16 or not isinstance(row[15], str)
            or not hmac.compare_digest(row[15], _mac(list(row[:15]), self._key))
            or row[1] != owner_digest or row[2] != request.asset_id
            or row[3] != request.revision_id or row[4] != request.chapter_id
            or row[5] != request.scene_id or row[6] != input_digest
            or row[7] != snapshot_digest or row[8] != _RENDERER_VERSION
            or row[9] != self._font_digest or row[10] != self._width
            or row[11] != self._height
        ):
            raise LocalSourceCardError("stored local source-card integrity failed")
        digest = _private_png(Path(str(row[12])))
        if not hmac.compare_digest(digest, str(row[13])):
            raise LocalSourceCardError("local source-card output digest conflicts")
        return LocalSourceCardArtifact(
            card_id=str(row[0]), asset_id=str(row[2]), revision_id=str(row[3]),
            chapter_id=str(row[4]), scene_id=str(row[5]),
            source_chunk_ids=request.source_chunk_ids, output_path=str(row[12]),
            output_sha256=str(row[13]), input_digest=str(row[6]),
            snapshot_digest=str(row[7]), renderer_version=str(row[8]),
            font_digest=str(row[9]), width_px=_integer(row[10]),
            height_px=_integer(row[11]),
            created_at=str(row[14]),
        )


def _snapshot(
    db_path: str, chunk_ids: tuple[str, ...], *, expected_owner_id: str
) -> list[dict[str, str | None]]:
    if not chunk_ids or len(chunk_ids) > _MAX_CHUNKS or len(set(chunk_ids)) != len(chunk_ids):
        raise ValueError("source chunks must be bounded, non-empty, and unique")
    for value in chunk_ids:
        _identifier(value, "source_chunk_id")
    placeholders = ",".join("?" for _ in chunk_ids)
    try:
        with connect_read(db_path) as connection:
            rows = connection.execute(
                "SELECT c.chunk_id, c.document_id, c.text, c.section_path, "
                "d.title, d.source_uri, d.owner_user_id FROM chunks c "
                "JOIN documents d ON d.document_id=c.document_id "
                f"WHERE c.chunk_id IN ({placeholders})",
                list(chunk_ids),
            ).fetchall()
    except Exception:
        raise LocalSourceCardError("canonical source-card evidence is unavailable") from None
    by_id = {str(row[0]): row for row in rows}
    if len(by_id) != len(chunk_ids):
        raise LocalSourceCardError("canonical source-card evidence is incomplete")
    result: list[dict[str, str | None]] = []
    for chunk_id in chunk_ids:
        row = by_id[chunk_id]
        text = str(row[2])
        if row[6] != expected_owner_id or not text.strip() or len(text.encode()) > _MAX_TEXT_BYTES:
            raise LocalSourceCardError("canonical source-card evidence conflicts")
        result.append(
            {
                "chunk_id": chunk_id,
                "document_id": _identifier(str(row[1]), "document_id"),
                "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "excerpt": " ".join(text.split())[:360],
                "section_path": None if row[3] is None else str(row[3])[:256],
                "document_title": None if row[4] is None else str(row[4])[:256],
                "source_uri": None if row[5] is None else str(row[5])[:1024],
            }
        )
    return result


def _render_png(
    request: LocalSourceCardRequest,
    *,
    snapshot: list[dict[str, str | None]],
    font_path: str,
    width: int,
    height: int,
) -> bytes:
    image = Image.new("RGB", (width, height), "#f7f9fb")
    draw = ImageDraw.Draw(image)
    display = ImageFont.truetype(font_path, 46)
    body = ImageFont.truetype(font_path, 25)
    utility = ImageFont.truetype(font_path, 17)
    draw.rectangle((0, 0, 18, height), fill="#f2c94c")
    draw.rectangle((18, 0, width, 72), fill="#18232f")
    draw.text((54, 25), "ANTIEK  /  LOCAL SOURCE CARD", font=utility, fill="#ffffff")
    title_lines = _wrap(draw, request.title, display, width - 110, 2)
    draw.multiline_text((54, 112), "\n".join(title_lines), font=display, fill="#15202b", spacing=8)
    purpose_y = 112 + len(title_lines) * 62 + 18
    purpose_lines = _wrap(draw, request.information_purpose, body, width - 110, 2)
    draw.multiline_text((54, purpose_y), "\n".join(purpose_lines), font=body, fill="#405466", spacing=6)
    divider_y = purpose_y + len(purpose_lines) * 36 + 28
    draw.line((54, divider_y, width - 54, divider_y), fill="#6f8798", width=2)
    excerpt = str(snapshot[0]["excerpt"])
    excerpt_lines = _wrap(draw, excerpt, body, width - 140, 5)
    draw.rounded_rectangle((54, divider_y + 28, width - 54, height - 110), radius=8, fill="#dceef0", outline="#1c7c86", width=2)
    draw.multiline_text((84, divider_y + 58), "\n".join(excerpt_lines), font=body, fill="#18363a", spacing=9)
    source = str(snapshot[0]["document_title"] or snapshot[0]["document_id"])
    if len(snapshot) > 1:
        source = f"{source}  +{len(snapshot) - 1} source(s)"
    location = str(snapshot[0]["section_path"] or "Source excerpt")
    source_label = textwrap.shorten(
        f"{source}  ·  {location}", width=72, placeholder="..."
    )
    draw.text((54, height - 70), source_label, font=utility, fill="#4f6272")
    disclosure = "DIAGRAMMATIC · NOT ARCHIVAL"
    disclosure_width = draw.textbbox((0, 0), disclosure, font=utility)[2]
    draw.text(
        (width - 54 - disclosure_width, height - 70),
        disclosure,
        font=utility,
        fill="#a13d3d",
    )
    with tempfile.SpooledTemporaryFile(max_size=_MAX_CARD_BYTES) as output:
        image.save(output, format="PNG", optimize=False, compress_level=9)
        output.seek(0)
        return output.read(_MAX_CARD_BYTES + 1)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: int, limit: int) -> list[str]:
    clean = " ".join(text.split())
    if not clean or len(clean.encode()) > 16 * 1024:
        raise ValueError("source-card display text is invalid")
    words = clean.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] <= width:
            current = candidate
        else:
            if not current:
                raise ValueError("source-card word exceeds the display width")
            lines.append(current)
            current = word
            if len(lines) >= limit:
                break
    if current and len(lines) < limit:
        lines.append(current)
    if len(lines) == limit and " ".join(lines) != clean:
        lines[-1] = textwrap.shorten(lines[-1], width=max(8, len(lines[-1]) - 1), placeholder="...")
    return lines


def _request(value: LocalSourceCardRequest) -> LocalSourceCardRequest:
    if not isinstance(value, LocalSourceCardRequest):
        raise ValueError("local source-card request is invalid")
    for item, field in (
        (value.asset_id, "asset_id"), (value.revision_id, "revision_id"),
        (value.chapter_id, "chapter_id"), (value.scene_id, "scene_id"),
    ):
        _identifier(item, field)
    if (
        not value.title.strip()
        or not value.information_purpose.strip()
        or len(value.title.encode()) > 16 * 1024
        or len(value.information_purpose.encode()) > 16 * 1024
    ):
        raise ValueError("local source-card text is empty")
    return value


def _font(value: str) -> tuple[str, str]:
    path = Path(value)
    try:
        resolved = path.resolve(strict=True)
        info = resolved.stat()
    except OSError:
        raise ValueError("local source-card font is unavailable") from None
    if not path.is_absolute() or not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 32 * 1024 * 1024:
        raise ValueError("local source-card font is invalid")
    return str(resolved), hashlib.sha256(resolved.read_bytes()).hexdigest()


def _private_directory(value: str) -> Path:
    path = Path(value)
    try:
        info = path.lstat()
    except OSError:
        raise ValueError("local source-card output directory is unavailable") from None
    if not path.is_absolute() or path.is_symlink() or path.resolve() != path or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("local source-card output directory is not private")
    return path


def _publish(root: Path, name: str, payload: bytes) -> None:
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    temporary = f".{name}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=descriptor)
        try:
            view = memoryview(payload)
            while view:
                view = view[os.write(fd, view) :]
            os.fsync(fd)
        finally:
            os.close(fd)
        with suppress(FileExistsError):
            os.link(
                temporary,
                name,
                src_dir_fd=descriptor,
                dst_dir_fd=descriptor,
                follow_symlinks=False,
            )
        os.fsync(descriptor)
    finally:
        with suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=descriptor)
        os.close(descriptor)


def _private_png(path: Path) -> str:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        raise LocalSourceCardError("local source-card output is unavailable") from None
    try:
        info = os.fstat(fd)
        for _attempt in range(20):
            if info.st_nlink != 2:
                break
            time.sleep(0.005)
            info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1 or not 32 <= info.st_size <= _MAX_CARD_BYTES:
            raise LocalSourceCardError("local source-card output is not private and bounded")
        header = os.read(fd, 24)
        if header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR" or int.from_bytes(header[16:20], "big") != 1280 or int.from_bytes(header[20:24], "big") != 720:
            raise LocalSourceCardError("local source-card PNG shape conflicts")
        digest = hashlib.sha256(header)
        while chunk := os.read(fd, 1024 * 1024):
            digest.update(chunk)
        return digest.hexdigest()
    finally:
        os.close(fd)


def _identifier(value: str, field: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"{field} is not a bounded identifier")
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def _mac(values: list[object], key: bytes) -> str:
    return hmac.new(key, _canonical(values), hashlib.sha256).hexdigest()


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("local source-card timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


__all__ = [
    "LocalSourceCardArtifact", "LocalSourceCardError", "LocalSourceCardRegistry",
    "LocalSourceCardRequest",
]
