"""A decision doc that says a gate is BLOCKING must name a gate CI actually runs.

Four decision records carry ``**Status:** ✅ Active (blocking ...)`` and name a
CI step plus a self-test that "reds if the gate is demoted to informational".
For three of them, ``git log -S`` over ``.github/`` returns **zero commits**:
the CI step was never added, and neither was the tripwire that was supposed to
notice. The tools themselves exist and are well written, which is exactly what
makes the docs convincing:

    docs/decisions/reachability-gate.md:4      "Active (blocking ... via the
                                                `reachability` job)"
      -> `python -m tools.reachability.probe_runner` appears in no workflow,
         and never has.

    docs/decisions/ratified-scoring-gate.md:4  "Active (blocking ... via the
                                                `Ratified-scoring gate` step)"
      -> `tools/ratified_gate.py` is referenced only by its own decision doc.

This is the repo's dominant defect class -- a check that reports success while
measuring nothing -- moved up one layer. A green gate that does not run is a
bug; a DOC asserting a gate runs, when the gate was never wired, is worse: it
survives review, gets cited by later decisions, and the absence is invisible
because the tool it names is real.

The check is deliberately narrow. It only reads docs that claim ACTIVE and
BLOCKING, and only asserts that a command the doc says CI runs appears
somewhere in .github/workflows/. It does not judge whether the step is
swallowed, required, or correct -- a doc that survives this is not thereby
accurate, it has merely cleared the lowest bar: the thing it points at exists.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_DECISIONS = _ROOT / "docs" / "decisions"
_WORKFLOWS = _ROOT / ".github" / "workflows"

# Docs whose claim is known-false and which this test is introduced ALONGSIDE
# a correction for. Empty by design: an entry here is a doc still lying.
KNOWN_FALSE_CLAIMS: dict[str, str] = {}

# `pytest` is a job name, not a gate command; every doc mentions it.
_NOT_A_GATE = frozenset({"pytest"})


def _normalised(text: str) -> str:
    """Fold wrapped lines. The docs break ``python -m`` across a newline."""
    return re.sub(r"\s+", " ", text)


def _workflow_corpus() -> str:
    files = sorted(_WORKFLOWS.glob("*.y*ml"))
    assert len(files) >= 5, f"only {len(files)} workflows found — check is vacuous"
    corpus = _normalised("\n".join(f.read_text(encoding="utf-8") for f in files))
    assert len(corpus) > 5000, "workflow corpus implausibly small"
    return corpus


def _blocking_docs() -> list[tuple[str, set[str]]]:
    docs = sorted(_DECISIONS.glob("*.md"))
    assert len(docs) > 50, f"only {len(docs)} decision docs found — check is vacuous"
    out: list[tuple[str, set[str]]] = []
    for doc in docs:
        raw = doc.read_text(encoding="utf-8", errors="ignore")
        # The LIVE claim is the Status field only -- up to the next field or
        # the start of a blockquote. A correction quotes the old wording
        # inside a `>` block, and a quoted claim is not a live one; reading
        # the whole doc would make every corrected record fail forever.
        status_block = re.search(
            r"^\*\*Status:\*\*(.*?)(?=^\*\*|^>|\n\n)", raw, re.M | re.S
        )
        if not status_block:
            continue
        claim = _normalised(status_block.group(1))
        if "Active" not in claim or "blocking" not in claim.lower():
            continue
        text = _normalised(raw)
        # Two styles appear in these records: `python -m pkg.mod` and a bare
        # backticked path like `tools/lint/merge_age_gate.py`. Catch both --
        # reading only the first made every doc that uses the second pass for
        # free, which the detector self-test below caught.
        commands = set(re.findall(r"python -m ([A-Za-z_][\w.]+)", text))
        commands |= set(re.findall(r"`(tools/[\w/]+\.py)`", text))
        out.append((doc.name, commands - _NOT_A_GATE))
    return out


def _referenced(command: str, corpus: str) -> bool:
    """Is this gate invoked by CI, in either notation?

    A doc may write the path (`tools/lint/reachability_gate_py.py`) while the
    workflow invokes the module (`python -m tools.lint.reachability_gate_py`).
    They denote the same file, so comparing the literal strings reports a
    wired gate as missing. Accept either spelling of the same target.
    """
    if command in corpus:
        return True
    if command.endswith(".py"):
        dotted = command[:-3].replace("/", ".")
        if dotted in corpus:
            return True
    return False


def test_detector_sees_the_docs_and_the_workflows() -> None:
    """Guard the guard: a parsing regression must not read as 'all accurate'."""
    docs = _blocking_docs()
    assert docs, "no doc claims an active blocking gate — the parser is broken"
    assert any(cmds for _, cmds in docs), (
        "no blocking doc names a single command — the command extractor is "
        "broken, so every doc would pass for free"
    )


def test_blocking_claims_name_a_gate_that_exists_in_ci() -> None:
    corpus = _workflow_corpus()
    liars: list[str] = []
    for name, commands in _blocking_docs():
        if name in KNOWN_FALSE_CLAIMS:
            continue
        missing = sorted(c for c in commands if not _referenced(c, corpus))
        if missing:
            liars.append(f"{name}: claims CI runs {missing}, which no workflow does")
    assert not liars, (
        "these decision records state a gate is ACTIVE and BLOCKING while "
        "naming a command that appears in no workflow:\n  "
        + "\n  ".join(liars)
        + "\nEither wire the gate, or correct the Status line. A doc that "
        "claims enforcement it does not have is worse than no doc."
    )


def test_known_false_register_is_empty() -> None:
    """The register must stay empty. An entry is a doc still lying."""
    assert not KNOWN_FALSE_CLAIMS, (
        f"decision docs still carrying a false blocking claim: "
        f"{sorted(KNOWN_FALSE_CLAIMS)}"
    )
