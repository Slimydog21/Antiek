"""Render ResearchArtifactBody to self-contained HTML (human + machine channel)."""

from __future__ import annotations

import html
import json

from .schema import ResearchArtifactBody

# Stone-leaning minimal CSS — offline, no CDN (§5.5 notebook voice).
_PAGE_CSS = """
:root { --stone-900:#1c1917; --stone-600:#57534e; --stone-200:#e7e5e4; --stone-50:#fafaf9;
  --amber-50:#fffbeb; --blue-700:#1d4ed8; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.55; color: var(--stone-900); background: var(--stone-50); margin: 0; padding: 24px; }
main { max-width: 720px; margin: 0 auto; }
h1 { font-family: Charter, Georgia, serif; font-size: 1.75rem; }
.kicker { color: var(--stone-600); font-size: 0.85rem; }
section { border: 1px solid var(--stone-200); background: #fff; padding: 16px 20px;
  margin: 16px 0; border-radius: 6px; }
.empty { color: var(--stone-600); font-style: italic; }
.card { margin: 10px 0; padding: 10px 12px; border-left: 3px solid var(--blue-700);
  background: var(--stone-50); }
.card[data-node-id] { cursor: default; }
.tag { font-size: 0.75rem; color: var(--stone-600); }
footer { margin-top: 32px; font-size: 0.8rem; color: var(--stone-600); }
button.copy { margin-top: 12px; padding: 8px 14px; border: 1px solid var(--stone-900);
  background: var(--amber-50); font-weight: 600; cursor: pointer; border-radius: 4px; }
button.copy.secondary { background: #fff; margin-left: 8px; }
#note-input { width: 100%; min-height: 72px; font-family: inherit; font-size: 14px;
  padding: 8px; border: 1px solid var(--stone-200); border-radius: 4px; }
pre.excerpt { white-space: pre-wrap; font-size: 0.95rem; }
"""


def _esc(s: str) -> str:
    return html.escape(s, quote=True)


def render_html(body: ResearchArtifactBody) -> str:
    insights_html = ""
    if body.insights:
        for ins in body.insights:
            insights_html += (
                f'<div class="card" data-node-id="{_esc(ins.node_id)}" data-kind="insight">'
                f"<p>{_esc(ins.text)}</p>"
                f'<p class="tag">node {_esc(ins.node_id)}</p></div>'
            )
    else:
        insights_html = '<p class="empty">No insights in the graph yet.</p>'

    questions_html = ""
    if body.open_questions:
        for q in body.open_questions:
            flag = " · needs research" if q.escalated else ""
            questions_html += (
                f'<div class="card" data-node-id="{_esc(q.node_id)}" data-kind="question">'
                f"<p>{_esc(q.text)}</p>"
                f'<p class="tag">node {_esc(q.node_id)}{_esc(flag)}</p></div>'
            )
    else:
        questions_html = '<p class="empty">No open questions in the graph yet.</p>'

    if body.synthesis_withheld:
        synth_block = '<p class="empty">Synthesis not available to display (§9.0 guard).</p>'
    elif body.synthesis_excerpt:
        synth_block = f'<pre class="excerpt">{_esc(body.synthesis_excerpt)}</pre>'
    else:
        synth_block = '<p class="empty">No synthesis yet.</p>'

    json_blob = json.dumps(body.model_dump(mode="json"), indent=2).replace("<", "\\u003c")
    ch = body.content_hash()

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Research — {_esc(body.investigation_id)}</title>
<style>{_PAGE_CSS}</style>
</head>
<body>
<main data-investigation-id="{_esc(body.investigation_id)}" data-content-hash="{_esc(ch)}">
<p class="kicker">ResearchArtifact v{body.schema_version} · ANT-AHT</p>
<h1>{_esc(body.problem_question)}</h1>
<section id="findings"><h2>Findings</h2>{insights_html}</section>
<section id="gaps"><h2>Open gaps</h2>{questions_html}</section>
<section id="synthesis"><h2>Synthesis excerpt</h2>{synth_block}</section>
<section id="agent-notes"><h2>Agent notes</h2>
<ul id="agent-notes-list">{"".join(f'<li>{_esc(n)}</li>' for n in body.agent_notes if (n or "").strip()) or '<li class="empty">(none yet)</li>'}</ul>
<label for="note-input">Add cross-window note (Thariq two-way)</label>
<textarea id="note-input" placeholder="Insight for the next agent session…"></textarea>
<p class="tag">Findings/gaps stay graph-sourced. Notes import via <code>--import-notes</code> or API.</p></section>
<button type="button" class="copy" id="copy-prompt">Copy as agent handoff</button>
<button type="button" class="copy secondary" id="add-note">Add note to artifact</button>
<button type="button" class="copy secondary" id="copy-json">Copy JSON for import</button>
<script type="application/json" id="antiek-artifact-v1">{json_blob}</script>
<script>
(function() {{
  var el = document.getElementById("antiek-artifact-v1");
  var list = document.getElementById("agent-notes-list");
  var input = document.getElementById("note-input");
  function payload() {{ return JSON.parse(el.textContent); }}
  function syncList(notes) {{
    list.innerHTML = "";
    if (!notes.length) {{
      var li = document.createElement("li");
      li.className = "empty";
      li.textContent = "(none yet)";
      list.appendChild(li);
      return;
    }}
    notes.forEach(function(t) {{
      var li = document.createElement("li");
      li.textContent = t;
      list.appendChild(li);
    }});
  }}
  document.getElementById("add-note").addEventListener("click", function() {{
    var t = (input.value || "").trim();
    if (!t) return;
    var p = payload();
    p.agent_notes = p.agent_notes || [];
    p.agent_notes.push(t);
    el.textContent = JSON.stringify(p, null, 2);
    syncList(p.agent_notes);
    input.value = "";
  }});
  document.getElementById("copy-prompt").addEventListener("click", function() {{
    var body = el.textContent;
    var prompt = "Continue research using this artifact (graph is canonical):\\n\\n" + body;
    navigator.clipboard.writeText(prompt);
  }});
  document.getElementById("copy-json").addEventListener("click", function() {{
    navigator.clipboard.writeText(el.textContent);
  }});
}})();
</script>
<footer>content_hash {_esc(ch[:16])}… · investigation {_esc(body.investigation_id)}</footer>
</main>
</body>
</html>
"""