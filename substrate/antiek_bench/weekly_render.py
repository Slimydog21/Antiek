"""Render a week's benchmark results to self-contained HTML (ask #11 presentation).

The operator's vision (ask #11): *"...a benchmark called Antiek-bench that
benchmarked performance (and presented it in settings) so that I can know on a
weekly basis what models are best at what tasks."* The execution stack produces
scored runs (task registry, scorer, runner, recorder); the routes return JSON.
But the operator wants to SEE the weekly verdict in Settings — which model won
each task family, by how much, and whether the week is complete or still
pending. THIS module is the pure renderer that turns a week's snapshot into a
single self-contained HTML document for that Settings panel.

**Native HTML, no JavaScript** — every task family is a ``<details><summary>``
block, collapsible by the browser's own semantics (the operator's HTML vision,
ask #6; mirrors the plan-tree renderer #1840). Fully controllable by coding
agents, no frontend framework.

**Pure** — no I/O, no clock, no network. Takes a :class:`WeeklyBenchSnapshot`
(the caller assembles it from the recorder's view records + the weekly
aggregator's output), returns an HTML string. ``generated_at_label`` is a
caller-resolved string (the renderer owns no clock). Every interpolated value is
``html.escape``d — model ids and task-family labels are config/operator-supplied
and treated as untrusted; the renderer never passes them through raw. Structural
tags are static literals, not interpolated.

**Honesty keystones (each is a test):**

1. **A pending/incomplete week is flagged, never hidden.** If any task family
   has incomplete runs (human-scored, awaiting confirmation) or no runs at all,
   the banner shows ``incomplete`` and each affected family shows a note. The
   operator never mistakes a half-finished week for a final verdict.
2. **A model with no completed runs is NOT ranked.** A fabricated mean score
   from zero runs is a lie. Such models appear in a separate "no completed runs"
   list, not in the ranking.
3. **Empty/unknown values shown honestly.** A ``None`` mean score renders as an
   em-dash (``&mdash;``), never as ``0.0`` or a blank. A task family with zero
   models renders an honest empty note, not a fabricated winner.
4. **"Best model" is only named when there is a real top score.** A tie at the
   top names all tied models (no arbitrary tie-break winner). A family where
   every model scored 0.0 still names the top — the score is real, just low.
5. **Provenance is real.** The footer carries the week id, the source record
   count, the generated-at label, and honesty notes — so the operator can trace
   how the verdict was built. The renderer never invents provenance.
6. **The snapshot's ``incomplete`` flag is authoritative.** The renderer trusts
   the caller's flag (the caller knows the recorder state); it also surfaces a
   per-family note when ``completed_runs == 0`` so a caller bug (flag says
   complete but a family has no runs) is visible, not silent.

**Composition:** the caller builds the snapshot from the recorder's
:class:`ViewRecord`-shaped outputs (#1829) + the weekly aggregator (#1831); this
module renders it. The recursive rewrite engines (#1831 weights, #1843
structure) consume the same snapshot to decide next week's changes — the HTML is
the human-facing view of the same data the loop learns from.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelScore:
    """One model's aggregate result in one task family (or overall)."""

    model_id: str
    mean_score: float | None  # None = no completed runs (pending/unknown)
    completed_runs: int
    pending_runs: int = 0
    notes: str = ""


@dataclass(frozen=True)
class TaskFamilyResult:
    """One task family's weekly result: ranked models + the verdict."""

    task_family: str
    models: tuple[ModelScore, ...]  # caller-supplied order; renderer ranks by score
    scoring_method: str = ""  # "exact" / "rubric" / "human" — surfaced for context


@dataclass(frozen=True)
class WeeklyBenchSnapshot:
    """A full week's bench results, ready to render."""

    week_id: str
    generated_at_label: str  # caller-resolved (renderer owns no clock)
    task_families: tuple[TaskFamilyResult, ...]
    overall_ranking: tuple[ModelScore, ...]  # cross-task aggregate, caller-supplied
    source_record_count: int  # how many view records fed this snapshot
    incomplete: bool  # authoritative: any family has pending/incomplete runs
    honesty_notes: tuple[str, ...] = field(default_factory=tuple)


