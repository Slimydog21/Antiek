"""The Reality-Contact Ledger — deterministic JSON over every test file.

Walks every ``test_*.py`` under ``tests/``, classifies each (classifier.py),
and emits ``tools/reality_contact/ledger.json``: per-file verdict, per-subsystem
labels, the core-mock evidence (with ``file:line`` + form), the boundary
contract's content hash + ``schema_version``, and the file count. Stable key
order + stable sort make two runs byte-identical.

A file that fails to parse is recorded as a ``parse-error`` entry WITH its path
— it never aborts the run (honesty: a partial ledger that names the failure
beats a crash).

Regenerate:  ``python -m tools.reality_contact.ledger``

(No package ``__main__.py`` is created here — that file belongs to SPR-02's
scoreboard, so the two sprints never contend for it. This module carries its own
``if __name__ == "__main__"``.)
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from tools.reality_contact import BOUNDARIES_PATH, LEDGER_PATH, REPO_ROOT
from tools.reality_contact.classifier import (
    BoundaryContract,
    FileClassification,
    classify_file,
    load_contract,
)

LEDGER_SCHEMA_VERSION = 1


def discover_test_files(repo_root: Path = REPO_ROOT) -> list[Path]:
    """Every ``test_*.py`` under ``tests/`` — the live tree, sorted for
    determinism. Mirrors ``find tests -name 'test_*.py'`` exactly (recursive,
    name glob), so the ledger's file count equals that command's count."""
    tests_dir = repo_root / "tests"
    return sorted(tests_dir.rglob("test_*.py"))


def _boundaries_hash(contract: BoundaryContract) -> str:
    """SHA-256 of the verbatim boundaries.yaml text the ledger was computed
    against (defensibility: the ledger is pinned to a specific contract)."""
    return "sha256:" + hashlib.sha256(contract.raw_text.encode("utf-8")).hexdigest()


def _entry_to_json(c: FileClassification) -> dict[str, Any]:
    """One file's ledger entry, with stable key order and sorted collections."""
    evidence = sorted(
        (
            {
                "subsystem": e.subsystem,
                "target": e.target,
                "form": e.form,
                "lineno": e.lineno,
                "raw": e.raw,
            }
            for e in c.core_mock_evidence
        ),
        key=lambda d: (d["subsystem"], d["lineno"], d["target"], d["form"]),
    )
    unresolved = sorted(
        (
            {"form": t.form, "lineno": t.lineno, "raw": t.raw}
            for t in c.unresolved_on_core
        ),
        key=lambda d: (d["lineno"], d["form"], d["raw"]),
    )
    entry = {
        "path": c.path,
        "verdict": c.verdict,
        # subsystem_labels emitted with sorted keys for byte-stability.
        "subsystem_labels": {k: c.subsystem_labels[k] for k in sorted(c.subsystem_labels)},
        "core_mock_evidence": evidence,
        "unresolved_on_core": unresolved,
    }
    if c.parse_error is not None:
        entry["parse_error"] = c.parse_error
    return entry


