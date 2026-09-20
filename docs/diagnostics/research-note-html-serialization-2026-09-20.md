# Preserve added notes when saving research HTML

## Failure Dossier

The editable research artifact worked in the browser until a note contained
`</script>` and the caller saved its DOM as HTML. The added note was valid JSON
in the live script element's `textContent`, but literal closing tags terminated
that element when the saved HTML was parsed. The real import endpoint returned
400 with `Unterminated string`. Root retained the browser reproduction under
its note-persistence worktree `.audit/browser-proof-state/closing-tag-caller.html`
and `closing-tag-import-result.json`.

### Contract and failure chain

1. `render_html(body: ResearchArtifactBody) -> str` initially escapes `<` in
   the JSON island at `substrate/research_artifact/render.py:71`.
2. The Add-note callback reparses that island and appends a note at line 119.
3. Its assignment at line 125 previously serialized with `JSON.stringify`
   without escaping `<`, undoing the initial HTML boundary protection.
4. Saving and reparsing the HTML truncated the JSON at the literal script end
   tag. `parse_body_from_html(html_text: str) -> ResearchArtifactBody` raised
   `JSONDecodeError` before durable note acceptance.

The one-line fix escapes every `<` after JavaScript serialization. The Python
f-string emits a JavaScript string containing a literal JSON Unicode escape.
`JSON.parse` restores the exact original note; imported notes remain append-only.
No LLM or network call occurs on this failure path or in the regression.

## Scope Map

| Entry point | Status | Evidence | Live LLM |
|---|---|---|---|
| Initial renderer and JSON island | Tested | Existing template tests plus initial note import in new regression | No |
| Actual emitted Add-note JavaScript | Tested | Node VM executes emitted IIFE and registered click callback | No |
| Saved island through production parser | Tested | Every hostile-note addition roundtrips the complete body | No |
| Copy JSON and handoff buttons | Tested | Actual callbacks preserve final serialized data and handoff prefix | No |
| Durable note import and replay | Tested | Existing accepted note retained, three new notes accepted, replay emits nothing, caller deletion preserves notes | No |
| Real browser DOM serialization | Pending root verification | Minimal DOM doubles do not establish browser behavior | No |
| Production deployment | Not run | No production mutation authorized in this lane | No |

## Handoff Packet

### Env Card

| Field | Value |
|---|---|
| Date | 2026-09-20 |
| Repo root | `/Users/slimydog/Antiek/.worktrees/research-note-html-serialization-20260920` |
| Branch | `fix/research-note-html-serialization-20260920` |
| Stacked base | `6e2c73d111a50a74ec0c4a72b3fa00f349822b8b` |
| Python | `/Users/slimydog/Antiek/platform/.venv/bin/python`, 3.12.13 |
| Node | `/opt/homebrew/opt/node@22/bin/node`, 22.22.0 |
| Import root | Worktree cwd, `PYTHONPATH=.` |
| LLM / paid / network for gates | None |

### Not proved

Real Chrome serialization, different-lineage acceptance and Ubuntu CI are
pending. The new Python regression requires the existing project Node toolchain
on PATH. Missing Node fails explicitly; it does not skip. The Python CI job does
not currently have an explicit setup-node step, so hosted-runner availability
must be confirmed by CI. No package dependency or baseline was added. The DOM
double tests emitted JavaScript behavior, not full browser DOM semantics.

### Status

Ready for independent review and browser verification. Provisional readiness
92/100: four points remain for browser proof, four for independent review and
CI. This assessment is not independent acceptance or production closure.

### Files touched

- `substrate/research_artifact/render.py`, one serialization assignment.
- `tests/test_research_artifact_template.py`, emitted JavaScript and real importer regression.
- This diagnostic.

### Milestones (checkboxes)

- [x] Reproduce parser failure before changing production source.
- [x] Escape dynamic JSON without changing note content.
- [x] Verify existing accepted notes, append-only import, and idempotent replay.
- [ ] Root browser verification, independent review and CI.

### Gate results

Commands run from the Env Card worktree. `PY` denotes its stated absolute Python;
Node 22's bin directory leads PATH. Complete logs remain in local `.audit/`.

| Gate | Command | Result | Log |
|---|---|---|---|
| Before fix | `PYTHONPATH=. $PY -m pytest tests/test_research_artifact_template.py -q --tb=short` | Exit 1, one failed and two passed; JSONDecodeError on hostile added note | `.audit/template-before.log` |
| Consumers | `PYTHONPATH=. $PY -m pytest tests/test_research_artifact_template.py tests/test_research_artifact_import.py tests/test_research_artifact_export.py tests/test_research_artifact_blocks.py -q --tb=short` | Exit 0, 37 passed | `.audit/consumer-tests.log` |
| Ruff | `$PY -m ruff check substrate/research_artifact/render.py tests/test_research_artifact_template.py` | Exit 0 | `.audit/ruff.log` |
| Scoped strict types | `$PY -m mypy --follow-imports=silent substrate/research_artifact/render.py` | Exit 0, no issues in one source file | `.audit/mypy.log` |
| Ownership | `python3 /Users/slimydog/Antiek/.infinite/validate-control-plane.py` | Pass, 653 agents / 9 active portfolio / 1751 owned surfaces | Session output |

### Decisions mid-flight

Use Node built-ins and minimal DOM doubles instead of adding a JavaScript engine
package. Execute the actual emitted script so an escaping regression fails on
behavior. Keep storage and importer repairs in the parent branch.

### Assumptions surfaced

The saved HTML must preserve the JSON island's script text literally. The
regression models that boundary by replacing only its content; root's Chrome
check verifies actual `outerHTML` behavior.

### Steelman rejected alternative

A source-string assertion is cheaper but cannot prove that Python and JavaScript
escaping layers produce the intended bytes. The emitted-script test caught the
actual pre-fix failure through the production parser.

### Open questions

Confirm Node availability in the applicable Ubuntu Python CI shard. Root owns
browser evidence and independent review.

### Next sprint can start when

Root completes browser verification and independent assessment of this stacked
change, then chooses its integration sequence with note persistence.

### Out-of-scope temptations

No changes to note storage, importer, event schema, graph authority or parent
branch files beyond the three assigned paths.

### Real-browser follow-up

Chrome exercised the actual Add-note control with literal closing-script tags,
mixed-case tags, Unicode, quotes and a backslash. The machine island contained
no literal less-than signs; JSON parsing restored the exact text. Saving the
edited DOM to a caller HTML file and invoking the actual local import route
returned200 with one accepted note/event. Repeating import returned zero new
notes. After deleting the caller file, re-export returned200 and retained the
exact note. No window errors or unhandled rejections were captured. The screenshot
was visually inspected. Source and evidence hashes are recorded in
[verification JSON](assets/research-note-html-serialization-20260920/browser-verification.json)
and [screenshot](assets/research-note-html-serialization-20260920/add-note.png).

This uses DevTools DOM serialization, not native Save Page, and a minimal real
artifact_router app with an isolated database. Full application authentication,
production, and the broader writing workflow remain unproved. Local server and
isolated Chrome shut down normally. Independent GLM review30151 remains running.

Strict source-only Hardenx scan of the changed renderer and test exited0, LOW,
zero REAL and five advisory findings. Evidence: .audit/serialization-hardenx.json.
This is not dependency or production clearance.
