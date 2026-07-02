#!/usr/bin/env python3
"""Generate ANT-AHT htmlspec (master + seven sprint pages). Idempotent."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
STYLE_PATH = Path("/Users/slimydog/.grok/skills/htmlspec/templates/style.css")
DATE = "2026-06-24"
CSS_BLOCK = f"<style>\n{STYLE_PATH.read_text()}\n</style>" if STYLE_PATH.is_file() else "<style></style>"


def wrap(title: str, body: str, wide: bool = False) -> str:
    cls = "page page--wide" if wide else "page"
    return (
        f"<!doctype html>\n<html lang=\"en\">\n<head>\n"
        f"<meta charset=\"utf-8\" />\n<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />\n"
        f"<title>{title}</title>\n{CSS_BLOCK}\n</head>\n<body>\n"
        f"<main class=\"{cls}\">\n{body}\n</main>\n</body>\n</html>\n"
    )


def rigor(h, f, r, d, de) -> str:
    return f"""<section class="block"><h2>Rigor — operating manual for this sprint</h2>
<div class="rigor">
<div class="rigor-card"><span class="label">1 · Intellectual honesty</span><h4>Calibrate confidence</h4><p>{h}</p></div>
<div class="rigor-card"><span class="label">2 · Fairness</span><h4>Steelman rejected alt</h4><p>{f}</p></div>
<div class="rigor-card"><span class="label">3 · Rigor</span><h4>Mechanical checks</h4><p>{r}</p></div>
<div class="rigor-card"><span class="label">4 · Diligence</span><h4>Read before write</h4><p>{d}</p></div>
<div class="rigor-card"><span class="label">5 · Defensibility</span><h4>Survives turnover</h4><p>{de}</p></div>
</div></section>"""


def milestones(items) -> str:
    out = ['<section class="block"><h2>Technical milestones</h2>']
    for i, (t, desc, crit, files) in enumerate(items, 1):
        cl = "".join(f"<li>{c}</li>" for c in crit)
        fl = "".join(f'<span class="file">{x}</span>' for x in files)
        out.append(f"""<div class="milestone"><div class="num">{i}</div><div>
<div class="title">{t}</div><p class="desc">{desc}</p>
<div class="criteria"><strong>Acceptance criteria</strong><ul>{cl}</ul></div>
<div class="files">{fl}</div></div></div>""")
    out.append("</section>")
    return "\n".join(out)


def sprint_page(
    sid,
    num,
    slug,
    title,
    tagline,
    wave,
    budget,
    p1,
    p2,
    pos,
    goal_extra,
    ms,
    rig,
    deps,
    ext,
    oos,
    gates,
    harness,
    status: str = "done",
) -> str:
    du = "".join(f"<li>{x}</li>" for x in deps) or '<li class="muted">None</li>'
    de = "".join(f"<li>{x}</li>" for x in ext)
    oo = "".join(f"<li>{x}</li>" for x in oos)
    gt = "".join(
        f"<tr><td><strong>{n}</strong></td><td><code>{c}</code></td><td>{e}</td></tr>"
        for n, c, e in gates
    )
    body = f"""<header class="hero">
<p class="eyebrow"><a href="index.html">&larr; Antiek HTML Transport</a> · Sprint {num}</p>
<h1>{title}</h1><p class="tagline">{tagline}</p>
<div class="meta-row">
<span class="tag tag--blue"><span class="dot"></span>Wave {wave}</span>
<span class="tag tag--{'green' if status == 'done' else 'yellow'}"><span class="dot"></span>{status}</span>
<span class="tag tag--grey">Budget: {budget}</span></div></header>
<section class="block"><h2>Parent context</h2><p>{p1}</p><p>{p2}</p>
<div class="callout callout--info"><strong>Position:</strong> {pos}</div></section>
<section class="block"><h2>Goal</h2><p><strong>{tagline}</strong></p><p>{goal_extra}</p></section>
{milestones(ms)}
{rigor(*rig)}
<section class="block"><h2>Dependencies</h2><div class="two-col">
<div><h3>Upstream</h3><ul>{du}</ul></div>
<div><h3>External</h3><ul>{de}</ul></div></div></section>
<section class="block"><h2>Out of scope</h2><ul>{oo}</ul></section>
<section class="block"><h2>Verification gates</h2>
<table class="spec"><thead><tr><th>Gate</th><th>Command</th><th>Expected</th></tr></thead><tbody>{gt}</tbody></table></section>
<section class="block" id="harness-hint" data-harness-pattern="{harness[0]}"
 data-harness-fanout-unit="{harness[1]}" data-harness-verifier-lenses="{harness[2]}"
 data-harness-rounds-floor="{harness[3]}" data-harness-rounds-cap="{harness[4]}">
