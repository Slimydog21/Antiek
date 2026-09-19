# SPR-06 Final Adjudication

1. **UNRESOLVED — determinism is explicitly tested, but the fixed clock is still not threaded everywhere tests construct adapters.** `_make_twin_adapter` and `_make_hosted_adapter` both pass `_fixed_now`, all three `BrokenProvenanceAdapter` constructions pass `_fixed_now`, and both reference adapters have an explicit determinism test through `assert_fetch_determinism` (`tests/test_corpus_contract.py:121,153,190-192,224-226,277,286,290`; `substrate/corpus_contract/conformance.py:211-229`). Those tests pass and compare the complete `CorpusDocument`, including provenance. However, the cross-owner test constructs `HostedDocsCorpusAdapter(reader, owner_id="owner-A")` without `now_fn` (`tests/test_corpus_contract.py:259`). That path currently fetches a miss and therefore does not call the clock, but the round-2 requirement was unambiguous that tests pass a FIXED `now_fn` everywhere they construct adapters. The wall-clock default is documented as production-only, yet a kit test path still relies on that default constructor configuration. The substantive replay proof is present, but the literal finding is not fully resolved.

5. **RESOLVED — the cross-owner test now denies an existing foreign document.** The test seeds `foreign_doc_id` in the global `docs` store, assigns it to `owner-B`, gives `owner-A` an empty membership list, scopes the adapter to `owner-A`, fetches that exact existing foreign ID, and asserts `CorpusMiss` (`tests/test_corpus_contract.py:228-263`). This is owner-scope denial, not an unknown-ID miss.

6. **UNRESOLVED — all three gates are green, but the handoff does not match the fresh pytest output verbatim.** Fresh commands produced:

```
$ .venv-wt/bin/python -m pytest tests/test_corpus_contract.py -q
21 passed in 0.35s

$ .venv-wt/bin/mypy substrate/corpus_contract/ --strict --ignore-missing-imports
Success: no issues found in 6 source files

$ .venv-wt/bin/ruff check substrate/corpus_contract/ tests/test_corpus_contract.py tests/type_check_wrong_adapter.py
All checks passed!
```

Ruff is clean and the unused import is gone. Mypy matches the handoff. The handoff records `21 passed in 0.32s`, not the fresh `21 passed in 0.35s`, so its gate section does not match fresh command output verbatim as required. No functional gate failure was found.

NEW findings: none.

VERDICT: REWORK — findings 1 and 6
