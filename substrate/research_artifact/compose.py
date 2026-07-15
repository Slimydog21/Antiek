"""Deterministically compose existing investigations into an HTML index."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import secrets
import stat
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from .export import build_html_only
from .import_notes import parse_body_from_html
from .paths import composition_member_path_for, composition_path_for, research_artifacts_dir
from .schema import ResearchArtifactBody

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


@dataclass(frozen=True)
class ComposeMember:
    investigation_id: str
    content_hash: str
    rendered_sha256: str


@dataclass(frozen=True)
class ComposeResult:
    composition_id: str
    ordered_set_digest: str
    path: Path
    members: list[ComposeMember]
    hash_conflicts: list[tuple[str, str]]


@dataclass(frozen=True)
class VerifiedCompositionMember:
    investigation_id: str
    content_hash: str
    rendered_sha256: str
    body: ResearchArtifactBody


@dataclass(frozen=True)
class VerifiedComposition:
    composition_id: str
    ordered_set_digest: str
    schema_version: int
    members: list[VerifiedCompositionMember]


def validate_investigation_ids(investigation_ids: list[str]) -> None:
    if not 2 <= len(investigation_ids) <= 20:
        raise ValueError("select between 2 and 20 investigations")
    if len(set(investigation_ids)) != len(investigation_ids):
        raise ValueError("investigation IDs must be unique")
    if any(not isinstance(iid, str) or not _SAFE_ID.fullmatch(iid) for iid in investigation_ids):
        raise ValueError("investigation ID has an unsafe shape")


def composition_id_for(members: list[tuple[str, str, str]]) -> str:
    canonical = json.dumps(members, separators=(",", ":"), ensure_ascii=False)
    return "cmp-" + hashlib.sha256(canonical.encode()).hexdigest()


def render_composition_index(metadata: dict[str, object]) -> str:
    composition_id = str(metadata["composition_id"])
    members = metadata["members"]
    conflicts = metadata["hash_conflicts"]
    if not isinstance(members, list) or not isinstance(conflicts, list):
        raise ValueError("invalid composition metadata")
    canonical_metadata = json.dumps(metadata, sort_keys=True, separators=(",", ":")).replace(
        "<", "\\u003c"
    )
    rows = "".join(
        f'<li><a href="./{composition_id}/{html.escape(str(member["investigation_id"]), quote=True)}">'
        f"{html.escape(str(member['investigation_id']))}</a> "
        f"<code>{html.escape(str(member['content_hash']))}</code></li>"
        for member in members
        if isinstance(member, dict)
    )
    conflicts_html = (
        "".join(
            f"<li>{html.escape(str(pair[0]))} vs {html.escape(str(pair[1]))}</li>"
            for pair in conflicts
            if isinstance(pair, list) and len(pair) == 2
        )
        or "<li>None</li>"
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Composed research artifacts</title></head><body><main>
<h1>Composed research artifacts</h1><ol>{rows}</ol>
<section><h2>Duplicate-content conflicts</h2><ul>{conflicts_html}</ul></section>
<script type="application/json" id="composition-metadata">{canonical_metadata}</script>
</main></body></html>"""


def _publish_immutable(path: Path, content: str) -> None:
    raw = content.encode("utf-8")
    directory = _open_or_create_directory(path.parent)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)

    def read_existing() -> bytes:
        fd = os.open(path.name, flags, dir_fd=directory)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise OSError("immutable artifact is not a singly linked regular file")
            chunks: list[bytes] = []
            while chunk := os.read(fd, 1024 * 1024):
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            os.close(fd)

    try:
        try:
            existing = read_existing()
        except FileNotFoundError:
            existing = None
        if existing is not None:
            if existing != raw:
                raise ValueError("immutable composition artifact conflicts with stored bytes")
            return

        tmp_name = f".{path.name}.{secrets.token_hex(12)}"
        fd = os.open(
            tmp_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=directory,
        )
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(
                    tmp_name,
                    path.name,
                    src_dir_fd=directory,
                    dst_dir_fd=directory,
                    follow_symlinks=False,
                )
                os.fsync(directory)
            except FileExistsError:
                if read_existing() != raw:
                    raise ValueError(
                        "immutable composition artifact conflicts with stored bytes"
                    ) from None
        finally:
            with suppress(FileNotFoundError):
                os.unlink(tmp_name, dir_fd=directory)
    finally:
        os.close(directory)


def _open_directory(path: Path, *, create: bool) -> int:
    absolute = path.expanduser().absolute()
    store = research_artifacts_dir().expanduser().absolute()
    try:
        relative = absolute.relative_to(store.parent)
    except ValueError as exc:
        raise ValueError("artifact publication escaped the configured store") from exc
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    # Resolve only the store's existing parent. The configured store and every
    # artifact-owned descendant are traversed with O_NOFOLLOW below.
    descriptor = os.open(store.parent.resolve(strict=True), flags)
    try:
        for part in relative.parts:
            try:
                next_descriptor = os.open(part, flags, dir_fd=descriptor)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(part, 0o700, dir_fd=descriptor)
                next_descriptor = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _open_or_create_directory(path: Path) -> int:
    return _open_directory(path, create=True)


