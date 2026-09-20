"""SPR-AHT-01 — ResearchArtifact template anti-fiction."""

from __future__ import annotations

from substrate.research_artifact.render import render_html
from substrate.research_artifact.schema import ResearchArtifactBody


def test_empty_body_renders_honest_empty_state():
    body = ResearchArtifactBody(
        investigation_id="inv-empty",
        problem_question="What is unknown?",
    )
    html = render_html(body)
    assert "No insights in the graph yet" in html
    assert "No open questions in the graph yet" in html
    assert "No synthesis yet" in html
    assert 'id="antiek-artifact-v1"' in html
    assert "inv-empty" in html
    assert 'id="copy-json"' in html
    assert 'id="add-note"' in html


def test_content_hash_stable():
    body = ResearchArtifactBody(
        investigation_id="inv-1",
        problem_question="Q",
    )
    assert body.content_hash() == body.content_hash()

def test_added_notes_survive_html_serialization_and_import(tmp_path, monkeypatch):
    """Run the shipped callback; persist its JSON island through the real importer.

    Node is part of the existing project toolchain and is required, not skipped.
    The small DOM double models callback registration and script textContent;
    a real-browser check separately covers browser outerHTML serialization.
    """
    import json
    import re
    import shutil
    import subprocess

    from substrate.event_log import trajectory
    from substrate.research_artifact.import_notes import (
        import_agent_notes,
        load_persisted_agent_notes,
        parse_body_from_html,
    )

    node = shutil.which("node")
    assert node, "Node is required to exercise ResearchArtifact's emitted JavaScript"
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.delenv("ANTIEK_EVENTS_DISABLED", raising=False)
    notes = [
        'literal </script><script>throw new Error("injected")</script>',
        'mixed </ScRiPt> <img src=x onerror="bad()"> & 雪',
        r'literal escape \u003c/script> and backslash \\ with "quotes"',
    ]
    original = ResearchArtifactBody(
        investigation_id="inv-browser-note", problem_question="Retain all fields",
        agent_notes=["Previously accepted note"],
    )
    html = render_html(original)
    original_file = tmp_path / "original.html"
    original_file.write_text(html, encoding="utf-8")
    assert import_agent_notes(original_file).notes_imported == 1
    island = re.search(
        r'<script type="application/json" id="antiek-artifact-v1">(.*?)</script>',
        html, re.DOTALL,
    )
    executable = re.search(r'<script>\s*(.*?)</script>', html, re.DOTALL)
    assert island is not None and executable is not None
    program = r'''
const fs = require("node:fs");
const vm = require("node:vm");
const source = JSON.parse(fs.readFileSync(0, "utf8"));
const elements = new Map();
const copied = [];
function element() {
  return {textContent: "", value: "", innerHTML: "", children: [], callbacks: {},
    appendChild(child) { this.children.push(child); },
    addEventListener(name, callback) { this.callbacks[name] = callback; }};
}
const document = {
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, element());
    return elements.get(id);
  },
  createElement() { return element(); }
};
const island = document.getElementById("antiek-artifact-v1");
island.textContent = source.island;
vm.runInNewContext(source.script, {
  document, navigator: {clipboard: {writeText(text) { copied.push(text); }}}
}, {timeout: 1000});
const input = document.getElementById("note-input");
const states = [];
for (const note of source.notes) {
  input.value = note;
  document.getElementById("add-note").callbacks.click();
  states.push({island: island.textContent, input: input.value});
}
document.getElementById("copy-json").callbacks.click();
document.getElementById("copy-prompt").callbacks.click();
const beforeBlank = island.textContent;
input.value = "   ";
document.getElementById("add-note").callbacks.click();
process.stdout.write(JSON.stringify({states, copied, blankUnchanged: beforeBlank === island.textContent}));
'''
    execution = subprocess.run(
        [node, "-e", program],
        input=json.dumps({"island": island.group(1), "script": executable.group(1), "notes": notes}),
        capture_output=True, text=True, check=True, timeout=10,
    )
    result = json.loads(execution.stdout)
    for index, state in enumerate(result["states"], start=1):
        saved = html[:island.start(1)] + state["island"] + html[island.end(1):]
        recovered = parse_body_from_html(saved)
        assert recovered.model_dump() == original.model_copy(
            update={"agent_notes": [*original.agent_notes, *notes[:index]]},
        ).model_dump()
        assert "<" not in state["island"]
        assert state["input"] == ""
    assert result["blankUnchanged"]
    final_island = result["states"][-1]["island"]
    assert result["copied"] == [
        final_island, "Continue research using this artifact (graph is canonical):\n\n" + final_island,
    ]
    caller = tmp_path / "saved-caller.html"
    caller.write_text(saved, encoding="utf-8")
    accepted = import_agent_notes(caller)
    assert accepted.notes_imported == 3
    assert accepted.notes_skipped_duplicate == 1
    assert len(accepted.event_ids) == 3
    before_replay = trajectory(original.investigation_id)
    replay = import_agent_notes(caller)
    assert replay.notes_imported == 0
    assert replay.notes_skipped_duplicate == 4
    assert trajectory(original.investigation_id) == before_replay
    caller.unlink()
    assert load_persisted_agent_notes(original.investigation_id) == [*original.agent_notes, *notes]
