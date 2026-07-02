#!/usr/bin/env python3
"""Build docs/html/html-landscape.html from repo inventory. Idempotent."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "html-landscape.html"

CATEGORIES = [
    ("all", "All first-party HTML"),
    ("profile-a", "Profile A — htmlspec (Lemon UI)"),
    ("profile-b", "Profile B — ResearchArtifact transport"),
    ("profile-c", "Profile C — operator docs/html"),
    ("profile-d", "UI redesign (PostHog feel)"),
    ("profile-e", "Specs & roadmaps"),
    ("profile-f", "Apps & test fixtures"),
]


def classify(path: str) -> str:
    p = path.replace("\\", "/")
    if "research_artifact" in p or "htmlspec/antiek-html-transport" in p:
        return "profile-b"
    if "htmlspec/" in p:
        return "profile-a"
    if p.startswith("docs/html/"):
        return "profile-c"
    if "ui_redesign_posthog" in p:
        return "profile-d"
    if p.startswith("docs/specs/") or p.startswith("docs/roadmap") or p.startswith("docs/sprint-breakdown"):
        return "profile-e"
    if p.startswith("apps/") or p.startswith("tests/fixtures"):
        return "profile-f"
    if p.startswith("specs/"):
        return "profile-e"
    return "profile-a"


def collect() -> list[dict]:
    cmd = [
        "find",
        "docs",
        "specs",
        "tests/fixtures",
        "apps/reading/public",
        "apps/x-extension",
        "-name",
        "*.html",
        "-type",
        "f",
    ]
    raw = subprocess.check_output(cmd, cwd=ROOT, text=True)
    rows = []
    for line in sorted(raw.strip().splitlines()):
        if "node_modules" in line or ".caffenagent" in line:
            continue
        rel = line
        rows.append(
            {
                "path": rel,
                "cat": classify(rel),
                "name": Path(rel).name,
            }
        )
    return rows


def main() -> None:
    rows = collect()
    data_json = json.dumps(rows)
    tabs = "".join(
        f'<button type="button" class="tab" data-cat="{cid}">{label}</button>'
        for cid, label in CATEGORIES
    )
    rows_html = "\n".join(
        f'<tr data-cat="{r["cat"]}"><td><code>{r["path"]}</code></td>'
        f'<td><span class="pill pill--{r["cat"]}">{r["cat"]}</span></td>'
        f'<td>{r["name"]}</td></tr>'
        for r in rows
    )
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Antiek HTML landscape — Thariq thesis catalog</title>
<link rel="stylesheet" href="styles.css">
<style>
.landscape-hero {{ margin-bottom: 2rem; }}
.tabs {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 1.5rem 0; }}
.tab {{
  font-family: var(--font-sans); font-size: 13px; padding: 6px 12px;
  border: 1px solid var(--stone-300); background: var(--stone-100);
  border-radius: 4px; cursor: pointer;
}}
.tab.active {{ background: var(--stone-900); color: var(--stone-50); border-color: var(--stone-900); }}
.asset-table {{ width: 100%; border-collapse: collapse; font-size: 14px; font-family: var(--font-mono); }}
.asset-table th, .asset-table td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--stone-200); }}
.asset-table th {{ font-family: var(--font-sans); font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--stone-600); }}
.pill {{ font-size: 11px; padding: 2px 8px; border-radius: 999px; background: var(--stone-200); }}
.svg-wrap {{ max-width: 100%; overflow-x: auto; margin: 1.5rem 0; }}
#search {{ width: 100%; max-width: 480px; padding: 8px 12px; font-size: 15px; border: 1px solid var(--stone-300); border-radius: 4px; }}
.hidden {{ display: none; }}
</style>
</head>
<body>
<nav class="topnav">
  <div class="topnav-inner">
    <span class="topnav-title">Antiek docs</span>
    <a href="index.html">Index</a>
    <a href="html-landscape.html" class="active">HTML landscape</a>
    <a href="thariq-antiek-index.html">Thariq × Antiek</a>
    <a href="ant-aht-vision-map.html">Vision map</a>
    <a href="ant-aht-operator-guide.html">ANT-AHT guide</a>
    <a href="ant-aht-cycle-complete.html">Ledger complete</a>
    <a href="../htmlspec/antiek-html-transport/index.html">ANT-AHT spec</a>
  </div>
</nav>
<main class="wide">
<article>
<p class="kicker">2026-06-23 · ANT-AHT exec-3 · {len(rows)} first-party HTML files</p>
<h1>HTML landscape in Antiek</h1>
<p class="landscape-hero">Inspired by
<a href="https://claude.com/blog/using-claude-code-the-unreasonable-effectiveness-of-html">Thariq / Claude Code — unreasonable effectiveness of HTML</a>:
rich, scannable artifacts for specs, research, and <strong>agent transport</strong> across context windows.
Canonical truth stays DuckDB + events; HTML is the lens operators and agents actually read.</p>

<h2>Three profiles</h2>
<ul>
<li><strong>Profile A</strong> — execution htmlspecs (rigor cards, harness hints, Lemon UI).</li>
<li><strong>Profile B</strong> — <code>ResearchArtifact</code> per investigation + compose index (<code>substrate/research_artifact/</code>).</li>
<li><strong>Profile C</strong> — stone §5.5 operator pages under <code>docs/html/</code>.</li>
</ul>

<h2>Thariq use-case map (Antiek)</h2>
<div class="card-grid wide">
<div class="card"><h3>Specs &amp; planning</h3><p>Profile A htmlspecs under <code>docs/htmlspec/</code> — tabs, rigor, sprint grids.</p></div>
<div class="card"><h3>Research reports</h3><p>Profile B <code>ResearchArtifact</code> — export per investigation, compose merge index.</p></div>
<div class="card"><h3>Ingest reader view</h3><p>URL + PDF book reader snapshots (<code>ANTIEK_READER_SNAPSHOT</code>) beside substrate chunks — SPR-AHT-04/07.</p></div>
<div class="card"><h3>Agent handoff</h3><p>Copy-as-prompt + <code>agent_notes[]</code> import → audited <code>artifact.generated</code> events.</p></div>
<div class="card"><h3>Write Lego outline</h3><p><code>GET /research/{{id}}/artifact/blocks</code> + DistillView shelf — full Write canvas deferred.</p></div>
<div class="card"><h3>On-policy RL audit</h3><p>What lands in HTML + events is the training trace (human research workflow).</p></div>
</div>

<div class="svg-wrap">
<svg viewBox="0 0 720 200" width="720" height="200" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Data flow">
  <rect x="10" y="70" width="140" height="60" fill="#f5f5f4" stroke="#44403c" stroke-width="2" rx="4"/>
  <text x="80" y="105" text-anchor="middle" font-size="13" font-family="system-ui">DuckDB graph</text>
  <rect x="200" y="70" width="140" height="60" fill="#eff6ff" stroke="#1d4ed8" stroke-width="2" rx="4"/>
  <text x="270" y="95" text-anchor="middle" font-size="12" font-family="system-ui">Event log</text>
  <text x="270" y="115" text-anchor="middle" font-size="11" font-family="system-ui">artifact.generated</text>
  <rect x="390" y="40" width="150" height="50" fill="#fdf1cf" stroke="#44403c" stroke-width="2" rx="4"/>
  <text x="465" y="70" text-anchor="middle" font-size="12" font-family="system-ui">Profile B HTML</text>
  <rect x="390" y="110" width="150" height="50" fill="#d9efe2" stroke="#44403c" stroke-width="2" rx="4"/>
  <text x="465" y="140" text-anchor="middle" font-size="12" font-family="system-ui">Reader snapshot</text>
  <rect x="580" y="70" width="130" height="60" fill="#f5f5f4" stroke="#44403c" stroke-width="2" rx="4"/>
  <text x="645" y="105" text-anchor="middle" font-size="12" font-family="system-ui">Write outline</text>
  <path d="M150 100 H200" stroke="#44403c" stroke-width="2" marker-end="url(#arr)"/>
  <path d="M340 100 H390" stroke="#44403c" stroke-width="2"/>
  <path d="M540 65 H580" stroke="#44403c" stroke-width="2"/>
  <path d="M540 135 H580" stroke="#44403c" stroke-width="2"/>
  <defs><marker id="arr" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#44403c"/></marker></defs>
</svg>
</div>

<h2>Inventory</h2>
<p>Filter by profile or search path. Excludes <code>node_modules</code> and caffenagent worktrees.</p>
<input type="search" id="search" placeholder="Filter paths…" autocomplete="off">
<div class="tabs" id="tabs">{tabs}</div>
<table class="asset-table" id="table">
<thead><tr><th>Path</th><th>Profile</th><th>File</th></tr></thead>
<tbody>{rows_html}</tbody>
</table>

<h2>Operator env flags</h2>
<table class="asset-table">
<tr><td><code>ANTIEK_RESEARCH_ARTIFACTS_DIR</code></td><td>Profile B export directory</td></tr>
<tr><td><code>ANTIEK_EXPORT_RESEARCH_ARTIFACT</code></td><td>Post <code>investigation.completed</code> auto-export</td></tr>
<tr><td><code>ANTIEK_READER_SNAPSHOT</code></td><td>Reader HTML on <code>ingest_url</code> and <code>ingest_pdf</code></td></tr>
<tr><td><code>ANTIEK_READER_SNAPSHOTS_DIR</code></td><td>Reader snapshot store (default <code>~/.antiek/reader-snapshots</code>)</td></tr>
</table>
</article>
</main>
<script>
const DATA = {data_json};
let activeCat = 'all';
const tbody = document.querySelector('#table tbody');
const search = document.getElementById('search');
function applyFilter() {{
  const q = (search.value || '').toLowerCase();
  for (const tr of tbody.querySelectorAll('tr')) {{
    const path = tr.querySelector('code').textContent.toLowerCase();
    const cat = tr.dataset.cat;
    const catOk = activeCat === 'all' || cat === activeCat;
    const qOk = !q || path.includes(q);
    tr.classList.toggle('hidden', !(catOk && qOk));
  }}
}}
document.getElementById('tabs').addEventListener('click', (e) => {{
  const btn = e.target.closest('.tab');
  if (!btn) return;
  activeCat = btn.dataset.cat;
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t === btn));
  applyFilter();
}});
search.addEventListener('input', applyFilter);
document.querySelector('.tab[data-cat="all"]').classList.add('active');
</script>
</body>
</html>
"""
    OUT.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT} ({len(rows)} rows)")


if __name__ == "__main__":
    main()