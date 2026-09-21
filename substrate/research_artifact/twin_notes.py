"""Twin note document for a ResearchArtifact HTML asset."""

from __future__ import annotations

import html
import json
from pathlib import Path

from .paths import twin_notes_path_for
from .schema import ResearchArtifactBody

_CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.55; color: #1c1917; background: #fafaf9; margin: 0; padding: 24px; }
main { max-width: 760px; margin: 0 auto; }
h1 { font-family: Charter, Georgia, serif; font-size: 1.7rem; margin-bottom: 4px; }
.kicker, .tag { color: #57534e; font-size: 0.85rem; }
section { border: 1px solid #e7e5e4; background: #fff; padding: 16px 20px;
  margin: 16px 0; border-radius: 6px; }
li { margin-bottom: 8px; }
.empty { color: #57534e; font-style: italic; }
textarea { width: 100%; min-height: 96px; font: inherit; border: 1px solid #e7e5e4;
  border-radius: 4px; padding: 8px; }
button { margin-top: 10px; padding: 8px 14px; border: 1px solid #1c1917;
  background: #fffbeb; border-radius: 4px; font-weight: 600; cursor: pointer; }
"""


def render_twin_notes_html(body: ResearchArtifactBody, *, artifact_path: Path) -> str:
    """Render the editable note twin.

    The main research artifact remains graph-sourced. This sibling document is
    the review/annotation surface: it mirrors insights/questions as prompts,
    carries current agent notes, and embeds the same machine payload so imports
    keep using the existing append-only note path.
    """

    artifact_href = artifact_path.as_posix()
    insight_items = "".join(
        f"<li>{_esc(ins.text)} <span class=\"tag\">{_esc(ins.node_id)}</span></li>"
        for ins in body.insights
    ) or '<li class="empty">No findings yet.</li>'
    question_items = "".join(
        f"<li>{_esc(q.text)} <span class=\"tag\">{_esc(q.node_id)}</span></li>"
        for q in body.open_questions
    ) or '<li class="empty">No open questions yet.</li>'
    note_items = "".join(
        f"<li>{_esc(note)}</li>" for note in body.agent_notes if (note or "").strip()
    ) or '<li class="empty">(none yet)</li>'
    json_blob = json.dumps(body.model_dump(mode="json"), indent=2).replace("<", "\\u003c")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Notes — {_esc(body.investigation_id)}</title>
<style>{_CSS}</style>
</head>
<body>
<main data-investigation-id="{_esc(body.investigation_id)}" data-twin-for="{_esc(str(artifact_path))}">
<p class="kicker">ResearchArtifact twin notes · ANT-AHT</p>
<h1>{_esc(body.problem_question)}</h1>
<p><a href="file://{_esc(artifact_href)}">Open research artifact</a></p>
<section><h2>Finding prompts</h2><ul>{insight_items}</ul></section>
<section><h2>Open question prompts</h2><ul>{question_items}</ul></section>
<section><h2>Agent notes</h2><ul id="agent-notes-list">{note_items}</ul>
<label for="note-input">Add note for import</label>
<textarea id="note-input" placeholder="A question, insight, or merge instruction for the next research pass..."></textarea>
<br><button type="button" id="add-note">Add note to twin payload</button>
<button type="button" id="copy-json">Copy JSON for import</button>
</section>
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
  document.getElementById("copy-json").addEventListener("click", function() {{
    navigator.clipboard.writeText(el.textContent);
  }});
}})();
</script>
</main>
</body>
</html>
"""


def write_twin_notes(body: ResearchArtifactBody, *, artifact_path: Path) -> Path:
    path = twin_notes_path_for(body.investigation_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_twin_notes_html(body, artifact_path=artifact_path), encoding="utf-8")
    return path


def _esc(value: str) -> str:
    return html.escape(value, quote=True)
