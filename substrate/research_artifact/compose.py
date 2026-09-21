"""Compose multiple investigations into one HTML index (view-layer merge)."""

from __future__ import annotations

import html
from dataclasses import dataclass
from pathlib import Path

from .build_body import build_body
from .export import export_research_artifact
from .paths import compose_path_for, draft_merge_path_for


@dataclass(frozen=True)
class ComposeMember:
    investigation_id: str
    content_hash: str
    artifact_path: Path
    twin_notes_path: Path


@dataclass(frozen=True)
class ComposeResult:
    path: Path
    draft_merge_path: Path | None
    members: list[ComposeMember]
    hash_conflicts: list[tuple[str, str]]


def compose_artifacts(
    investigation_ids: list[str],
    *,
    db_path: str | None = None,
    events_dir: str | None = None,
    write_index: bool = True,
    write_draft_merge: bool = False,
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
            twin_notes_path=res.twin_notes_path,
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
                f"<code>{html.escape(m.content_hash[:12])}</code> "
                f"<a href=\"file://{html.escape(str(m.twin_notes_path))}\">notes twin</a></li>"
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

    draft_path: Path | None = None
    if write_draft_merge:
        draft_path = _write_draft_merge(
            investigation_ids,
            members=members,
            db_path=db_path,
            events_dir=events_dir,
            conflicts=conflicts,
        )

    return ComposeResult(
        path=out_path,
        draft_merge_path=draft_path,
        members=members,
        hash_conflicts=conflicts,
    )


def _write_draft_merge(
    investigation_ids: list[str],
    *,
    members: list[ComposeMember],
    db_path: str | None,
    events_dir: str | None,
    conflicts: list[tuple[str, str]],
) -> Path:
    bodies = [
        build_body(iid, db_path=db_path, events_dir=events_dir)
        for iid in investigation_ids
    ]
    sections = ""
    for member, body in zip(members, bodies, strict=True):
        findings = "".join(
            f"<li>{html.escape(ins.text)} <span>{html.escape(ins.node_id)}</span></li>"
            for ins in body.insights
        ) or "<li><em>No findings yet.</em></li>"
        questions = "".join(
            f"<li>{html.escape(q.text)} <span>{html.escape(q.node_id)}</span></li>"
            for q in body.open_questions
        ) or "<li><em>No open questions yet.</em></li>"
        notes = "".join(
            f"<li>{html.escape(note)}</li>"
            for note in body.agent_notes
            if (note or "").strip()
        ) or "<li><em>No agent notes yet.</em></li>"
        sections += f"""
<section data-investigation-id="{html.escape(body.investigation_id)}">
<h2>{html.escape(body.problem_question)}</h2>
<p><a href="file://{html.escape(str(member.artifact_path))}">artifact</a> ·
<a href="file://{html.escape(str(member.twin_notes_path))}">notes twin</a> ·
<code>{html.escape(member.content_hash[:12])}</code></p>
<h3>Findings</h3><ul>{findings}</ul>
<h3>Open questions</h3><ul>{questions}</ul>
<h3>Agent notes</h3><ul>{notes}</ul>
</section>"""
    conflict_block = ""
    if conflicts:
        conflict_block = (
            "<section><h2>Hash conflicts requiring review</h2><ul>"
            + "".join(
                f"<li>{html.escape(a)} vs {html.escape(b)}</li>"
                for a, b in conflicts
            )
            + "</ul></section>"
        )
    index_path = compose_path_for(*investigation_ids)
    draft_path = draft_merge_path_for(*investigation_ids)
    html_text = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Draft merge — {len(members)} research artifacts</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.55; margin: 0; padding: 24px; background: #fafaf9; color: #1c1917; }}
main {{ max-width: 860px; margin: 0 auto; }}
section {{ background: #fff; border: 1px solid #e7e5e4; border-radius: 6px; margin: 16px 0; padding: 16px 20px; }}
.kicker, span {{ color: #57534e; font-size: 0.85rem; }}
</style>
</head>
<body>
<main data-draft-merge="true" data-source-count="{len(members)}">
<p class="kicker">Draft merge review · no graph mutation · ANT-AHT</p>
<h1>Draft merge of {len(members)} research artifacts</h1>
<p>This page combines exported artifacts for review before any graph/write merge. It does not mutate insights, questions, notes, or source artifacts.</p>
<p><a href="file://{html.escape(str(index_path))}">Open compose index</a></p>
{conflict_block}
{sections}
</main>
</body>
</html>
"""
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(html_text, encoding="utf-8")
    return draft_path
