# tools/golden_traces/

Capture + replay infrastructure for the Sprint 5 `orchestrate.py`
extraction. The 3,361-LOC monolith has four roles embedded
(decomposer → evidence_retriever → parameter_extractor → connector →
synthesizer). Each role gets extracted into `roles/<name>/` one at a
time; each extraction must replay against captured Researchmaxx
traces and produce equivalent output before the next extraction
starts.

This module ships the capture + replay scripts + schema. Sprint 5
will import `replay_trace_strict` into the per-role extraction tests.

## Files

- `schema.py` — Pydantic `GoldenTrace` + `RoleCall` models +
  `stable_json_hash` helper (deterministic SHA-256 over sorted JSON).
- `capture.py` — operator-runnable script that builds a `GoldenTrace`
  from a Researchmaxx events JSONL.
- `replay.py` — strict hash-equal comparison between a captured trace
  and an Antiek replay's role calls.
- `captured/` — captured traces live here. Committed to git.

## Operator workflow (Sprint 5 dependency)

```bash
# 1. Pick a representative investigation question. Spec target: 3
#    traces covering different question shapes (quantitative thesis,
#    qualitative review, comparison analysis).

# 2. Run the live Researchmaxx orchestrate.py against the question.
#    Trajectory lands at ~/.hermes/research_events/<investigation_id>.jsonl

cd ~/.hermes/skills/research/graph-research-substrate/scripts
python orchestrate.py \
    --target "Is PsiQuantum's photonic-qubit roadmap defensible?" \
    --investigation-id psi-quantum-2026-q2

# 3. Capture the trace into Antiek.
cd ~/Desktop/Antiek
python tools/golden_traces/capture.py \
    --trajectory ~/.hermes/research_events/psi-quantum-2026-q2.jsonl \
    --investigation-id psi-quantum-2026-q2 \
    --question "Is PsiQuantum's photonic-qubit roadmap defensible?" \
    --researchmaxx-commit $(cd ~/.hermes/skills/research/graph-research-substrate && git rev-parse HEAD) \
    --output tools/golden_traces/captured/psi-quantum.json \
    --notes "Quantitative thesis with hard numeric constraints"

# 4. Commit the captured trace so Sprint 5 tests can reference it.
git add tools/golden_traces/captured/psi-quantum.json
git commit -m "feat: capture golden trace — psi-quantum thesis"
```

## Replay (Sprint 5 — used by extraction tests)

```python
# Inside a Sprint 5 extraction test:

from pathlib import Path
from tools.golden_traces import load_trace, replay_trace_strict

cap = load_trace(Path("tools/golden_traces/captured/psi-quantum.json"))

# After Antiek's extracted decomposer runs against the same
# inputs, build a list of RoleCall objects representing the
# replay output:
replayed_calls = [...]  # built by the test from Antiek outputs

report = replay_trace_strict(cap, replayed_calls)
assert report.exact_signature_match, (
    f"replay drift: {[c for c in report.per_call if not c.output_match]}"
)
```

## What "match" means

**Strict match** (today): every captured role call's
`(input_hash, output_hash)` pair equals the replay's. This catches
non-LLM drift cheaply.

**Lenient match** (Sprint 5): structural equivalence for LLM roles
that exhibit nondeterminism. Each role needs a specific comparator
(e.g. Decomposer: sub_question set + keyword set match regardless of
order; Synthesizer: harder — needs a content-rubric comparator).
Ships when the first LLM-role extraction test in Sprint 5 needs it.

## Why this gates the orchestrate.py extraction

Without golden traces, extracting a 3,361-LOC monolith into 5 typed
role modules is destructive surgery — there's no signal that the new
roles produce equivalent output. With traces, each extraction PR
shows "captured signature X / replayed signature Y" and the diff
makes drift visible.

This is the same ratchet pattern Sprint 5's spec calls for:
> Capture 2-3 golden Researchmaxx investigation traces FIRST.
> Then extract one role at a time and assert trace replay holds.
