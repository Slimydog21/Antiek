REWORK ROUND for your SPR-02 research-brief deliverable in this worktree (branch drd/spr02-brief-gate). An independent adversarial reviewer executed the sprint's own verifier lens ("obtain a run token without approval through any code path") and it landed on 3 of 3 paths. VERDICT: REWORK — findings 1,2 mandatory; address the MINORs 3-6 where cheap.

FINDING 1 (MAJOR, mandatory): parse_html trusts data-state — flipping data-state="draft" to "approved" in the projected HTML then run_token(parse_html(...)) mints a valid token with zero approval events (project_html.py:88, lifecycle.py:43). Fix so the sanctioned editable-HTML path cannot smuggle state: parse_html must refuse non-draft state, or reset parsed briefs to DRAFT with a documented rule — the editable artifact edits CONTENT, never lifecycle state. Add the red-proof test (tampered data-state cannot yield a token).

FINDING 2 (MAJOR, mandatory): ResearchBrief is directly constructible with state=APPROVED and empty events, and run_token accepts it (model.py:49-59). Fix: constrain construction to DRAFT (post_init rejects non-draft initial state unless accompanied by a consistent event trail), AND make run_token require a non-empty approval event trail whose last event is the approval. Add the red-proof test (constructed-APPROVED brief with no events cannot yield a token).

FINDING 3 (MINOR): RunToken("x","deadbeef") fabricates authorization with no brief. Cheap hardening: module-private constructor discipline — document that RunToken possession is only meaningful with a verifiable brief_hash, or make the constructor validate hash shape; at minimum correct the docstring's absolute claim.

FINDING 4 (MINOR): replace() on an APPROVED brief alters content silently and run_token mints over the altered hash. Cheap fix if it falls out of finding 2's event-trail check (hash-at-approval recorded in the approval event, run_token verifies current content hash equals approval-event hash — this ALSO fixes finding 5's volatile-hash issue if you hash content-only fields). Otherwise document honestly.

FINDING 5 (MINOR): brief_content_hash includes volatile fields (state, events) via asdict wholesale (provenance.py:20-25), so the hash cannot be reconstructed from the editable HTML round-trip. Recommended with finding 4: hash CONTENT fields only (question, scope, exclusions, source_preferences, budget, price_ceiling, unattended) — stable across lifecycle, reconstructible from HTML.

FINDING 6 (MINOR): APPROVED-is-terminal has no pinning test. Add the one-line raise assertion.

Then: re-run all gates until green (PYTHONPATH=$PWD .venv-wt/bin/pytest tests/test_research_brief.py -q; .venv-wt/bin/mypy --strict substrate/research_brief/; .venv-wt/bin/ruff check substrate/research_brief/ tests/test_research_brief.py), commit in logical commits (no push, no PRs), update HANDOFF-SPR02.md honestly. Never weaken a gate. Do not commit SPEC-SPR02.html, REWORK-BRIEF.md, or .venv-wt.
