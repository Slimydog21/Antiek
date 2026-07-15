"""Owner-bound, database-authoritative serving of immutable twin notes."""

from __future__ import annotations

import hashlib
import html
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Sequence

from roles.note_taker.parser import parse_notes_response
from runtime.db_lock import connect_read, connect_write
from substrate.graph import default_db_path
from substrate.research_artifact.schema import ResearchArtifactBody

from .compression import (
    COMPRESSION_AUTHORITY, COMPRESSOR_VERSION, MAX_BODY_BYTES, MAX_HTML_BYTES,
    MAX_MEMBERS, MAX_NOTES, MAX_SOURCE_EVENTS, RENDERER_VERSION, _static_html,
)

COMPOSITION_VERSION = 1
MAX_ASSETS = 200
MAX_HISTORY = 1000


class TwinNoteUnavailable(LookupError):
    pass


class TwinNoteIntegrityError(RuntimeError):
    pass


class TwinNoteInputError(ValueError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def _identity(value: str, prefix: str) -> str:
    if type(value) is not str or not value.startswith(prefix) or len(value) != 36 or value != value.strip():
        raise TwinNoteUnavailable
    if any(c not in "0123456789abcdef" for c in value[4:]):
        raise TwinNoteUnavailable
    return value


@dataclass(frozen=True)
class VerifiedRevision:
    revision_id: str
    asset_id: str
    supersedes_revision_id: str | None
    body_sha256: str
    html_bytes: bytes
    html_sha256: str
    note_count: int
    source_count: int
    body: ResearchArtifactBody

    def metadata(self) -> dict[str, Any]:
        return {"revision_id": self.revision_id, "asset_id": self.asset_id, "note_count": self.note_count,
                "source_count": self.source_count}


class TwinNoteServingService:
    """Read operations never initialize, repair, touch files, or acquire a writer."""

    def __init__(self, *, db_path: str | None = None) -> None:
        self.db_path = db_path or default_db_path()

    def _verify_revision(self, con: Any, account_id: str, revision_id: str) -> VerifiedRevision:
        _identity(revision_id, "tnr-")
        rows = con.execute(
            "SELECT revision_id,account_id,asset_id,supersedes_revision_id,compressor_version,renderer_version,"
            "membership_sha256,body_json,body_sha256,html_bytes,html_sha256,relative_path,note_count,source_event_count "
            "FROM twin_note_revisions WHERE account_id=? AND revision_id=?", [account_id, revision_id]).fetchall()
        if len(rows) != 1:
            raise TwinNoteUnavailable
        (rid, owner, asset_id, predecessor, compressor, renderer, membership, body_json, body_sha,
         blob, html_sha, relative, note_count, source_count) = rows[0]
        try:
            if owner != account_id or compressor != COMPRESSOR_VERSION or renderer != RENDERER_VERSION:
                raise TwinNoteIntegrityError
            if any(type(v) is not str or not v or len(v) > 512 for v in (account_id, asset_id)):
                raise TwinNoteIntegrityError
            if len(body_json.encode()) > MAX_BODY_BYTES or len(bytes(blob)) > MAX_HTML_BYTES:
                raise TwinNoteIntegrityError
            parsed = json.loads(body_json)
            if _canonical(parsed) != body_json or _sha(body_json) != body_sha:
                raise TwinNoteIntegrityError
            body = ResearchArtifactBody.model_validate(parsed)
            if body.investigation_id != rid:
                raise TwinNoteIntegrityError
            members = con.execute(
                "SELECT member_ordinal,investigation_id,window_id,consumer_version,window_ordinal,source_digest,raw_result_sha256 "
                "FROM twin_note_revision_members WHERE revision_id=? ORDER BY member_ordinal", [rid]).fetchall()
            if not members or len(members) > MAX_MEMBERS or [r[0] for r in members] != list(range(len(members))):
                raise TwinNoteIntegrityError
            membership_rows, attributed, seen, all_sources = [], [], set(), set()
            for ordinal, investigation_id, window_id, consumer_version, window_ordinal, source_digest, raw_sha in members:
                window = con.execute(
                    "SELECT investigation_id,consumer_version,ordinal,source_event_ids_json,source_digest,request_json,"
                    "request_sha256,state,raw_result,raw_result_sha256 FROM note_taker_windows WHERE window_id=?", [window_id]).fetchall()
                if len(window) != 1:
                    raise TwinNoteIntegrityError
                wi, wc, wo, sources_json, ws_digest, request_json, request_sha, state, raw, ws_raw_sha = window[0]
                if (wi, wc, wo, ws_digest, ws_raw_sha) != (investigation_id, consumer_version, window_ordinal, source_digest, raw_sha):
                    raise TwinNoteIntegrityError
                if state != "completed" or raw is None or _sha(raw) != raw_sha or _sha(request_json) != request_sha or _sha(sources_json) != source_digest:
                    raise TwinNoteIntegrityError
                sources, request = json.loads(sources_json), json.loads(request_json)
                if (_canonical(sources) != sources_json or _canonical(request) != request_json or
                        type(sources) is not list or not sources or any(type(x) is not str for x in sources) or
                        request.get("investigation_id") != investigation_id or request.get("source_event_ids") != sources):
                    raise TwinNoteIntegrityError
                membership_rows.append({"member_ordinal": ordinal, "investigation_id": investigation_id,
                    "window_id": window_id, "consumer_version": consumer_version, "window_ordinal": window_ordinal,
                    "source_digest": source_digest, "request_sha256": request_sha, "raw_result_sha256": raw_sha})
                all_sources.update(sources)
                for note in parse_notes_response(raw, canonical_event_ids=sources):
                    note_key = _canonical({"text": note.text, "confidence": note.confidence,
                                           "source_event_ids": list(note.source_event_ids)})
                    if note_key in seen:
                        continue
                    seen.add(note_key)
                    attributed.append({"text": note.text, "confidence": note.confidence,
                        "source_event_ids": list(note.source_event_ids), "investigation_id": investigation_id,
                        "window_id": window_id})
            if _sha(_canonical(membership_rows)) != membership or len(attributed) > MAX_NOTES or len(all_sources) > MAX_SOURCE_EVENTS:
                raise TwinNoteIntegrityError
            revision_identity = _canonical({"account_id": account_id, "asset_id": asset_id,
                "supersedes_revision_id": predecessor, "membership_sha256": membership,
                "compressor_version": COMPRESSOR_VERSION, "renderer_version": RENDERER_VERSION})
            if rid != "tnr-" + _sha(revision_identity)[:32]:
                raise TwinNoteIntegrityError
            expected_body = ResearchArtifactBody(investigation_id=rid,
                problem_question=f"Compressed twin notes for {asset_id}", insights=[], open_questions=[],
                synthesis_excerpt=None, synthesis_withheld=True, source_event_ids=sorted(all_sources),
                agent_notes=[f"[{r['investigation_id']} | {r['window_id']} | {','.join(r['source_event_ids'])}] {r['text']}" for r in attributed])
            if expected_body.model_dump(mode="json") != body.model_dump(mode="json"):
                raise TwinNoteIntegrityError
            expected_html = _static_html(body, revision_id=rid, authority=COMPRESSION_AUTHORITY, attributions=attributed)
            expected_relative = f"{_sha(account_id)[:24]}/{_sha(asset_id)[:24]}/{rid}.html"
            payload = bytes(blob)
            if payload != expected_html or _sha(payload) != html_sha or relative != expected_relative:
                raise TwinNoteIntegrityError
            effects = con.execute("SELECT effect_id,expected_path,expected_sha256,state FROM twin_note_publication_effects WHERE revision_id=?", [rid]).fetchall()
            effect_id = "tne-" + _sha(_canonical([rid, relative, html_sha]))[:32]
            if effects != [(effect_id, relative, html_sha, "published")]:
                raise TwinNoteIntegrityError
            if note_count != len(attributed) or source_count != len(all_sources):
                raise TwinNoteIntegrityError
        except TwinNoteIntegrityError:
            raise
        except Exception as exc:
            raise TwinNoteIntegrityError from exc
        return VerifiedRevision(rid, asset_id, predecessor, body_sha, bytes(blob), html_sha,
                                note_count, source_count, body)

    def _verify_chain(self, con: Any, account_id: str, asset_id: str,
                      cache: dict[tuple[str, str], dict[str, VerifiedRevision]] | None = None,
                      ) -> dict[str, VerifiedRevision]:
        """Verify the complete owner/asset component as one bounded linear chain."""
        key = (account_id, asset_id)
        if cache is not None and key in cache:
            return cache[key]
        rows = con.execute(
            "SELECT revision_id,supersedes_revision_id FROM twin_note_revisions "
            "WHERE account_id=? AND asset_id=?", [account_id, asset_id]).fetchall()
        if not rows:
            raise TwinNoteUnavailable
        if len(rows) > MAX_HISTORY:
            raise TwinNoteIntegrityError
        ids = {row[0] for row in rows}
        if len(ids) != len(rows):
            raise TwinNoteIntegrityError
        # Inspect references globally: a foreign owner/asset successor pointing into
        # this component is corruption too, even though an owner-scoped query hides it.
        inbound = con.execute(
            "SELECT revision_id,account_id,asset_id,supersedes_revision_id FROM twin_note_revisions "
            "WHERE supersedes_revision_id IN (SELECT revision_id FROM twin_note_revisions WHERE account_id=? AND asset_id=?)",
            [account_id, asset_id]).fetchall()
        if any(row[1] != account_id or row[2] != asset_id for row in inbound):
            raise TwinNoteIntegrityError
        successors: dict[str, list[str]] = {rid: [] for rid in ids}
        roots: list[str] = []
        for rid, predecessor in rows:
            if predecessor is None:
                roots.append(rid)
            elif predecessor not in ids:
                raise TwinNoteIntegrityError
            else:
                successors[predecessor].append(rid)
        if len(roots) != 1 or any(len(values) > 1 for values in successors.values()):
            raise TwinNoteIntegrityError
        verified: dict[str, VerifiedRevision] = {}
        seen: set[str] = set()
        rid: str | None = roots[0]
        while rid is not None:
            if rid in seen or len(seen) >= MAX_HISTORY:
                raise TwinNoteIntegrityError
            seen.add(rid)
            revision = self._verify_revision(con, account_id, rid)
            if revision.asset_id != asset_id:
                raise TwinNoteIntegrityError
            verified[rid] = revision
            children = successors[rid]
            rid = children[0] if children else None
        if seen != ids:
            raise TwinNoteIntegrityError
        if cache is not None:
            cache[key] = verified
        return verified

    def _verified_exact(self, con: Any, account_id: str, revision_id: str,
                        cache: dict[tuple[str, str], dict[str, VerifiedRevision]] | None = None,
                        ) -> VerifiedRevision:
        _identity(revision_id, "tnr-")
        owner = con.execute(
            "SELECT asset_id FROM twin_note_revisions WHERE account_id=? AND revision_id=?",
            [account_id, revision_id]).fetchall()
        if len(owner) != 1:
            raise TwinNoteUnavailable
        chain = self._verify_chain(con, account_id, owner[0][0], cache)
        try:
            return chain[revision_id]
        except KeyError as exc:
            raise TwinNoteIntegrityError from exc

    def revision(self, account_id: str, revision_id: str) -> VerifiedRevision:
        with connect_read(self.db_path) as con:
            return self._verified_exact(con, account_id, revision_id)

    def _history(self, con: Any, account_id: str, asset_id: str) -> list[VerifiedRevision]:
        chain = self._verify_chain(con, account_id, asset_id)
        by_predecessor = {revision.supersedes_revision_id: revision for revision in chain.values()}
        result: list[VerifiedRevision] = []
        current = by_predecessor[None]
        while True:
            result.append(current)
            successor = by_predecessor.get(current.revision_id)
            if successor is None:
                break
            current = successor
        result.reverse()
        return result

    def assets(self, account_id: str) -> list[dict[str, Any]]:
        with connect_read(self.db_path) as con:
            assets = con.execute("SELECT DISTINCT asset_id FROM twin_note_revisions WHERE account_id=? ORDER BY asset_id LIMIT ?", [account_id, MAX_ASSETS + 1]).fetchall()
            if len(assets) > MAX_ASSETS:
                raise TwinNoteIntegrityError
            return [{"asset_id": aid, "asset_label": aid, "current_revision": (history := self._history(con, account_id, aid))[0].metadata(), "revision_count": len(history)} for (aid,) in assets]

    def history(self, account_id: str, asset_id: str) -> list[VerifiedRevision]:
        if type(asset_id) is not str or not asset_id or asset_id != asset_id.strip() or len(asset_id) > 512:
            raise TwinNoteUnavailable
        with connect_read(self.db_path) as con:
            return self._history(con, account_id, asset_id)

    @staticmethod
    def _composition_html(composition_id: str, members: list[VerifiedRevision], ledger: list[list[Any]]) -> bytes:
        metadata = _canonical({"composition_id": composition_id, "composition_version": 1, "members": ledger}).replace("<", "\\u003c")
        sections = "".join(
            f'<section data-member-ordinal="{i}" data-revision-id="{html.escape(r.revision_id, quote=True)}">'
            f'<h2>{i + 1}. {html.escape(r.asset_id)}</h2><p>Revision {html.escape(r.revision_id)} · '
            f'{r.note_count} notes · {r.source_count} sources · <a href="/research/twin-notes/revisions/{r.revision_id}">open exact revision</a></p>'
            f'<ol>{"".join(f"<li>{html.escape(note)}</li>" for note in r.body.agent_notes)}</ol></section>'
            for i, r in enumerate(members))
        return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Twin-note composition</title><style>body{max-width:860px;margin:auto;padding:28px;font:16px/1.55 system-ui}'
            'section{border-top:1px solid #999;padding:18px 0}</style></head><body><main>'
            f'<h1>Twin-note composition</h1>{sections}<script type="application/json" id="antiek-twin-composition-v1">{metadata}</script>'
            f'<footer>Immutable composition {html.escape(composition_id)}</footer></main></body></html>').encode()

    def compose(self, account_id: str, revision_ids: Sequence[str]) -> dict[str, Any]:
        if type(revision_ids) not in (list, tuple) or not 2 <= len(revision_ids) <= 20:
            raise TwinNoteInputError("revision_ids must contain 2 to 20 exact revisions")
        try:
            ids = [_identity(value, "tnr-") for value in revision_ids]
        except TwinNoteUnavailable as exc:
            raise TwinNoteInputError("revision_ids must contain canonical revision IDs") from exc
        if len(set(ids)) != len(ids):
            raise TwinNoteInputError("duplicate revisions are forbidden")
        with connect_write(self.db_path, purpose="twin_note/compose") as con:
            con.execute("BEGIN TRANSACTION")
            try:
                cache: dict[tuple[str, str], dict[str, VerifiedRevision]] = {}
                revisions = [self._verified_exact(con, account_id, rid, cache) for rid in ids]
                ledger = [[i, r.revision_id, r.asset_id, r.body_sha256, r.html_sha256] for i, r in enumerate(revisions)]
                ordered_sha = _sha(_canonical(ledger))
                composition_id = "tnc-" + _sha(_canonical([account_id, COMPOSITION_VERSION, ordered_sha]))[:32]
                rendered = self._composition_html(composition_id, revisions, ledger)
                rendered_sha = _sha(rendered)
                created = (datetime(2000, 1, 1, tzinfo=UTC) + timedelta(seconds=int(_sha(composition_id)[:8], 16))).replace(tzinfo=None)
                existing = con.execute("SELECT composition_id,account_id,composition_version,ordered_members_sha256,html_bytes,html_sha256,member_count,created_at FROM twin_note_compositions WHERE composition_id=?", [composition_id]).fetchone()
                immutable = (composition_id, account_id, 1, ordered_sha, rendered, rendered_sha, len(ids), created)
                expected_members = [(composition_id, *row) for row in ledger]
                if existing is None:
                    con.execute("INSERT INTO twin_note_compositions VALUES (?,?,?,?,?,?,?,?)", list(immutable))
                    for row in expected_members:
                        con.execute("INSERT INTO twin_note_composition_members VALUES (?,?,?,?,?,?)", list(row))
                else:
                    if existing != immutable or con.execute("SELECT composition_id,member_ordinal,revision_id,asset_id,body_sha256,html_sha256 FROM twin_note_composition_members WHERE composition_id=? ORDER BY member_ordinal", [composition_id]).fetchall() != expected_members:
                        raise TwinNoteIntegrityError
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
        return {"composition_id": composition_id, "members": [r.metadata() | {"member_ordinal": i} for i, r in enumerate(revisions)],
                "url": f"/research/twin-notes/compositions/{composition_id}"}

    def composition(self, account_id: str, composition_id: str) -> bytes:
        _identity(composition_id, "tnc-")
        with connect_read(self.db_path) as con:
            rows = con.execute("SELECT composition_version,ordered_members_sha256,html_bytes,html_sha256,member_count,created_at FROM twin_note_compositions WHERE account_id=? AND composition_id=?", [account_id, composition_id]).fetchall()
            if len(rows) != 1:
                raise TwinNoteUnavailable
            version, ordered_sha, blob, digest, count, created_at = rows[0]
            ledger_rows = con.execute("SELECT member_ordinal,revision_id,asset_id,body_sha256,html_sha256 FROM twin_note_composition_members WHERE composition_id=? ORDER BY member_ordinal", [composition_id]).fetchall()
            try:
                if version != 1 or count != len(ledger_rows) or not 2 <= count <= 20 or [x[0] for x in ledger_rows] != list(range(count)):
                    raise TwinNoteIntegrityError
                cache: dict[tuple[str, str], dict[str, VerifiedRevision]] = {}
                revisions = [self._verified_exact(con, account_id, row[1], cache) for row in ledger_rows]
                ledger = [list(row) for row in ledger_rows]
                if any((r.asset_id, r.body_sha256, r.html_sha256) != tuple(row[2:]) for r, row in zip(revisions, ledger_rows, strict=True)):
                    raise TwinNoteIntegrityError
                expected_id = "tnc-" + _sha(_canonical([account_id, 1, ordered_sha]))[:32]
                expected_created = (datetime(2000, 1, 1, tzinfo=UTC) + timedelta(seconds=int(_sha(composition_id)[:8], 16))).replace(tzinfo=None)
                rendered = self._composition_html(composition_id, revisions, ledger)
                if (_sha(_canonical(ledger)) != ordered_sha or expected_id != composition_id or
                        created_at != expected_created or bytes(blob) != rendered or _sha(rendered) != digest):
                    raise TwinNoteIntegrityError
                return bytes(blob)
            except TwinNoteIntegrityError:
                raise
            except Exception as exc:
                raise TwinNoteIntegrityError from exc


__all__ = ["TwinNoteInputError", "TwinNoteIntegrityError", "TwinNoteServingService", "TwinNoteUnavailable", "VerifiedRevision"]
