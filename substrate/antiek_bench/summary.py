"""HTML human-readable summary of a bench run."""

from __future__ import annotations

from typing import Any

from substrate.engagement_spine.project import project_to_html

from .store import BenchStore


def project_run_html(run_id: str, *, store: BenchStore) -> str:
    """Project a stored run to HTML. Scores and task labels must appear in output."""
    run = store.get_run(run_id)
    if run is None:
        raise KeyError(f"unknown run_id: {run_id}")

    week_id = str(run.get("week_id") or "")
    suite_version = str(run.get("suite_version") or "")
    model_id = str(run.get("model_id") or "")
    mean = run.get("mean_score")
    by_class = run.get("by_task_class") or {}
    scores = run.get("scores") or []

    lines: list[str] = [
        f"Antiek-bench run {run_id}",
        f"Week: {week_id} · Suite: {suite_version} · Model: {model_id}",
        f"Mean score: {mean}",
    ]
    for tc, sc in sorted(by_class.items()):
        lines.append(f"Task class {tc}: {sc}")
    for s in scores:
        lines.append(
            f"Item {s.get('item_id')} [{s.get('task_class')}] score={s.get('score')}"
        )

    content: list[dict[str, Any]] = [
        {
            "type": "heading",
            "attrs": {"level": 1},
            "content": [{"type": "text", "text": "Antiek-bench results"}],
        }
    ]
    for line in lines:
        content.append(
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": line}],
            }
        )
    doc_model = {"type": "doc", "content": content}
    html = project_to_html(doc_model, document_id=run_id, creator="antiek_bench")
    if not html or not html.strip():
        raise RuntimeError("empty HTML summary")
    if html.lstrip().lower().startswith("%pdf"):
        raise RuntimeError("PDF is not a valid bench view surface")
    # Content properties
    if suite_version and suite_version not in html:
        raise RuntimeError("suite_version missing from HTML summary")
    if model_id and model_id not in html:
        raise RuntimeError("model_id missing from HTML summary")
    return html
