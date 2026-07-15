"""Deterministic, durable publication of completed recursive note windows.

This service is deliberately independent of ``generate_twin``.  It transports
already-authorized V20 note output and never creates signed generation authority.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import stat
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from roles.note_taker.parser import parse_notes_response
from runtime.db_lock import connect_read, connect_write
from substrate.graph import default_db_path
from substrate.graph.schema import init_database_at_path
from substrate.research_artifact.schema import ResearchArtifactBody
from substrate.schemas.events import NoteCompressedDocWrittenPayload
from substrate.write.event_outbox import (
    build_typed_envelope,
    canonical_event_json,
    dispatch_aggregate_pending,
    enqueue_event,
)

COMPRESSOR_VERSION = 1
RENDERER_VERSION = 1
COMPRESSION_AUTHORITY = "window_note_compression_v1"
MAX_MEMBERS = 1_000
MAX_NOTES = 10_000
MAX_SOURCE_EVENTS = 100_000
MAX_BODY_BYTES = 16 * 1024 * 1024
MAX_HTML_BYTES = 24 * 1024 * 1024


class TwinNoteCompressionError(RuntimeError):
    """Admission, identity, corruption, or publication conflict."""


class OwnershipResolver(Protocol):
    def __call__(self, account_id: str, asset_id: str, investigation_id: str) -> bool: ...


@dataclass(frozen=True)
class TwinNoteRevision:
    revision_id: str
    account_id: str
    asset_id: str
    supersedes_revision_id: str | None
    membership_sha256: str
    body_json: str
    body_sha256: str
    html_bytes: bytes
    html_sha256: str
    relative_path: str
    note_count: int
    source_event_count: int

    @property
    def body(self) -> ResearchArtifactBody:
        return ResearchArtifactBody.model_validate_json(self.body_json)

@dataclass(frozen=True)
class WindowAdmission:
    account_id: str
    asset_id: str
    window_ids: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    member_json: tuple[str, ...]
    attributed_json: tuple[str, ...]
    source_event_ids: tuple[str, ...]

    def members(self) -> list[dict[str, Any]]:
        return [json.loads(value) for value in self.member_json]

    def attributed(self) -> list[dict[str, Any]]:
        return [json.loads(value) for value in self.attributed_json]


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha(value: str | bytes) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def _safe_identity(value: str, label: str) -> str:
    if type(value) is not str or not value or value != value.strip() or len(value) > 512:
        raise TwinNoteCompressionError(f"{label} must be a canonical non-empty string")
    return value

def build_window_admission(*, db_path: str, ownership_resolver: OwnershipResolver,
                           account_id: str, asset_id: str,
                           window_ids: Sequence[str]) -> WindowAdmission:
    account_id = _safe_identity(account_id, "account_id")
    asset_id = _safe_identity(asset_id, "asset_id")
    if type(window_ids) not in (tuple, list) or not window_ids or len(window_ids) > MAX_MEMBERS:
        raise TwinNoteCompressionError("window_ids must be an ordered non-empty bounded sequence")
    ids = tuple(_safe_identity(value, "window_id") for value in window_ids)
    if len(set(ids)) != len(ids):
        raise TwinNoteCompressionError("duplicate window members are forbidden")
    select = ("SELECT window_id,consumer_version,investigation_id,ordinal,source_event_ids_json,"
              "source_digest,request_json,request_sha256,state,raw_result,raw_result_sha256 "
              f"FROM note_taker_windows WHERE window_id IN ({','.join('?' for _ in ids)})")
    with connect_read(db_path) as con:
        fetched = con.execute(select, list(ids)).fetchall()
    by_id = {row[0]: tuple(row) for row in fetched}
    if set(by_id) != set(ids):
        raise TwinNoteCompressionError("a requested window is missing")
    rows = tuple(by_id[window_id] for window_id in ids)
    for row in rows:
        if not ownership_resolver(account_id, asset_id, row[2]):
            raise TwinNoteCompressionError("ownership resolver rejected a member")
    members: list[dict[str, Any]] = []
    attributed: list[dict[str, Any]] = []
    seen_notes: set[str] = set()
    all_sources: set[str] = set()
    for ordinal, row in enumerate(rows):
        window_id, consumer_version, investigation_id, window_ordinal, source_json, source_digest, request_json, request_sha, state, raw, raw_sha = row
        if state != "completed" or raw is None or raw_sha is None:
            raise TwinNoteCompressionError("only completed windows with stored output are eligible")
        if _sha(request_json) != request_sha or _sha(raw) != raw_sha or _sha(source_json) != source_digest:
            raise TwinNoteCompressionError("window evidence digest mismatch")
        try:
            sources, request = json.loads(source_json), json.loads(request_json)
        except (TypeError, ValueError) as exc:
            raise TwinNoteCompressionError("window evidence is not canonical JSON") from exc
        if (not isinstance(sources, list) or not sources or any(type(x) is not str for x in sources)
                or _canonical(sources) != source_json or _canonical(request) != request_json
                or not isinstance(request, dict) or request.get("investigation_id") != investigation_id
                or request.get("source_event_ids") != sources):
            raise TwinNoteCompressionError("window request is not bound to its investigation and sources")
        all_sources.update(sources)
        members.append({"member_ordinal":ordinal,"investigation_id":investigation_id,
            "window_id":window_id,"consumer_version":consumer_version,"window_ordinal":window_ordinal,
            "source_digest":source_digest,"request_sha256":request_sha,"raw_result_sha256":raw_sha})
        for note in parse_notes_response(raw, canonical_event_ids=sources):
            identity = _canonical({"text":note.text,"confidence":note.confidence,
                                   "source_event_ids":list(note.source_event_ids)})
            if identity not in seen_notes:
                seen_notes.add(identity)
                attributed.append({"text":note.text,"confidence":note.confidence,
                    "source_event_ids":list(note.source_event_ids),"investigation_id":investigation_id,
                    "window_id":window_id})
    if len(attributed) > MAX_NOTES or len(all_sources) > MAX_SOURCE_EVENTS:
        raise TwinNoteCompressionError("note or source-event ceiling exceeded")
    return WindowAdmission(account_id,asset_id,ids,rows,tuple(_canonical(x) for x in members),
                           tuple(_canonical(x) for x in attributed),
                           tuple(sorted(all_sources)))


def _static_html(body: ResearchArtifactBody, *, revision_id: str, authority: str,
                 attributions: list[dict[str, Any]]) -> bytes:
    body_json = _canonical(body.model_dump(mode="json")).replace("<", "\\u003c")
    items = "".join(
        '<li data-investigation-id="{}" data-window-id="{}" data-source-events="{}">'
        '<p>{}</p><p class="attribution">Investigation {} · window {} · sources {}</p></li>'.format(
            html.escape(row["investigation_id"], quote=True),
            html.escape(row["window_id"], quote=True),
            html.escape(",".join(row["source_event_ids"]), quote=True),
            html.escape(row["text"]), html.escape(row["investigation_id"]),
            html.escape(row["window_id"]), html.escape(", ".join(row["source_event_ids"])),
        ) for row in attributions
    ) or '<li class="empty">No attributed notes.</li>'
    rendered = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>Twin notes — {html.escape(body.problem_question)}</title>'
        '<style>body{max-width:760px;margin:auto;padding:28px;font:16px/1.55 system-ui;color:#1c1917}'
        'li{margin:18px 0}.attribution,footer{color:#57534e;font-size:.85rem}.empty{font-style:italic}</style>'
        f'</head><body><main data-revision-id="{html.escape(revision_id, quote=True)}" '
        f'data-authority="{authority}"><h1>{html.escape(body.problem_question)}</h1>'
        f'<ol>{items}</ol><script type="application/json" id="antiek-artifact-v1">{body_json}</script>'
        f'<footer>Immutable revision {html.escape(revision_id)}</footer></main></body></html>'
    )
    return rendered.encode("utf-8")


class DurableTwinNoteCompression:
    def __init__(self, ownership_resolver: OwnershipResolver, *, db_path: str | None = None,
                 publication_root: str | os.PathLike[str], events_dir: str | None = None,
                 checkpoint: Callable[[str, str], None] | None = None) -> None:
        if not callable(ownership_resolver):
            raise TypeError("ownership_resolver must be callable")
        self.ownership_resolver = ownership_resolver
        self.db_path = db_path or default_db_path()
        self.publication_root = Path(publication_root)
        self.events_dir = events_dir
        self.checkpoint = checkpoint
        init_database_at_path(self.db_path)

    def _check(self, name: str, identity: str) -> None:
        if self.checkpoint:
            self.checkpoint(name, identity)

    def verify_replay_ledgers(self, revision: Any) -> None:
        with connect_read(self.db_path) as con:
            path_row = con.execute("SELECT relative_path FROM twin_note_revisions WHERE revision_id=?",
                                   [revision.revision_id]).fetchone()
        if path_row is None:
            raise TwinNoteCompressionError("revision is missing during replay")
        relative_path = path_row[0]
        effect_id = "tne-" + _sha(_canonical([revision.revision_id,relative_path,
                                               revision.html_sha256]))[:32]
        event_time = datetime(2000,1,1,tzinfo=UTC)+timedelta(seconds=int(_sha(revision.revision_id)[:8],16))
        event = build_typed_envelope(revision.revision_id,
            NoteCompressedDocWrittenPayload(output_path=relative_path,
                note_count=revision.note_count,byte_size=len(revision.html_bytes)),
            role="twin_note_compressor",policy_id=COMPRESSION_AUTHORITY,document_id=revision.asset_id,
            event_id="evt-compress-"+_sha(revision.revision_id)[:24],emitted_at=event_time)
        encoded = canonical_event_json(event)
        expected_outbox = (event.event_id,f"twin-note-compress:{revision.revision_id}",
            revision.revision_id,"twin_note_revision",revision.revision_id,encoded,_sha(encoded))
        with connect_read(self.db_path) as con:
            effects = con.execute("SELECT effect_id,revision_id,expected_path,expected_sha256 "
                "FROM twin_note_publication_effects WHERE revision_id=?",[revision.revision_id]).fetchall()
            outbox = con.execute("SELECT event_id,operation_id,investigation_id,aggregate_kind,aggregate_id,"
                "event_json,event_sha256 FROM write_event_outbox WHERE aggregate_kind='twin_note_revision' "
                "AND aggregate_id=?",[revision.revision_id]).fetchall()
        if effects != [(effect_id,revision.revision_id,relative_path,revision.html_sha256)]:
            raise TwinNoteCompressionError("publication effect conflicts with immutable bytes")
        if outbox != [expected_outbox]:
            raise TwinNoteCompressionError("outbox conflicts with immutable event bytes")

    def compress(self, *, account_id: str, asset_id: str, window_ids: Sequence[str],
                 expected_predecessor: str | None = None,
                 command_receipt: tuple[str, str, str] | None = None) -> TwinNoteRevision:
        admission = build_window_admission(db_path=self.db_path,
            ownership_resolver=self.ownership_resolver, account_id=account_id,
            asset_id=asset_id, window_ids=window_ids)
        account_id, asset_id, ids = admission.account_id, admission.asset_id, admission.window_ids
        if expected_predecessor is not None:
            _safe_identity(expected_predecessor, "expected_predecessor")

        select_windows = (
            "SELECT window_id, consumer_version, investigation_id, ordinal, source_event_ids_json, "
            "source_digest, request_json, request_sha256, state, raw_result, raw_result_sha256 "
            f"FROM note_taker_windows WHERE window_id IN ({','.join('?' for _ in ids)})"
        )
        with connect_write(self.db_path, purpose="twin_note/compress") as con:
            con.execute("BEGIN TRANSACTION")
            rows = con.execute(select_windows, list(ids)).fetchall()
            exact_rows = tuple({row[0]: tuple(row) for row in rows}[window_id] for window_id in ids)
            if exact_rows != admission.rows:
                con.execute("ROLLBACK")
                raise TwinNoteCompressionError("window evidence changed after ownership resolution")
            members, attributed = admission.members(), admission.attributed()
            all_sources = admission.source_event_ids
            membership = _sha(_canonical(members))
            identity = _canonical({"account_id": account_id, "asset_id": asset_id,
                "supersedes_revision_id": expected_predecessor, "membership_sha256": membership,
                "compressor_version": COMPRESSOR_VERSION, "renderer_version": RENDERER_VERSION})
            revision_id = "tnr-" + _sha(identity)[:32]
            relative_path = f"{_sha(account_id)[:24]}/{_sha(asset_id)[:24]}/{revision_id}.html"
            body = ResearchArtifactBody(investigation_id=revision_id,
                problem_question=f"Compressed twin notes for {asset_id}", insights=[], open_questions=[],
                synthesis_excerpt=None, synthesis_withheld=True, source_event_ids=sorted(all_sources),
                agent_notes=[f"[{r['investigation_id']} | {r['window_id']} | {','.join(r['source_event_ids'])}] {r['text']}" for r in attributed])
            body_json = _canonical(body.model_dump(mode="json"))
            body_sha = _sha(body_json)
            html_bytes = _static_html(body, revision_id=revision_id,
                                      authority=COMPRESSION_AUTHORITY, attributions=attributed)
            if len(body_json.encode()) > MAX_BODY_BYTES or len(html_bytes) > MAX_HTML_BYTES:
                raise TwinNoteCompressionError("body or HTML byte ceiling exceeded")
            html_sha = _sha(html_bytes)
            effect_id = "tne-" + _sha(_canonical([revision_id, relative_path, html_sha]))[:32]
            event_time = datetime(2000, 1, 1, tzinfo=UTC) + timedelta(seconds=int(_sha(revision_id)[:8], 16))
            created_at = event_time.replace(tzinfo=None)

            current_rows = con.execute(
                "SELECT r.revision_id FROM twin_note_revisions r WHERE r.account_id=? AND r.asset_id=? "
                "AND NOT EXISTS (SELECT 1 FROM twin_note_revisions s WHERE s.account_id=r.account_id "
                "AND s.asset_id=r.asset_id AND s.supersedes_revision_id=r.revision_id)",
                [account_id, asset_id],
            ).fetchall()
            existing = con.execute("SELECT * FROM twin_note_revisions WHERE revision_id=?", [revision_id]).fetchone()
            expected_current = [] if expected_predecessor is None else [(expected_predecessor,)]
            # A command key is the authority for materialization.  A different
            # key may not adopt deterministic bytes created from a predecessor
            # that ceased to be current while admission was in flight.
            if current_rows != expected_current and (existing is None or command_receipt is not None):
                raise TwinNoteCompressionError("expected predecessor is stale")
            immutable = (revision_id, account_id, asset_id, expected_predecessor, COMPRESSOR_VERSION,
                RENDERER_VERSION, membership, body_json, body_sha, html_bytes, html_sha, relative_path,
                len(attributed), len(all_sources), created_at)
            event = build_typed_envelope(revision_id,
                NoteCompressedDocWrittenPayload(output_path=relative_path, note_count=len(attributed), byte_size=len(html_bytes)),
                role="twin_note_compressor", policy_id=COMPRESSION_AUTHORITY,
                document_id=asset_id, event_id="evt-compress-" + _sha(revision_id)[:24], emitted_at=event_time)
            try:
                if existing is None:
                    con.execute("INSERT INTO twin_note_revisions (revision_id,account_id,asset_id,supersedes_revision_id,compressor_version,renderer_version,membership_sha256,body_json,body_sha256,html_bytes,html_sha256,relative_path,note_count,source_event_count,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", list(immutable))
                    for member in members:
                        con.execute("INSERT INTO twin_note_revision_members VALUES (?,?,?,?,?,?,?,?)", [revision_id, member["member_ordinal"], member["investigation_id"], member["window_id"], member["consumer_version"], member["window_ordinal"], member["source_digest"], member["raw_result_sha256"]])
                    con.execute("INSERT INTO twin_note_publication_effects (effect_id,revision_id,expected_path,expected_sha256) VALUES (?,?,?,?)", [effect_id, revision_id, relative_path, html_sha])
                    enqueue_event(con, operation_id=f"twin-note-compress:{revision_id}", aggregate_kind="twin_note_revision", aggregate_id=revision_id, event=event)
                else:
                    selected = existing[:15]
                    if selected != immutable:
                        raise TwinNoteCompressionError("revision identity was reused with different immutable bytes")
                    expected_members = [(revision_id, member["member_ordinal"], member["investigation_id"],
                        member["window_id"], member["consumer_version"], member["window_ordinal"],
                        member["source_digest"], member["raw_result_sha256"]) for member in members]
                    stored_members = con.execute("SELECT revision_id,member_ordinal,investigation_id,window_id,consumer_version,window_ordinal,source_digest,raw_result_sha256 FROM twin_note_revision_members WHERE revision_id=? ORDER BY member_ordinal", [revision_id]).fetchall()
                    if stored_members != expected_members:
                        raise TwinNoteCompressionError("revision member ledger conflicts with immutable bytes")
                    effect = con.execute("SELECT effect_id,revision_id,expected_path,expected_sha256 FROM twin_note_publication_effects WHERE revision_id=?", [revision_id]).fetchall()
                    if effect != [(effect_id, revision_id, relative_path, html_sha)]:
                        raise TwinNoteCompressionError("publication effect conflicts with immutable bytes")
                    enqueue_event(con, operation_id=f"twin-note-compress:{revision_id}", aggregate_kind="twin_note_revision", aggregate_id=revision_id, event=event)
                if command_receipt is not None:
                    idempotency_key, request_sha, preview_sha = command_receipt
                    receipt = con.execute(
                        "SELECT request_sha256,preview_sha256,asset_id,expected_predecessor,revision_id,created_at "
                        "FROM twin_note_revision_commands WHERE account_id=? AND idempotency_key=?",
                        [account_id, idempotency_key]).fetchone()
                    expected_receipt = (request_sha, preview_sha, asset_id, expected_predecessor,
                                        revision_id, created_at)
                    if receipt is None:
                        con.execute("INSERT INTO twin_note_revision_commands "
                            "(account_id,idempotency_key,request_sha256,preview_sha256,asset_id,expected_predecessor,revision_id,created_at) "
                            "VALUES (?,?,?,?,?,?,?,?)", [account_id,idempotency_key,request_sha,preview_sha,
                            asset_id,expected_predecessor,revision_id,created_at])
                    elif receipt != expected_receipt:
                        raise TwinNoteCompressionError("idempotency receipt conflicts with immutable command")
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
        self._check("after_transaction_commit", revision_id)
        self.recover(revision_id=revision_id)
        return TwinNoteRevision(revision_id, account_id, asset_id, expected_predecessor, membership,
            body_json, body_sha, html_bytes, html_sha, relative_path, len(attributed), len(all_sources))

    def recover(self, *, revision_id: str | None = None) -> list[str]:
        published: list[str] = []
        with connect_write(self.db_path, purpose="twin_note/recover") as con:
            where, args = (" AND e.revision_id=?", [revision_id]) if revision_id else ("", [])
            rows = con.execute("SELECT e.effect_id,e.revision_id,e.expected_path,e.expected_sha256,r.html_bytes,e.state "
                "FROM twin_note_publication_effects e JOIN twin_note_revisions r USING(revision_id) "
                "WHERE TRUE" + where + " ORDER BY e.created_at,e.effect_id", args).fetchall()
            for effect_id, rid, relative, digest, blob, state in rows:
                payload = bytes(blob)
                if _sha(payload) != digest:
                    raise TwinNoteCompressionError("publication effect does not match authoritative DB bytes")
                self._publish_one(effect_id, relative, digest, payload)
                changed = con.execute("UPDATE twin_note_publication_effects SET state='published',attempt_count=attempt_count+1,published_at=CURRENT_TIMESTAMP WHERE effect_id=? AND state='pending' RETURNING effect_id", [effect_id]).fetchone()
                if changed:
                    published.append(rid)
                self._check("after_publication_receipt", rid)
            targets = [revision_id] if revision_id else [row[0] for row in con.execute("SELECT DISTINCT aggregate_id FROM write_event_outbox WHERE aggregate_kind='twin_note_revision' AND state='pending'").fetchall()]
            for rid in targets:
                dispatch_aggregate_pending(con, rid, aggregate_kind="twin_note_revision", aggregate_id=rid,
                                           events_dir=self.events_dir, checkpoint=self.checkpoint)
        return published

    def _publish_one(self, effect_id: str, relative: str, digest: str, payload: bytes) -> None:
        root = self.publication_root
        relative_parts = Path(relative).parts
        if len(relative_parts) != 3 or any(part in ("", ".", "..") for part in relative_parts):
            raise TwinNoteCompressionError("publication path is not canonical")

        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        # Walk even the configured root from the filesystem root.  A single
        # pathname open with O_NOFOLLOW protects only its final component and
        # would still permit a swapped symlink in an ancestor.
        root_parts = Path(os.path.abspath(os.fspath(root))).parts
        directory_fd = os.open(root_parts[0], directory_flags)
        try:
            for component in root_parts[1:]:
                try:
                    os.mkdir(component, mode=0o700, dir_fd=directory_fd)
                except FileExistsError:
                    pass
                try:
                    child_fd = os.open(component, directory_flags, dir_fd=directory_fd)
                except OSError as exc:
                    raise TwinNoteCompressionError(
                        "publication root is not a nofollow-opened directory tree"
                    ) from exc
                os.close(directory_fd)
                directory_fd = child_fd
        except Exception:
            os.close(directory_fd)
            raise
        try:
            for component in relative_parts[:-1]:
                try:
                    os.mkdir(component, mode=0o700, dir_fd=directory_fd)
                except FileExistsError:
                    pass
                try:
                    child_fd = os.open(component, directory_flags, dir_fd=directory_fd)
                except OSError as exc:
                    raise TwinNoteCompressionError("publication path contains a non-directory or symlink") from exc
                os.close(directory_fd)
                directory_fd = child_fd

            final_name = relative_parts[-1]
            temp_name = f".{effect_id}.tmp"

            def verify_final(*, missing_ok: bool) -> bool:
                try:
                    fd = os.open(final_name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
                except FileNotFoundError:
                    if missing_ok:
                        return False
                    raise TwinNoteCompressionError("published file disappeared")
                except OSError as exc:
                    raise TwinNoteCompressionError("publication final cannot be nofollow-opened") from exc
                try:
                    info = os.fstat(fd)
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                        raise TwinNoteCompressionError("publication final is not a singly-linked regular file")
                    chunks: list[bytes] = []
                    while True:
                        chunk = os.read(fd, 1024 * 1024)
                        if not chunk:
                            break
                        chunks.append(chunk)
                    actual = b"".join(chunks)
                    if actual != payload or _sha(actual) != digest:
                        raise TwinNoteCompressionError("publication path contains conflicting bytes")
                    return True
                finally:
                    os.close(fd)

            temp_owned = False
            try:
                info = os.stat(temp_name, dir_fd=directory_fd, follow_symlinks=False)
            except FileNotFoundError:
                info = None
            if info is not None:
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    # A crash after link leaves the owned temp and final as the
                    # only two names for one inode. Remove the temp name before
                    # enforcing the final's single-link invariant.
                    try:
                        final_info = os.stat(final_name, dir_fd=directory_fd, follow_symlinks=False)
                    except FileNotFoundError:
                        final_info = None
                    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 2 or
                            final_info is None or final_info.st_ino != info.st_ino or
                            final_info.st_dev != info.st_dev):
                        raise TwinNoteCompressionError("stale publication temp has a non-owned shape")
                    os.unlink(temp_name, dir_fd=directory_fd)
                    os.fsync(directory_fd)
                    info = None
                if info is not None:
                    temp_owned = True

            if verify_final(missing_ok=True):
                if temp_owned:
                    os.unlink(temp_name, dir_fd=directory_fd)
                    os.fsync(directory_fd)
                return

            flags = os.O_WRONLY | os.O_NOFOLLOW
            if temp_owned:
                fd = os.open(temp_name, flags | os.O_TRUNC, dir_fd=directory_fd)
            else:
                fd = os.open(temp_name, flags | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=directory_fd)
                temp_owned = True
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise TwinNoteCompressionError("temporary publication is not an exclusive regular file")
                view = memoryview(payload)
                while view:
                    count = os.write(fd, view)
                    if count <= 0:
                        raise TwinNoteCompressionError("temporary publication write made no progress")
                    view = view[count:]
                self._check("after_temporary_write", effect_id)
                os.fsync(fd)
                self._check("after_file_fsync", effect_id)
            finally:
                os.close(fd)
            info = os.stat(temp_name, dir_fd=directory_fd, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise TwinNoteCompressionError("temporary publication is not an exclusive regular file")
            try:
                os.link(temp_name, final_name, src_dir_fd=directory_fd,
                        dst_dir_fd=directory_fd, follow_symlinks=False)
            except FileExistsError:
                verify_final(missing_ok=False)
            self._check("after_link", effect_id)
            os.fsync(directory_fd)
            self._check("after_directory_fsync", effect_id)
            os.unlink(temp_name, dir_fd=directory_fd)
            temp_owned = False
            os.fsync(directory_fd)
            verify_final(missing_ok=False)
        finally:
            os.close(directory_fd)

    def current_revision(self, *, account_id: str, asset_id: str) -> TwinNoteRevision | None:
        with connect_read(self.db_path) as con:
            rows = con.execute("SELECT r.revision_id,r.account_id,r.asset_id,r.supersedes_revision_id,r.membership_sha256,r.body_json,r.body_sha256,r.html_bytes,r.html_sha256,r.relative_path,r.note_count,r.source_event_count FROM twin_note_revisions r WHERE r.account_id=? AND r.asset_id=? AND NOT EXISTS (SELECT 1 FROM twin_note_revisions s WHERE s.account_id=r.account_id AND s.asset_id=r.asset_id AND s.supersedes_revision_id=r.revision_id)", [account_id, asset_id]).fetchall()
        if len(rows) > 1:
            raise TwinNoteCompressionError("multiple current revisions violate immutable supersession")
        return None if not rows else TwinNoteRevision(*rows[0][:7], bytes(rows[0][7]), *rows[0][8:])


TwinNoteCompressionService = DurableTwinNoteCompression

__all__ = ["COMPRESSION_AUTHORITY", "COMPRESSOR_VERSION", "RENDERER_VERSION", "DurableTwinNoteCompression", "OwnershipResolver", "TwinNoteCompressionError", "TwinNoteCompressionService", "TwinNoteRevision"]
