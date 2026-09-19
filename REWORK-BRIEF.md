REWORK ROUND for your SPR-06 corpus-contract deliverable in this worktree (branch drd/spr06-corpus-contract). An independent adversarial reviewer REJECTED it with 5 findings — all confirmed real. Fix every one. The spec (SPEC-SPR06.html) and the findings (REFUTE-SPR06.md, read it in full) are in this directory.

Required fixes:

1. (MAJOR) Inject the clock: adapters and the conformance broken-adapter take a now_fn/clock parameter; no datetime.now calls anywhere inside substrate/corpus_contract/. Update the Provenance docstring truthfully.

2. (BLOCKER) Read-only must be structural, not name-prefix theater: narrow the reader Protocols so a conforming reader exposes ONLY the read methods the adapter uses, keep the retained reference private, and make assert_read_only verify the adapter's PUBLIC surface exposes no reader handle at all. Document any residual limit honestly in the conformance docstring.

3. (MAJOR) Harden assert_search_retrieval: additionally assert (a) a non-matching decoy fixture doc is NOT ranked above the seeded doc, (b) returned scores are non-increasing, (c) a query matching nothing returns zero hits.

4. (BLOCKER) Add the negative static type proof that M1 demands and the current handoff falsely claims exists: a wrong-signature adapter that mypy provably rejects (e.g. a type-check-only module asserting the assignment fails, using a "type: ignore[arg-type]" expectation that mypy enforces via warn-unused-ignores, or an equivalent mechanism that makes the gate fail if the Protocol stops rejecting bad adapters). Then correct HANDOFF-SPR06.md to the truth.

5. (BLOCKER) hosted_docs.fetch must enforce the adapter's declared owner scope: a document_id outside the owner scope returns CorpusMiss; add a test proving the cross-owner case.

Then re-run ALL gates until green:
  PYTHONPATH=$PWD .venv-wt/bin/pytest tests/test_corpus_contract.py -q
  .venv-wt/bin/mypy --strict substrate/corpus_contract/
  .venv-wt/bin/ruff check substrate/corpus_contract/ tests/test_corpus_contract.py

Commit the fixes as logical commits (do NOT push, do NOT open PRs), and update HANDOFF-SPR06.md honestly (including finding-2 residual limits, if any). Never weaken a gate or delete a failing test to pass. Do not commit SPEC-SPR06.html, REFUTE-SPR06.md, REWORK-BRIEF.md, or .venv-wt.
