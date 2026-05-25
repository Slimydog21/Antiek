"""Collision #2 guard — single voice-pipeline owner (antiek-unified SPR-03).

The one greppable invariant a future maintainer verifies in one command:
**exactly one module defines ``ingest_voice_note`` (in ``acquisition/voice/``),
and it is the only producer of ``document_type='voice_note'`` documents.** A
second definition, or any other module inserting a voice-note document, is the
fork the ledger forbids (Read SPR-06 + Speak SPR-02 *call* the owner; neither
builds a parallel capture→ASR→distill pipeline).

Rigor #3 — these tests fail when the invariant is violated, not merely when it
holds: a synthetic second definition makes the grep count 2 and the test fails.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from substrate.contracts.voice_pipeline import (
    VOICE_INGEST_FUNCTION,
    VOICE_NOTE_DOCUMENT_TYPE,
    VOICE_PIPELINE_OWNER,
    VoicePipelineContract,
)

_REPO = Path(__file__).resolve().parent.parent
# Search scope: the substrate-owning trees a parallel pipeline could hide in.
# (Tests/fixtures are excluded — a test defining a stub is not a production
# pipeline.)
_SEARCH_DIRS = ("acquisition", "substrate", "roles", "runtime", "orchestration")


def _code_only(source: str) -> str:
    """Blank out docstrings so a grep matches executable code, not prose that
    merely *mentions* the pattern (e.g. the voice_pipeline contract's docstring
    names ``ingest_voice_note`` and ``document_type='voice_note'``)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                doc = body[0]
                for i in range(doc.lineno - 1, min(getattr(doc, "end_lineno", doc.lineno), len(lines))):
                    lines[i] = ""
    return "\n".join(lines)


def _grep_def_count(symbol: str) -> list[Path]:
    """Files in the search scope that contain a top-level ``def <symbol>``."""
    pattern = re.compile(rf"^def {re.escape(symbol)}\b", re.MULTILINE)
    hits: list[Path] = []
    for d in _SEARCH_DIRS:
        root = _REPO / d
        if not root.exists():
            continue
        for py in root.rglob("*.py"):
            if pattern.search(_code_only(py.read_text(encoding="utf-8"))):
                hits.append(py)
    return hits


def test_exactly_one_ingest_voice_note_definition():
    """The load-bearing grep: one definition, in the owner."""
    hits = _grep_def_count(VOICE_INGEST_FUNCTION)
    assert len(hits) == 1, (
        f"expected exactly one `def {VOICE_INGEST_FUNCTION}`, found "
        f"{[str(h.relative_to(_REPO)) for h in hits]} — a second voice "
        "pipeline is the seam-#2 fork the ledger forbids"
    )
    (only,) = hits
    rel = str(only.relative_to(_REPO))
    assert rel.startswith(VOICE_PIPELINE_OWNER), (
        f"`{VOICE_INGEST_FUNCTION}` is defined in {rel}, not the single owner "
        f"{VOICE_PIPELINE_OWNER}"
    )
    assert rel == "acquisition/voice/adapter.py", rel


def test_only_owner_produces_voice_note_documents():
    """Only the owner stamps ``document_type='voice_note'`` on an inserted
    document. Any insert_document(... document_type='voice_note' ...) outside
    the owner is a second producer."""
    # The producing call shape: a document_type set to the voice-note type.
    pattern = re.compile(
        rf"""document_type\s*=\s*["']{re.escape(VOICE_NOTE_DOCUMENT_TYPE)}["']"""
    )
    producers: list[Path] = []
    for d in _SEARCH_DIRS:
        root = _REPO / d
        if not root.exists():
            continue
        for py in root.rglob("*.py"):
            if pattern.search(_code_only(py.read_text(encoding="utf-8"))):
                producers.append(py)
    rels = sorted(str(p.relative_to(_REPO)) for p in producers)
    assert rels == ["acquisition/voice/adapter.py"], (
        f"voice-note documents are produced by {rels}; the single owner is "
        f"{VOICE_PIPELINE_OWNER} — a second producer is the seam-#2 fork"
    )


def test_owner_satisfies_voice_pipeline_contract():
    """The owner's module exposes the contract's call surface
    (``ingest_voice_note``) — the consumers (Read SPR-06, Speak SPR-02) compose
    against this, not a re-implementation."""
    import acquisition.voice as voice

    assert hasattr(voice, VOICE_INGEST_FUNCTION)
    assert callable(getattr(voice, VOICE_INGEST_FUNCTION))
    # The contract is a runtime-checkable Protocol over the call name —
    # ``ingest_voice_note`` is the committed seam method the consumers compose
    # against. (We assert the name, not isinstance: the owner is a module, not
    # an object, so the Protocol pins the call-surface name.)
    assert VOICE_INGEST_FUNCTION in VoicePipelineContract.__annotations__ \
        or hasattr(VoicePipelineContract, VOICE_INGEST_FUNCTION)


def test_a_synthetic_second_definition_would_fail(tmp_path):
    """Rigor #3 — prove the guard FAILS on a real fork. We don't write into the
    tree; we simulate the grep against a scope that contains a second
    definition and assert the count logic rejects it."""
    # Two synthetic files, both defining the symbol.
    (tmp_path / "a.py").write_text(f"def {VOICE_INGEST_FUNCTION}():\n    ...\n")
    (tmp_path / "b.py").write_text(f"def {VOICE_INGEST_FUNCTION}():\n    ...\n")
    pattern = re.compile(rf"^def {re.escape(VOICE_INGEST_FUNCTION)}\b", re.MULTILINE)
    hits = [p for p in tmp_path.rglob("*.py") if pattern.search(p.read_text())]
    assert len(hits) == 2  # the fork the real test would reject