<h2>Harness hint</h2><p>Pattern <code>{harness[0]}</code> · {harness[1]}</p></section>
<footer class="spec-footer">{sid} · <a href="index.html">Master spec</a> · {DATE}</footer>"""
    return wrap(f"{sid} · {title}", body)


def _sprint_card(num, slug, title, goal, wave, budget, st) -> str:
    tag = "tag--green" if st == "done" else "tag--yellow"
    return f"""<a class="sprint-card" href="sprint-{num}-{slug}.html">
<span class="id">SPR-AHT-{num}</span><span class="title">{title}</span><span class="goal">{goal}</span>
<span class="footer"><span class="tag tag--blue">Wave {wave}</span>
<span class="tag tag--grey">{budget}</span><span class="tag {tag}"><span class="dot"></span>{st}</span></span></a>"""


def master_index() -> str:
    cards = [
        ("01", "research-artifact-contract", "ResearchArtifact v1 contract", "Dual-channel HTML + JSON block.", 1, "3 milestones", "done"),
        ("02", "export-pipeline", "Export pipeline", "Disk write + artifact.generated event.", 1, "3 milestones", "done"),
        ("03", "agent-transport-protocol", "Agent transport protocol", "Cross-window handoff doc + templates.", 2, "2 milestones", "done"),
        ("04", "ingest-reader-snapshot", "Ingest reader snapshot", "Sanitized HTML beside URL ingest.", 2, "3 milestones", "done"),
        ("05", "compose-merge", "Compose / merge index", "Multi-investigation HTML index.", 3, "2 milestones", "done"),
        ("06", "write-bridge-api", "Write bridge + API", "Outline blocks + FastAPI routes.", 3, "3 milestones", "done"),
        ("07", "book-reader-snapshot", "Book reader snapshot", "PDF ingest → readable HTML beside chunks.", 2, "2 milestones", "done"),
    ]
    by_wave: dict[int, list[str]] = {1: [], 2: [], 3: []}
    for num, slug, title, goal, wave, budget, st in cards:
        by_wave[wave].append(_sprint_card(num, slug, title, goal, wave, budget, st))
    body = f"""<header class="hero"><p class="eyebrow">Master spec · ANT-AHT</p>
