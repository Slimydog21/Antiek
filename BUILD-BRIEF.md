You are the implementation builder for ONE spec sprint. Your complete operating manual is SPEC-SPR08.html in this directory — read it fully first (standalone: context, milestones M1-M4, acceptance criteria, rigor rules, verification gates, handoff format). Branch: drd/spr08-web-layer.

Execution rules:
1. Milestones in order. Owned files ONLY: acquisition/web_layer/* and tests/test_web_layer.py. Zero edits elsewhere; never commit SPEC-SPR08.html, BUILD-BRIEF.md, or .venv-wt.
2. Gate env: uv venv .venv-wt --python 3.14 && VIRTUAL_ENV=$PWD/.venv-wt uv pip install -c tools/lints/constraints.txt -e '.[dev]' 'ruff==0.15.15' 'mypy==2.1.0'
3. Fleet lessons that WILL be checked by the adversarial reviewer (siblings failed review for each): clocks/HTTP injected everywhere with tests passing FIXED values (no wall-clock reliance in any test path); the swap-seam interface suite must run against BOTH extraction implementations with zero vendor-specific carve-outs; key-hygiene = a typed config error BEFORE any HTTP when the key is missing, plus an assertion that the key appears in neither repr() nor str() of the client; every price/limit number carries a citation comment with a date-stamp; ruff/mypy/pytest must cover EVERY owned file including the test file.
4. Read integration_exa_browserbase.md (docs/) before designing the interfaces — the adapter shape was decided there; divergence must be justified in the handoff.
5. Cost math: pure, hand-computed test to the cent, per-vendor rows date-stamped.
6. Commit per-milestone (no push, no PRs). Handoff to HANDOFF-SPR08.md in the spec's format, gate outputs pasted verbatim from fresh runs.