def build_ledger(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Build the full ledger dict (not yet serialized)."""
    contract = load_contract()
    files = discover_test_files(repo_root)
    entries: list[FileClassification] = [
        classify_file(p, repo_root, contract) for p in files
    ]

    # Deterministic order: by path.
    entries.sort(key=lambda c: c.path)

    # Roll-up counts.
    counts: dict[str, int] = {
        "reality": 0,
        "theater": 0,
        "mixed": 0,
        "n-a": 0,
        "indeterminate": 0,
        "parse-error": 0,
    }
    per_subsystem_theater: dict[str, int] = {}
    for c in entries:
        counts[c.verdict] = counts.get(c.verdict, 0) + 1
        for subsystem, label in c.subsystem_labels.items():
            if label == "theater":
                per_subsystem_theater[subsystem] = per_subsystem_theater.get(subsystem, 0) + 1

    # How many tests mock the LLM/TTS provider boundary — a lower bound on the
    # scope the metric is BY DESIGN blind to (provider mocks are BOUNDARY, never
    # theater). Computed from the classifier's recorded boundary hits, so it is
    # deterministic and recomputable.
    _PROVIDER_BOUNDARY = "substrate.dispatch.providers"
    provider_boundary_mock_file_count = sum(
        1 for c in entries if _PROVIDER_BOUNDARY in c.boundary_mock_modules
    )

    return {
        "ledger_schema_version": LEDGER_SCHEMA_VERSION,
        "boundaries_schema_version": contract.schema_version,
        "boundaries_hash": _boundaries_hash(contract),
        "boundaries_path": BOUNDARIES_PATH.relative_to(repo_root).as_posix(),
        "file_count": len(entries),
        "counts": {k: counts[k] for k in sorted(counts)},
        "per_subsystem_theater": {k: per_subsystem_theater[k] for k in sorted(per_subsystem_theater)},
        # The caveat travels WITH the number: SPR-02's scoreboard reads this
        # ledger, not boundaries.yaml's prose. theater=0 does NOT mean "all tests
        # are real" — provider/LLM mocks are BOUNDARY by design, so the
        # "mocked the LLM and asserted a synthesis" pattern is invisible here.
        "known_blind_spots": {
            "provider_mocks_are_boundary": (
                "LLM/TTS provider mocks (substrate.dispatch.providers) and the other "
                "external seams (network, clock, payments, email, browser, third-party "
                "search) are classified BOUNDARY, not theater, BY DESIGN: a test that "
                "stubs the provider and asserts a synthesis is reality-contact for the "
                "orchestrator/graph it actually runs, not theater. So this metric does "
                "NOT detect the 'mocked the LLM and asserted a synthesis' pattern that "
                "motivated it. The boundary contract is pending SPR-06 operator "
                "ratification."
            ),
            "provider_boundary_mock_file_count": provider_boundary_mock_file_count,
            "provider_boundary_mock_file_count_note": (
                "Test files with a statically-resolved mock target under "
                f"'{_PROVIDER_BOUNDARY}'. A value of 0 is EVIDENCE OF the blind spot, not "
                "absence of it: provider/LLM faking in this codebase is done by "
                "DEPENDENCY INJECTION (register_provider(stub), register_providers=False), "
                "NOT by patching the providers module — and DI is invisible to static "
                "mock-detection. So DI-stubbed-LLM tests are counted 'reality' (they "
                "exercise the real orchestrator) even though the synthesis content is "
                "stubbed. SPR-06 should quantify the DI-fake magnitude — a grep of "
                "register_provider / Fake*Provider / StubProvider finds it in ~56 files."
            ),
            "static_analysis_limits": (
                "DI-injected fakes, conftest-fixture injection, dynamically-built mock "
                "targets, and setattr on an unresolvable object fail-safe to "
                "'indeterminate' or are not counted — never silently 'reality'. The "
                "classifier is deliberately conservative, not omniscient."
            ),
        },
        "core_modules": list(contract.core),  # already sorted by the parser
        "boundary_modules": list(contract.boundary),
        "files": [_entry_to_json(c) for c in entries],
    }


def serialize_ledger(ledger: dict[str, Any]) -> str:
    """Byte-stable JSON: sort_keys for the top object is NOT used (we control key
    order explicitly to keep `files` last and human-ordered), but every nested
    dict was built with deterministic key order + sorted collections. Trailing
    newline for POSIX-friendly diffs."""
    return json.dumps(ledger, indent=2, ensure_ascii=False) + "\n"


def write_ledger(repo_root: Path = REPO_ROOT, out_path: Path = LEDGER_PATH) -> dict[str, Any]:
    ledger = build_ledger(repo_root)
    out_path.write_text(serialize_ledger(ledger), encoding="utf-8")
    return ledger


def main() -> int:
    ledger = write_ledger()
    counts = ledger["counts"]
    print(
        f"Reality-Contact Ledger written to "
        f"{LEDGER_PATH.relative_to(REPO_ROOT).as_posix()}"
    )
    print(f"  file_count: {ledger['file_count']}")
    print(f"  boundaries: {ledger['boundaries_hash']} (schema v{ledger['boundaries_schema_version']})")
    print("  verdict counts:")
    for k in sorted(counts):
        print(f"    {k:14s} {counts[k]}")
    if ledger["per_subsystem_theater"]:
        print("  per-subsystem theater:")
        for k, v in ledger["per_subsystem_theater"].items():
            print(f"    {k:40s} {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