def read_composition_store_file(*parts: str) -> bytes:
    if not parts or any(not part or part in {".", ".."} or "/" in part for part in parts):
        raise ValueError("invalid composition store path")
    directory = _open_directory(
        composition_path_for("cmp-" + "0" * 64).parent.joinpath(*parts[:-1]),
        create=False,
    )
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(parts[-1], flags, dir_fd=directory)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise FileNotFoundError
            chunks: list[bytes] = []
            while chunk := os.read(fd, 1024 * 1024):
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            os.close(fd)
    finally:
        os.close(directory)


def verify_composition_index(content: bytes, composition_id: str) -> dict[str, object]:
    marker = b'id="composition-metadata">'
    metadata = json.loads(content.split(marker, 1)[1].split(b"</script>", 1)[0])
    members = metadata["members"]
    if (
        not isinstance(members, list)
        or not 2 <= len(members) <= 20
        or any(
            not isinstance(member, dict)
            or set(member) != {"investigation_id", "content_hash", "rendered_sha256"}
            or not isinstance(member.get("investigation_id"), str)
            or not _SAFE_ID.fullmatch(member["investigation_id"])
            or not isinstance(member.get("content_hash"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", member["content_hash"])
            or not isinstance(member.get("rendered_sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", member["rendered_sha256"])
            for member in members
        )
    ):
        raise ValueError("invalid composition members")
    identity = [
        (member["investigation_id"], member["content_hash"], member["rendered_sha256"])
        for member in members
    ]
    expected_conflicts: list[list[str]] = []
    first_by_hash: dict[str, str] = {}
    for investigation_id, content_hash, _rendered_sha256 in identity:
        if content_hash in first_by_hash:
            expected_conflicts.append([first_by_hash[content_hash], investigation_id])
        else:
            first_by_hash[content_hash] = investigation_id
    if (
        set(metadata)
        != {
            "composition_id",
            "hash_conflicts",
            "members",
            "ordered_set_digest",
            "schema_version",
        }
        or type(metadata.get("schema_version")) is not int
        or metadata.get("schema_version") != 1
        or metadata.get("hash_conflicts") != expected_conflicts
        or metadata.get("composition_id") != composition_id
        or metadata.get("ordered_set_digest") != composition_id.removeprefix("cmp-")
        or composition_id_for(identity) != composition_id
        or render_composition_index(metadata).encode("utf-8") != content
    ):
        raise ValueError("composition index integrity failure")
    return metadata


def load_verified_composition(composition_id: str) -> VerifiedComposition:
    index_path = composition_path_for(composition_id)
    metadata = verify_composition_index(
        read_composition_store_file(index_path.name), composition_id
    )
    verified: list[VerifiedCompositionMember] = []
    for member in metadata["members"]:
        investigation_id = member["investigation_id"]
        member_path = composition_member_path_for(composition_id, investigation_id)
        raw = read_composition_store_file(composition_id, member_path.name)
        if hashlib.sha256(raw).hexdigest() != member["rendered_sha256"]:
            raise ValueError("composition member rendered hash mismatch")
        body = parse_body_from_html(raw.decode("utf-8"))
        if (
            body.investigation_id != investigation_id
            or body.content_hash() != member["content_hash"]
        ):
            raise ValueError("composition member semantic identity mismatch")
        verified.append(
            VerifiedCompositionMember(
                investigation_id=investigation_id,
                content_hash=member["content_hash"],
                rendered_sha256=member["rendered_sha256"],
                body=body,
            )
        )
    return VerifiedComposition(
        composition_id=composition_id,
        ordered_set_digest=metadata["ordered_set_digest"],
        schema_version=metadata["schema_version"],
        members=verified,
    )


def compose_artifacts(
    investigation_ids: list[str],
    *,
    db_path: str | None = None,
    events_dir: str | None = None,
    write_index: bool = True,
) -> ComposeResult:
    validate_investigation_ids(investigation_ids)
    members: list[ComposeMember] = []
    rendered_members: list[tuple[str, str]] = []
    by_hash: dict[str, str] = {}
    conflicts: list[tuple[str, str]] = []
    for iid in investigation_ids:
        body, rendered = build_html_only(iid, db_path=db_path, events_dir=events_dir)
        member = ComposeMember(
            iid,
            body.content_hash(),
            hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
        )
        members.append(member)
        rendered_members.append((iid, rendered))
        previous = by_hash.get(member.content_hash)
        if previous is not None:
            conflicts.append((previous, iid))
        else:
            by_hash[member.content_hash] = iid

    member_identity = [(m.investigation_id, m.content_hash, m.rendered_sha256) for m in members]
    composition_id = composition_id_for(member_identity)
    digest = composition_id.removeprefix("cmp-")
    metadata = {
        "composition_id": composition_id,
        "hash_conflicts": [list(pair) for pair in conflicts],
        "members": [
            {
                "content_hash": m.content_hash,
                "investigation_id": m.investigation_id,
                "rendered_sha256": m.rendered_sha256,
            }
            for m in members
        ],
        "ordered_set_digest": digest,
        "schema_version": 1,
    }
    index = render_composition_index(metadata)
    out_path = composition_path_for(composition_id)
    if write_index:
        # Render everything before the first write; every individual publish is atomic.
        for investigation_id, rendered in rendered_members:
            _publish_immutable(
                composition_member_path_for(composition_id, investigation_id), rendered
            )
        _publish_immutable(out_path, index)
    return ComposeResult(composition_id, digest, out_path, members, conflicts)