<h1>Antiek HTML Transport</h1>
<p class="tagline">Profile B — agent-friendly HTML lenses on DuckDB truth (Thariq thesis).</p>
<div class="meta-row"><span class="tag tag--green"><span class="dot"></span>exec-2 complete</span>
<span class="tag tag--grey">7 sprints · 3 waves · {DATE}</span></div></header>
<section class="block"><h2>Architectural fork (ratified)</h2>
<ul>
<li><strong>Canonical truth:</strong> DuckDB graph + typed event log — never HTML-primary.</li>
<li><strong>Profile A:</strong> htmlspec execution pages (Lemon UI, rigor cards, harness hints).</li>
<li><strong>Profile B:</strong> <code>ResearchArtifact</code> transport — per-investigation HTML + machine JSON.</li>
<li><strong>Profile C:</strong> Operator <code>docs/html/</code> (stone §5.5 notebook aesthetic).</li>
<li><strong>Merge semantics:</strong> graph/pack first; HTML compose = index + content-hash conflicts.</li>
</ul>
<p>Landscape catalog: <a href="../../html/html-landscape.html">docs/html/html-landscape.html</a></p>
</section>
<section class="block"><h2>Sprint roster</h2>
<div class="wave-band">Wave 1 — contract + export</div><div class="sprint-grid">{''.join(by_wave[1])}</div>
<div class="wave-band">Wave 2 — protocol + ingest (URL + book)</div><div class="sprint-grid">{''.join(by_wave[2])}</div>
<div class="wave-band">Wave 3 — compose + Write bridge</div><div class="sprint-grid">{''.join(by_wave[3])}</div>
</section>
<section class="block" id="harness-hint-run" data-harness-default-pattern="inline">
<h2>Harness</h2><p>Exec-2: pytest ANT-AHT suite + optional <code>ANTIEK_EXPORT_RESEARCH_ARTIFACT</code> post-complete hook.</p>
<pre><code>./.venv/bin/python -m pytest tests/test_research_artifact_*.py tests/test_reader_snapshot.py tests/test_artifact_routes.py -q</code></pre>
</section>"""
    return wrap("ANT-AHT · Antiek HTML Transport", body, wide=True)


def main() -> None:
    (ROOT / "index.html").write_text(master_index())
    print(f"Wrote {ROOT / 'index.html'}")

    pages = [
        sprint_page(
            "SPR-AHT-01", "01", "research-artifact-contract",
            "ResearchArtifact v1 contract",
            "Dual-channel HTML: human sections + application/json block.",
            1, "3 milestones",
            "Thariq-style HTML is the agent lens; markdown alone fails information density for deep research handoff.",
            "SessionEvidencePack and distillation already exist; this sprint names the on-disk Profile B shape.",
            "Wave 1 foundation before export or API.",
            "Schema v1 fields + render template + content_hash over canonical JSON.",
            [
                ("Schema module", "ResearchArtifactBody v1 with content_hash().",
                 ["pytest template gate passes", "JSON block id antiek-artifact-v1"],
                 ["substrate/research_artifact/schema.py"]),
                ("Renderer", "Human channel + copy-as-prompt + embedded JSON.",
                 ["fixture minimal.html shape", "no script injection in insights"],
                 ["substrate/research_artifact/render.py", "tests/fixtures/research_artifact/minimal.html"]),
                ("Decision doc", "docs/decisions/research-artifact-v0.md",
                 ["graph canonical stated"], ["docs/decisions/research-artifact-v0.md"]),
            ],
            ("Report ArtifactKind=other+intent from code.", "Steelman markdown-only transport; rejected for cross-window agent density.",
             "test_research_artifact_template.py required.", "Read architecture_notes Layer 4 before schema.",
             "Handoff cites content_hash algorithm."),
            [], ["master-product-spec §5", "architecture_notes"],
            ["Git commit of ~/.antiek artifacts", "Two-way HTML import"],
            [("Template", "./.venv/bin/python -m pytest tests/test_research_artifact_template.py -q", "pass")],
            ("inline", "schema+render", "dual-channel|hash", "1", "2"),
        ),
        sprint_page(
            "SPR-AHT-02", "02", "export-pipeline",
            "Export pipeline",
            "Write HTML to operator store; emit artifact.generated.",
            1, "3 milestones",
            "Each completed deep research should be one shareable HTML file when invoked.",
            "Export reads graph + trajectory; does not bypass db_lock writer funnel for graph mutations.",
            "Depends on SPR-AHT-01 contract.",
            "CLI + export_research_artifact() + paths under ~/.antiek/research-artifacts/.",
            [
                ("Paths + export", "artifact_path_for + export_research_artifact.",
                 ["file on disk", "artifact.generated in trajectory"],
                 ["substrate/research_artifact/paths.py", "substrate/research_artifact/export.py"]),
                ("Context build", "Distill question, insights, synthesis from trajectory.",
                 ["build_body hermetic test"], ["substrate/research_artifact/build_body.py", "context.py"]),
                ("CLI", "python -m substrate.research_artifact",
                 ["--help works"], ["substrate/research_artifact/__main__.py"]),
            ],
            ("Emit event even when re-export overwrites file.", "Steelman git-tracked artifacts; rejected for diff noise.",
             "export test uses temp ANTIEK_RESEARCH_ARTIFACTS_DIR.", "Read emit_typed ArtifactGeneratedPayload.",
             "Log intent prefix research_artifact_v1:"),
            ["SPR-AHT-01"], ["runtime/db_lock.py"],
            ["Auto-export on every phase", "Dedicated ArtifactKind enum bump"],
            [("Export", "./.venv/bin/python -m pytest tests/test_research_artifact_export.py -q", "pass")],
            ("inline", "export.py", "event-log|provenance", "1", "2"),
        ),
        sprint_page(
            "SPR-AHT-03", "03", "agent-transport-protocol",
            "Agent transport protocol",
            "Document how agents append to HTML lenses across context windows.",
            2, "2 milestones",
            "Operators merge HTML like code; substrate remains merge authority.",
            "RESEARCH_ARTIFACT_TRANSPORT.md is the protocol; TEMPLATES.md gets handoff block.",
            "Wave 2 — parallel with ingest snapshot.",
            "No import_notes.py until operator requests two-way edit.",
            [
                ("Transport doc", "docs/agent-execution/RESEARCH_ARTIFACT_TRANSPORT.md",
                 ["profiles A/B/C defined", "forbidden HTML-primary bypass"],
                 ["docs/agent-execution/RESEARCH_ARTIFACT_TRANSPORT.md"]),
                ("Handoff template", "TEMPLATES.md research artifact block",
                 ["paste block exists"], ["docs/agent-execution/TEMPLATES.md"]),
            ],
            ("Mark import path GAP not silent.", "Steelman wiki-only transport; rejected for agent auditability.",
             "grep for HTML-primary in protocol.", "Read Thariq blog use cases before editing.",
             "Cite on-policy RL audit via events + HTML."),
            ["SPR-AHT-02"], [],
            ["import_notes v0", "RL training pipeline"],
            [("Doc", "grep -q RESEARCH_ARTIFACT_TRANSPORT docs/agent-execution/RESEARCH_ARTIFACT_TRANSPORT.md", "match")],
            ("inline", "docs only", "defensibility|correspondence", "1", "1"),
        ),
        sprint_page(
            "SPR-AHT-04", "04", "ingest-reader-snapshot",
            "Ingest reader snapshot",
            "Optional sanitized HTML when ingesting URLs.",
            2, "3 milestones",
            "Reading a web article should produce a human-readable HTML snapshot alongside chunks.",
            "Derivative of fetched HTML — not a second ingest path.",
            "Wire behind ANTIEK_READER_SNAPSHOT flag.",
            "Strips script/style; metadata header with document_id and source URL.",
            [
                ("reader_html module", "build_reader_snapshot + sanitize.",
                 ["test_reader_snapshot.py"], ["acquisition/snapshot/reader_html.py"]),
                ("Adapter hook", "ingest_url sets reader_snapshot_path when flag on.",
                 ["test_acquisition_urls snapshot test"], ["acquisition/urls/adapter.py"]),
                ("Decision", "docs/decisions/ingest-reader-snapshot.md",
                 ["flag documented"], ["docs/decisions/ingest-reader-snapshot.md"]),
            ],
            ("Default flag off in prod.", "Steelman always snapshot; rejected for disk churn until operator opts in.",
             "pytest with ANTIEK_READER_SNAPSHOTS_DIR temp dir.", "Read ingest_url return sites before field add.",
             "Handoff documents env vars."),
            ["SPR-AHT-01"], [],
            ["EPUB/PDF reader HTML", "Automatic snapshot without flag"],
            [("Snapshot", "./.venv/bin/python -m pytest tests/test_reader_snapshot.py tests/test_acquisition_urls.py -k reader_snapshot -q", "pass")],
            ("inline", "adapter.py tail", "sanitization|xss-strip", "1", "2"),
        ),
        sprint_page(
            "SPR-AHT-05", "05", "compose-merge",
            "Compose / merge index",
            "Multi-investigation HTML index for operator review.",
            3, "2 milestones",
            "Merge HTML files like developers merge code — with hash conflict surfacing.",
            "compose.py builds index linking per-inv artifacts; does not flatten graph.",
            "Wave 3 after export stable.",
            "Compose path under research-artifacts/compose-*.html",
            [
                ("Compose module", "compose_research_artifacts index page.",
                 ["compose test passes"], ["substrate/research_artifact/compose.py"]),
                ("Decision", "docs/decisions/research-artifact-compose.md",
                 ["merge semantics"], ["docs/decisions/research-artifact-compose.md"]),
            ],
            ("Content hash mismatch → visible conflict section.", "Steelman single mega-HTML; rejected for audit granularity.",
             "test_research_artifact_compose.py", "Read compose decision before UI.",
             "Handoff lists max investigation count in filename."),
            ["SPR-AHT-02"], [],
            ["Git merge driver for HTML", "Automatic compose on complete"],
            [("Compose", "./.venv/bin/python -m pytest tests/test_research_artifact_compose.py -q", "pass")],
            ("inline", "compose.py", "hash-conflict|index", "1", "2"),
        ),
        sprint_page(
            "SPR-AHT-06", "06", "write-bridge-api",
            "Write bridge + API",
            "OutlineBlockRef for Write Lego + HTTP export/blocks.",
            3, "3 milestones",
            "Drag HTML data points into outlines; tab-complete sections later with on-policy RL.",
            "blocks.py lists insights/questions; artifact_routes.py exposes REST.",
            "Post-complete export hook optional via ANTIEK_EXPORT_RESEARCH_ARTIFACT.",
            "FastAPI routes mounted on research app.",
            [
                ("Blocks", "list_outline_blocks for Write bridge.",
                 ["blocks test"], ["substrate/research_artifact/blocks.py"]),
                ("API routes", "POST export, GET blocks.",
                 ["test_artifact_routes.py"], ["interfaces/research/api/artifact_routes.py", "app.py"]),
                ("Hook", "maybe_export_after_investigation_complete",
                 ["orchestrator calls hook"], ["substrate/research_artifact/hooks.py", "orchestration/loop_one/orchestrator.py"]),
            ],
            ("API 500 surfaces exception message — acceptable for operator API.", "Steelman GraphQL artifact API; rejected for scope.",
             "TestClient hermetic tests.", "Read app router include order.",
             "Handoff lists route paths."),
            ["SPR-AHT-02", "SPR-AHT-05"], ["FastAPI TestClient"],
            ["Write UI drag-drop", "Notebook auto-embed"],
            [("API", "./.venv/bin/python -m pytest tests/test_artifact_routes.py -q", "pass"),
             ("Blocks", "./.venv/bin/python -m pytest tests/test_research_artifact_blocks.py -q", "pass")],
            ("inline", "artifact_routes.py", "api-contract|write-bridge", "1", "2"),
        ),
        sprint_page(
            "SPR-AHT-07", "07", "book-reader-snapshot",
            "Book reader snapshot",
            "Readable HTML when ingesting PDF books (textbook / PD corpus).",
            2, "2 milestones",
            "Books and textbooks should be reviewable as HTML lenses like web articles.",
            "Reuses ANTIEK_READER_SNAPSHOT flag and ~/.antiek/reader-snapshots store.",
            "Wave 2 extension of SPR-AHT-04 — markdown body from PDF extraction.",
            "markdown_to_safe_html + ingest_pdf hook; title/author in meta header.",
            [
                ("markdown_to_safe_html", "Escape-first minimal heading/paragraph render.",
                 ["test_reader_snapshot markdown tests"], ["acquisition/snapshot/reader_html.py"]),
                ("ingest_pdf hook", "IngestBookResult.reader_snapshot_path when flag on.",
                 ["test_acquisition_books snapshot test"], ["acquisition/books/adapter.py"]),
            ],
            ("EPUB-native deferred; PD epub still becomes PDF at ingest.", "Steelman separate book HTML store; rejected — one reader-snapshots dir.",
             "P-18 includes book snapshot test.", "Read SPR-AHT-04 before wiring.",
             "Decision doc ingest-reader-snapshot.md updated."),
            ["SPR-AHT-04"], [],
            ["EPUB direct HTML ingest", "Servable-book gate changes"],
            [("Book snapshot", "./.venv/bin/python -m pytest tests/test_reader_snapshot.py tests/test_acquisition_books.py -k reader_snapshot -q", "pass")],
            ("inline", "books/adapter.py", "markdown-escape|same-flag", "1", "2"),
        ),
    ]

    slugs = [
        "01-research-artifact-contract",
        "02-export-pipeline",
        "03-agent-transport-protocol",
        "04-ingest-reader-snapshot",
        "05-compose-merge",
        "06-write-bridge-api",
        "07-book-reader-snapshot",
    ]
    for slug, html in zip(slugs, pages):
        path = ROOT / f"sprint-{slug}.html"
        path.write_text(html)
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()