_PAGE_CSS = """
:root { --stone-900:#1c1917; --stone-600:#57534e; --stone-200:#e7e5e4; --stone-50:#fafaf9;
  --amber-50:#fffbeb; --blue-700:#1d4ed8; --green-700:#15803d; --amber-700:#b45309; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.55; color: var(--stone-900); background: var(--stone-50); margin: 0; padding: 24px; }
main { max-width: 820px; margin: 0 auto; }
h1 { font-family: Charter, Georgia, serif; font-size: 1.7rem; margin-bottom: 4px; }
.kicker { color: var(--stone-600); font-size: 0.85rem; }
.banner { padding: 12px 16px; border-radius: 6px; margin: 16px 0; font-weight: 600; }
.banner.complete { background: #f0fdf4; border: 1px solid var(--green-700); color: var(--green-700); }
.banner.incomplete { background: var(--amber-50); border: 1px solid var(--amber-700); color: var(--amber-700); }
section { margin: 24px 0; }
h2 { font-size: 1.15rem; border-bottom: 1px solid var(--stone-200); padding-bottom: 6px; }
details { border: 1px solid var(--stone-200); background: #fff; border-radius: 6px;
  margin: 8px 0; padding: 8px 14px; }
details > summary { cursor: pointer; font-weight: 600; }
details[open] > summary { margin-bottom: 8px; }
table { width: 100%; border-collapse: collapse; margin: 6px 0; }
th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--stone-200); font-size: 0.92rem; }
th { color: var(--stone-600); font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.04em; }
.score { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.best { color: var(--green-700); font-weight: 700; }
.method { font-size: 0.75rem; color: var(--stone-600); }
.note { font-size: 0.82rem; color: var(--amber-700); margin: 4px 0; }
.empty { color: var(--stone-600); font-style: italic; }
footer { margin-top: 32px; font-size: 0.8rem; color: var(--stone-600); border-top: 1px solid var(--stone-200); padding-top: 12px; }
"""


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _fmt_score(score: float | None) -> str:
    if score is None:
        return "&mdash;"
    return f"{score:.3f}"


def _ranked(models: tuple[ModelScore, ...]) -> tuple[ModelScore, ...]:
    """Rank models by mean_score descending; None-scores sort last.

    Stable sort preserves caller order within ties (no arbitrary reordering).
    """
    return tuple(sorted(models, key=lambda m: (m.mean_score is None, -(m.mean_score or 0.0))))


def _best_model_ids(ranked: tuple[ModelScore, ...]) -> tuple[str, ...]:
    """Return the model id(s) sharing the top COMPLETED score (ties included).

    Returns () when no model has a completed run (None top score). Does NOT
    fabricate a winner from pending runs.
    """
    completed = tuple(m for m in ranked if m.mean_score is not None)
    if not completed:
        return ()
    top = completed[0].mean_score
    return tuple(
        m.model_id for m in completed if m.mean_score == top
    )


def _render_model_rows(models: tuple[ModelScore, ...], best_ids: tuple[str, ...]) -> str:
    ranked = _ranked(models)
    best_set = set(best_ids)
    rows: list[str] = []
    no_runs: list[ModelScore] = []
    for model in ranked:
        if model.mean_score is None:
            no_runs.append(model)
            continue
        is_best = model.model_id in best_set
        rows.append(
            "<tr>"
            f'<td class="{"best" if is_best else ""}">{_esc(model.model_id)}{" &#9733;" if is_best else ""}</td>'
            f'<td class="score">{_fmt_score(model.mean_score)}</td>'
            f"<td>{model.completed_runs}</td>"
            f"<td>{model.pending_runs}</td>"
            f"<td>{_esc(model.notes) if model.notes else ''}</td>"
            "</tr>"
        )
    parts: list[str] = []
    if rows:
        parts.append(
            "<table><thead><tr>"
            "<th>Model</th><th>Mean score</th><th>Completed</th><th>Pending</th><th>Notes</th>"
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
        )
    else:
        parts.append('<p class="empty">No completed runs this week.</p>')
    if no_runs:
        ids = ", ".join(_esc(m.model_id) for m in no_runs)
        parts.append(
            f'<p class="note">No completed runs (pending/unknown): {ids}.</p>'
        )
    return "".join(parts)


