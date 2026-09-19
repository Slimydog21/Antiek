MICRO-ROUND for SPR-06, two mechanical items only:
1. tests/test_corpus_contract.py line ~259 (cross-owner test): construct HostedDocsCorpusAdapter with now_fn=_fixed_now like every other test construction. That closes the last literal instance of finding 1.
2. Re-run PYTHONPATH=$PWD .venv-wt/bin/pytest tests/test_corpus_contract.py -q and update HANDOFF-SPR06.md's pytest line from that run. Note: the orchestrator has ruled that pytest TIMING strings are expected to differ between runs — the handoff must honestly reflect YOUR fresh run; nothing more.
One commit, no push. Touch nothing else.
