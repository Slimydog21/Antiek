REWORK ROUND 2 for SPR-06 (branch drd/spr06-corpus-contract). The re-adjudication (REFUTE-SPR06.md, read in full) RESOLVED findings 2/3/4 but left 1/5/6. These are small and surgical — fix exactly these, nothing else:

FINDING 1 (determinism must be PROVEN, not just possible): the conformance kit and the test factories construct adapters without now_fn, so no run proves deterministic replay. Fix: (a) conformance kit accepts and threads a now_fn into every adapter construction it performs, (b) tests pass a FIXED now_fn everywhere, (c) add one explicit test: two fetches of the same id with the same fixed clock produce EQUAL CorpusDocument (including provenance.retrieved_at). The wall-clock default may remain for production ergonomics ONLY if the kit itself never relies on it — and the docstring must say exactly that.

FINDING 5 (cross-owner test proves the wrong thing): the current test asks for an id absent from the store entirely — that is an unknown-id miss, not cross-owner denial. Fix the test: seed the store with a document that EXISTS globally and belongs to owner-B, construct the adapter scoped to owner-A, fetch that id, assert CorpusMiss. Keep the unknown-id test as its own separate case.

FINDING 6 (ruff red + false handoff): remove the unused FetchResult import (tests/type_check_wrong_adapter.py:12). Then re-run ruff over ALL owned files INCLUDING the new type-check test file: .venv-wt/bin/ruff check substrate/corpus_contract/ tests/test_corpus_contract.py tests/type_check_wrong_adapter.py

HONESTY REQUIREMENT (this is the second round where HANDOFF-SPR06.md overclaimed — "no datetime.now remains" while three lambdas remained; "ruff pass" while F401 was red): rewrite the handoff's gate-results section ONLY from freshly captured command outputs, pasted verbatim. A third overclaim forfeits the lane.

Gates to green, logical commits (no push), do not commit SPEC/REFUTE/REWORK files or .venv-wt.
