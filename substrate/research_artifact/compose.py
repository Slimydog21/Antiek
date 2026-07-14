"""Compose multiple investigations into one HTML index (view-layer merge)."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .build_body import build_body
from .export import build_html_only, export_research_artifact
from .paths import compose_dir, compose_draft_path, compose_manifest_path, compose_path_for

COMPOSE_SCHEMA_VERSION = 1
MAX_COMPOSE_MEMBERS = 32


@dataclass(frozen=True)
class ComposeMember:
    investigation_id: str
    content_hash: str
    artifact_path: Path


@dataclass(frozen=True)
class ComposeResult:
    path: Path
    members: list[ComposeMember]
    hash_conflicts: list[tuple[str, str]]
    compose_id: str | None = None
    selection_fingerprint: str | None = None
    reused: bool = False


class StaleComposePreview(ValueError):
    pass


def preview_artifacts(
    investigation_ids: list[str], *, db_path: str | None = None,
    events_dir: str | None = None,
) -> ComposeResult:
    """Freeze an ordered selection against canonical bodies, without writes."""
    if not 2 <= len(investigation_ids) <= MAX_COMPOSE_MEMBERS:
        raise ValueError(f"select between 2 and {MAX_COMPOSE_MEMBERS} researches")
    if len(set(investigation_ids)) != len(investigation_ids):
        raise ValueError("duplicate investigation ids are not allowed")
    members: list[ComposeMember] = []
    by_hash: dict[str, list[str]] = {}
    for iid in investigation_ids:
        body = build_body(iid, db_path=db_path, events_dir=events_dir)
        content_hash = body.content_hash()
        members.append(ComposeMember(iid, content_hash, Path()))
        by_hash.setdefault(content_hash, []).append(iid)
    conflicts = [(ids[0], iid) for ids in by_hash.values() for iid in ids[1:]]
    fingerprint = _fingerprint(members)
    compose_id = f"cmp-{fingerprint[:24]}"
    return ComposeResult(
        path=compose_draft_path(compose_id), members=members,
        hash_conflicts=conflicts, compose_id=compose_id,
        selection_fingerprint=fingerprint,
    )


def create_compose_draft(
    investigation_ids: list[str], *, expected_fingerprint: str,
    db_path: str | None = None, events_dir: str | None = None,
) -> ComposeResult:
    """Atomically persist an immutable, idempotent HTML compose index."""
    result = preview_artifacts(investigation_ids, db_path=db_path, events_dir=events_dir)
    if result.selection_fingerprint != expected_fingerprint:
        raise StaleComposePreview("research content changed; review the selection again")
    assert result.compose_id is not None
    root = compose_dir()
    root.mkdir(parents=True, exist_ok=True)
    target = root / result.compose_id
    with _compose_lock():
        if compose_manifest_path(result.compose_id).is_file() and result.path.is_file():
            return ComposeResult(**{**result.__dict__, "reused": True})
        rendered_members: list[str] = []
        for member in result.members:
            body, rendered = build_html_only(member.investigation_id, db_path=db_path, events_dir=events_dir)
            if body.content_hash() != member.content_hash:
                raise StaleComposePreview("research content changed while creating the draft")
            rendered_members.append(_static_member_html(rendered))
        manifest = {
            "schema_version": COMPOSE_SCHEMA_VERSION,
            "compose_id": result.compose_id,
            "selection_fingerprint": result.selection_fingerprint,
            "members": [{"investigation_id": m.investigation_id, "content_hash": m.content_hash} for m in result.members],
            "hash_conflicts": [list(pair) for pair in result.hash_conflicts],
        }
        stage = Path(tempfile.mkdtemp(prefix=f".{result.compose_id}.", dir=root))
        try:
            (stage / "members").mkdir()
            (stage / "index.html").write_text(render_compose_html(result), encoding="utf-8")
            (stage / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2), encoding="utf-8")
            for index, rendered in enumerate(rendered_members):
                (stage / "members" / f"{index}.html").write_text(rendered, encoding="utf-8")
            os.rename(stage, target)
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise
    return result


def load_compose_draft(compose_id: str) -> ComposeResult:
    path = compose_manifest_path(compose_id)
    if not path.is_file():
        raise FileNotFoundError(compose_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != COMPOSE_SCHEMA_VERSION or data.get("compose_id") != compose_id:
        raise ValueError("invalid compose manifest")
    return ComposeResult(
        path=compose_draft_path(compose_id),
        members=[ComposeMember(str(m["investigation_id"]), str(m["content_hash"]), Path()) for m in data["members"]],
        hash_conflicts=[tuple(pair) for pair in data.get("hash_conflicts", [])],
        compose_id=compose_id, selection_fingerprint=str(data["selection_fingerprint"]), reused=True,
    )


def delete_compose_draft(compose_id: str) -> None:
    target = compose_draft_path(compose_id).parent
    with _compose_lock():
        if not target.is_dir():
            raise FileNotFoundError(compose_id)
        shutil.rmtree(target)


def render_compose_html(result: ComposeResult) -> str:
    rows = "".join(
        '<li><a href="member/' + str(index) + '">' +
        html.escape(m.investigation_id) + '</a><code>' + html.escape(m.content_hash) + '</code></li>'
        for index, m in enumerate(result.members)
    )
    conflicts = ""
    if result.hash_conflicts:
        conflicts = "<section><h2>Identical canonical content</h2><ul>" + "".join(
            f"<li>{html.escape(a)} and {html.escape(b)}</li>" for a, b in result.hash_conflicts
        ) + "</ul></section>"
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Research compose draft</title>
<style>:root{{color-scheme:light dark}}body{{font:16px/1.55 ui-serif,Georgia,serif;max-width:70rem;margin:auto;padding:3rem}}h1,h2{{font-family:ui-sans-serif,system-ui,sans-serif}}li{{margin:1rem 0}}code{{display:block;font-size:.75rem;overflow-wrap:anywhere}}</style></head>
<body><header><p>Antiek · reversible HTML draft</p><h1>{len(result.members)} researches, held together</h1>
<p>This index preserves every source as a separate artifact. No AI ran and no body was flattened.</p></header>
<main><ol>{rows}</ol>{conflicts}</main></body></html>'''


def _fingerprint(members: list[ComposeMember]) -> str:
    raw = json.dumps({"schema_version": COMPOSE_SCHEMA_VERSION, "members": [[m.investigation_id, m.content_hash] for m in members]}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def _static_member_html(rendered: str) -> str:
    """Remove controls whose mutation/copy script is intentionally disabled."""
    rendered = re.sub(r"<script>(.*?)</script>", "", rendered, flags=re.DOTALL)
    rendered = re.sub(r'<button\b[^>]*>.*?</button>', "", rendered, flags=re.DOTALL)
    rendered = re.sub(r'<label for="note-input">.*?</label>', "", rendered, flags=re.DOTALL)
    return re.sub(r'<textarea id="note-input".*?</textarea>', "", rendered, flags=re.DOTALL)


@contextmanager
def _compose_lock():
    import fcntl

    lock_path = compose_dir() / ".lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def compose_artifacts(
    investigation_ids: list[str],
    *,
    db_path: str | None = None,
    events_dir: str | None = None,
    write_index: bool = True,
) -> ComposeResult:
    members: list[ComposeMember] = []
    by_hash: dict[str, str] = {}
    conflicts: list[tuple[str, str]] = []
    for iid in investigation_ids:
        res = export_research_artifact(
            iid,
            db_path=db_path,
            events_dir=events_dir,
            emit_event=False,
        )
        m = ComposeMember(
            investigation_id=iid,
            content_hash=res.content_hash,
            artifact_path=res.path,
        )
        members.append(m)
        prev = by_hash.get(res.content_hash)
        if prev and prev != iid:
            conflicts.append((prev, iid))
        else:
            by_hash[res.content_hash] = iid

    out_path = compose_path_for(*investigation_ids)
    if write_index:
        rows = ""
        for m in members:
            rows += (
                f"<li><a href=\"file://{html.escape(str(m.artifact_path))}\">"
                f"{html.escape(m.investigation_id)}</a> "
                f"<code>{html.escape(m.content_hash[:12])}</code></li>"
            )
        conflict_block = ""
        if conflicts:
            conflict_block = (
                "<section><h2>Hash collisions (review)</h2><ul>"
                + "".join(
                    f"<li>{html.escape(a)} vs {html.escape(b)}</li>"
                    for a, b in conflicts
                )
                + "</ul></section>"
            )
        index = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Compose — {len(members)} artifacts</title></head><body>
<h1>Composed research artifacts</h1>
<ul>{rows}</ul>{conflict_block}
</body></html>"""
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(index, encoding="utf-8")

    return ComposeResult(path=out_path, members=members, hash_conflicts=conflicts)