def _render_task_family(family: TaskFamilyResult) -> str:
    ranked = _ranked(family.models)
    best_ids = _best_model_ids(ranked)
    has_completed = any(m.mean_score is not None for m in family.models)
    family_incomplete = not has_completed or any(m.pending_runs > 0 for m in family.models)

    if best_ids:
        verdict = "Best: " + ", ".join(_esc(mid) for mid in best_ids)
    elif has_completed:
        verdict = '<span class="empty">No model scored above pending.</span>'
    else:
        verdict = '<span class="empty">No completed runs.</span>'

    method_tag = f' <span class="method">({_esc(family.scoring_method)})</span>' if family.scoring_method else ""
    summary = f"{_esc(family.task_family)}{method_tag} &mdash; {verdict}"

    body = _render_model_rows(family.models, best_ids)
    if family_incomplete:
        body = '<p class="note">This family has pending/incomplete runs.</p>' + body

    open_attr = ""  # collapsed by default; operator expands what they care about
    return (
        f'<details{open_attr}><summary>{summary}</summary>'
        f'<div class="family-body">{body}</div></details>'
    )


def render_weekly_bench(snapshot: WeeklyBenchSnapshot) -> str:
    """Render a weekly bench snapshot to a self-contained HTML document.

    Pure: no I/O, no clock, no network. Every interpolated value is escaped.
    """
    banner_cls = "incomplete" if snapshot.incomplete else "complete"
    banner_text = "Week incomplete — some runs are pending." if snapshot.incomplete else "Week complete."
    banner = f'<div class="banner {banner_cls}">{_esc(banner_text)}</div>'

    family_blocks = "".join(_render_task_family(f) for f in snapshot.task_families)
    if not snapshot.task_families:
        family_blocks = '<p class="empty">No task families recorded this week.</p>'

    overall_rows = _render_model_rows(snapshot.overall_ranking, _best_model_ids(_ranked(snapshot.overall_ranking)))
    if snapshot.overall_ranking:
        overall_html = (
            '<section><h2>Overall ranking</h2>'
            "<p class='kicker'>Cross-task aggregate — which model won the most this week.</p>"
            f"{overall_rows}</section>"
        )
    else:
        overall_html = '<section><h2>Overall ranking</h2><p class="empty">No overall data this week.</p></section>'

    notes_html = ""
    if snapshot.honesty_notes:
        items = "".join(f"<li>{_esc(note)}</li>" for note in snapshot.honesty_notes)
        notes_html = f"<ul>{items}</ul>"

    footer = (
        "<footer>"
        f"<div>Week: <code>{_esc(snapshot.week_id)}</code></div>"
        f"<div>Source records: {snapshot.source_record_count}</div>"
        f"<div>Generated: {_esc(snapshot.generated_at_label)}</div>"
        "<div>Renderer: pure HTML, no JavaScript. All values escaped.</div>"
        f"{notes_html}"
        "</footer>"
    )

    return (
        "<!DOCTYPE html>"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>Antiek-bench — {_esc(snapshot.week_id)}</title>"
        f"<style>{_PAGE_CSS}</style></head><body><main>"
        f'<p class="kicker">Antiek-bench weekly report</p>'
        f"<h1>Week {_esc(snapshot.week_id)}</h1>"
        f"{banner}"
        '<section><h2>Task families</h2>'
        f"{family_blocks}</section>"
        f"{overall_html}"
        f"{footer}"
        "</main></body></html>"
    )


__all__ = [
    "ModelScore",
    "TaskFamilyResult",
    "WeeklyBenchSnapshot",
    "render_weekly_bench",
]
