"""Tests for the Reality-Contact classifier (SPR-01, M5).

Fixture-driven: each extraction FORM is detected, each VERDICT is correct, the
near-miss negatives are NOT flagged, and an unresolved-target-on-core lands
`indeterminate` (never `reality`). Plus the boundary-contract invariants: every
CORE entry imports cleanly, CORE ∩ BOUNDARY = ∅, and no entry lacks a
justification.

By the classifier's OWN definition these tests are `reality`: they import and
exercise the real classifier/extractor/ledger modules and mock NOTHING on a core
path (they mock nothing at all). Each detection assertion is designed to BITE —
the handoff records a revert-demo proving a test goes red when a detection form
is disabled.
"""

from __future__ import annotations

import importlib
import subprocess
from pathlib import Path

import pytest

from tools.reality_contact import REPO_ROOT
from tools.reality_contact.classifier import (
    classify_source,
    load_contract,
)
from tools.reality_contact.extract import extract_file
from tools.reality_contact.ledger import (
    build_ledger,
    discover_test_files,
    serialize_ledger,
)

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "reality_contact"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# M1 — boundary contract invariants
# --------------------------------------------------------------------------- #
def test_every_core_entry_imports_cleanly():
    """A typo'd CORE module name silently reclassifies all its tests as
    `reality` — the worst failure this sprint can make. Every CORE entry MUST
    import."""
    contract = load_contract()
    failures = []
    for module in contract.core:
        try:
            importlib.import_module(module)
        except Exception as exc:  # noqa: BLE001 — we want the message
            failures.append(f"{module}: {type(exc).__name__}: {exc}")
    assert not failures, "CORE modules failed to import:\n" + "\n".join(failures)


def test_core_and_boundary_are_disjoint():
    contract = load_contract()
    overlap = contract.core_set() & contract.boundary_set()
    assert overlap == frozenset(), f"CORE ∩ BOUNDARY must be empty, got {overlap}"


def test_contract_has_a_schema_version_and_nonempty_lists():
    contract = load_contract()
    assert contract.schema_version >= 1
    assert contract.core, "CORE list must not be empty"
    assert contract.boundary, "BOUNDARY list must not be empty"


def test_loading_boundaries_with_missing_justification_raises(tmp_path):
    """Defensibility: an entry with no justification is rejected at load."""
    from tools.reality_contact.classifier import _parse_boundaries

    bad = (
        "schema_version: 1\n"
        "core:\n"
        "  - module: substrate.graph.ops\n"
        "    justification: ''\n"
        "boundary:\n"
        "  - module: httpx\n"
        "    justification: net\n"
    )
    with pytest.raises(ValueError, match="lacks a justification"):
        _parse_boundaries(bad)


# --------------------------------------------------------------------------- #
# M2 — extraction forms (each positive fixture detected at the right target/line)
# --------------------------------------------------------------------------- #
def test_extract_decorator_form():
    targets = extract_file(FIXTURES / "form_decorator_core.py")
    hits = [t for t in targets if t.form == "decorator"]
    assert len(hits) == 1
    assert hits[0].target == "orchestration.loop_one.orchestrator._run_investigation"
    assert hits[0].resolved is True
    assert hits[0].lineno > 0


def test_extract_with_context_manager_form():
    targets = extract_file(FIXTURES / "form_with_core.py")
    hits = [t for t in targets if t.form == "with"]
    assert len(hits) == 1
    assert hits[0].target == "substrate.dispatch.router.dispatch"
    assert hits[0].resolved is True


def test_extract_patch_object_form():
    targets = extract_file(FIXTURES / "form_patch_object_core.py")
    # patch.object(compute, "...") sits inside a `with`, so its form is "with".
    hits = [t for t in targets if "object" in t.raw]
    assert len(hits) == 1
    assert hits[0].target == "substrate.attribution.compute.compute_attribution_for_synthesis"
    assert hits[0].resolved is True


def test_extract_monkeypatch_string_form():
    targets = extract_file(FIXTURES / "form_monkeypatch_str_core.py")
    hits = [t for t in targets if t.form == "monkeypatch"]
    assert len(hits) == 1
    assert hits[0].target == "substrate.graph.ops.insert_document"
    assert hits[0].resolved is True


def test_extract_monkeypatch_object_form():
    targets = extract_file(FIXTURES / "form_monkeypatch_obj_core.py")
    hits = [t for t in targets if t.form == "monkeypatch"]
    assert len(hits) == 1
    assert hits[0].target == "substrate.graph.search.search"
    assert hits[0].resolved is True


def test_extract_aliased_monkeypatch_receiver_is_caught():
    """Round-2 hardening: a setattr via an ALIASED monkeypatch receiver (named
    `mp`, not `monkeypatch`) on a core symbol must still be extracted. Keying on
    the receiver NAME would silently drop it and mislabel the file `reality` —
    the one false-`reality` path this instrument exists to close."""
    targets = extract_file(FIXTURES / "form_monkeypatch_aliased_receiver_core.py")
    hits = [t for t in targets if t.target == "substrate.graph.ops.insert_document"]
    assert len(hits) == 1, "aliased-receiver setattr on a core symbol must be caught"
    assert hits[0].resolved is True
    assert hits[0].form == "monkeypatch"


def test_extract_mocker_form():
    targets = extract_file(FIXTURES / "form_mocker_core.py")
    hits = [t for t in targets if t.form == "mocker"]
    assert len(hits) == 1
    assert hits[0].target == "substrate.graph.schema.init_database_at_path"
    assert hits[0].resolved is True


def test_extract_mock_ctor_shadow_form():
    targets = extract_file(FIXTURES / "form_mock_ctor_shadow_core.py")
    hits = [t for t in targets if t.form == "mock-ctor-shadow"]
    assert len(hits) == 1
    assert hits[0].target == "substrate.dispatch.router.dispatch"
    assert hits[0].resolved is True


def test_unresolved_dynamic_target_is_recorded_not_dropped():
    targets = extract_file(FIXTURES / "indeterminate_unresolved_core.py")
    unresolved = [t for t in targets if not t.resolved]
    assert len(unresolved) == 1, "the dynamic patch target must be recorded as unresolved"
    assert unresolved[0].target is None
    assert unresolved[0].lineno > 0


def test_near_miss_local_patch_name_not_extracted_as_mock():
    """A local var named `patch` (no unittest.mock.patch import) and a MagicMock
    used as input DATA must NOT produce mock targets that mislabel the file."""
    targets = extract_file(FIXTURES / "near_miss_local_patch_name.py")
    # The only resolvable target is the monkeypatch on `orch` (a NON-core alias).
    core_like = [t for t in targets if t.target and "substrate.graph" in t.target]
    assert core_like == [], "no core target should be extracted from the near-miss file"


def test_na_fixture_magicmock_input_data_not_a_shadow():
    """A MagicMock bound to a name that is not an import alias is input data,
    not a shadow over a core symbol — it must not be emitted."""
    targets = extract_file(FIXTURES / "na_pure_util.py")
    shadows = [t for t in targets if t.form == "mock-ctor-shadow"]
    assert shadows == []


# --------------------------------------------------------------------------- #
# M3 — verdicts
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "fixture,expected_verdict",
    [
        ("form_decorator_core.py", "theater"),
        ("form_with_core.py", "theater"),
        ("form_patch_object_core.py", "theater"),
        ("form_monkeypatch_str_core.py", "theater"),
        ("form_monkeypatch_obj_core.py", "theater"),
        ("form_monkeypatch_aliased_receiver_core.py", "theater"),
        ("form_mocker_core.py", "theater"),
        ("form_mock_ctor_shadow_core.py", "theater"),
        ("reality_boundary_only.py", "reality"),
        ("reality_boundary_symbol_carveout.py", "reality"),
        ("na_pure_util.py", "n-a"),
        ("near_miss_local_patch_name.py", "reality"),
        ("indeterminate_unresolved_core.py", "indeterminate"),
        ("mixed_two_subsystems.py", "mixed"),
    ],
)
def test_verdicts(fixture, expected_verdict):
    src = _read(fixture)
    result = classify_source(fixture, src)
    assert result.verdict == expected_verdict, (
        f"{fixture}: expected {expected_verdict}, got {result.verdict} "
        f"(labels={result.subsystem_labels})"
    )


def test_theater_evidence_cites_the_core_symbol():
    """A theater verdict must carry evidence naming the mocked core symbol +
    file:line + form (SPR-02 reads this)."""
    result = classify_source(
        "form_decorator_core.py", _read("form_decorator_core.py")
    )
    assert result.core_mock_evidence
    ev = result.core_mock_evidence[0]
    assert ev.subsystem == "orchestration.loop_one.orchestrator"
    assert ev.target == "orchestration.loop_one.orchestrator._run_investigation"
    assert ev.lineno > 0
    assert ev.form == "decorator"


def test_indeterminate_never_emits_reality_label():
    """Honesty bar: an unresolved-on-core target must keep the subsystem out of
    `reality`."""
    result = classify_source(
        "indeterminate_unresolved_core.py", _read("indeterminate_unresolved_core.py")
    )
    assert result.verdict == "indeterminate"
    assert "reality" not in set(result.subsystem_labels.values())


def test_mixed_records_per_subsystem_labels():
    result = classify_source("mixed_two_subsystems.py", _read("mixed_two_subsystems.py"))
    assert result.subsystem_labels["substrate.attribution.compute"] == "theater"
    assert result.subsystem_labels["substrate.graph.ops"] == "reality"


def test_parse_error_is_recorded_not_raised():
    result = classify_source("broken.py", "def f(:\n    pass\n")
    assert result.verdict == "parse-error"
    assert result.parse_error is not None


def test_boundary_symbol_carveout_is_not_theater():
    """A mock landing EXACTLY on a boundary_symbol carve-out (the config loader)
    is a boundary-stub, not theater — even though the symbol sits under a core
    module. But a mock on the routing core itself (dispatch) IS still theater."""
    # The carve-out stub → reality, no core-mock evidence.
    carve = classify_source(
        "reality_boundary_symbol_carveout.py",
        _read("reality_boundary_symbol_carveout.py"),
    )
    assert carve.verdict == "reality"
    assert carve.core_mock_evidence == []
    # The contract carves out from_yaml but NOT dispatch: a dispatch() stub is
    # still theater (the carve-out is surgical, not a whole-module demotion).
    contract = load_contract()
    assert "substrate.dispatch.router.DispatchConfig.from_yaml" in contract.boundary_symbol_set()
    assert "substrate.dispatch.router.dispatch" not in contract.boundary_symbol_set()
    still_theater = classify_source("form_with_core.py", _read("form_with_core.py"))
    assert still_theater.verdict == "theater"  # patches router.dispatch


# --------------------------------------------------------------------------- #
# M4 — ledger determinism + coverage
# --------------------------------------------------------------------------- #
def test_ledger_file_count_matches_find():
    """The ledger's file_count must equal `find tests -name 'test_*.py' | wc -l`
    on the live tree."""
    ledger = build_ledger()
    discovered = discover_test_files()
    # Cross-check against the actual shell find the gate uses.
    out = subprocess.run(
        ["bash", "-lc", "find tests -name 'test_*.py' | wc -l"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    find_count = int(out.stdout.strip())
    assert ledger["file_count"] == len(discovered) == find_count


def test_ledger_is_byte_identical_across_two_builds():
    a = serialize_ledger(build_ledger())
    b = serialize_ledger(build_ledger())
    assert a == b


def test_ledger_embeds_boundaries_hash_and_schema_version():
    ledger = build_ledger()
    assert ledger["boundaries_hash"].startswith("sha256:")
    assert ledger["boundaries_schema_version"] >= 1
    assert "ledger_schema_version" in ledger


def test_ledger_carries_known_blind_spots():
    """The theater=0 caveat must travel WITH the number into the ledger. SPR-02's
    scoreboard reads the ledger, not boundaries.yaml's prose — so the operator
    sees, at the point of the number, that provider/LLM mocks are BOUNDARY-by-
    design and the 'mocked the LLM, asserted a synthesis' pattern is invisible to
    theater. A clean-looking number without its caveat is exactly the false
    confidence this whole spec exists to break."""
    ledger = build_ledger()
    kbs = ledger.get("known_blind_spots")
    assert isinstance(kbs, dict), "ledger must carry a known_blind_spots block"
    assert kbs.get("provider_mocks_are_boundary"), "must state the provider-is-boundary design"
    count = kbs.get("provider_boundary_mock_file_count")
    assert isinstance(count, int) and count >= 0
    assert kbs.get("static_analysis_limits"), "must state the static-analysis limits"


def test_ledger_runs_over_all_files_without_raising():
    """The full run must not raise on ANY real test file; parse errors are
    recorded, not fatal."""
    ledger = build_ledger()
    assert ledger["file_count"] > 0
    # Every entry has a verdict in the closed set.
    allowed = {"reality", "theater", "mixed", "n-a", "indeterminate", "parse-error"}
    for entry in ledger["files"]:
        assert entry["verdict"] in allowed


def test_no_resolved_core_mock_yields_reality_when_unresolved_absent():
    """A file importing a core and mocking only a boundary, with no unresolved
    target, is reality (the §reality definition is exercised against the real
    classifier — this test mocks nothing on a core path)."""
    result = classify_source("reality_boundary_only.py", _read("reality_boundary_only.py"))
    assert result.verdict == "reality"
    assert set(result.subsystem_labels.values()) == {"reality"}


# --------------------------------------------------------------------------- #
# Self-reference: these very tests are `reality` by the classifier's definition.
# --------------------------------------------------------------------------- #
def test_this_test_file_classifies_as_reality():
    """The classifier's own definition applied to THIS file: it imports the real
    classifier package and mocks nothing on a core path, so it must be
    reality (it imports no CORE subsystem itself → n-a, OR reality if it did).
    We assert it is NOT theater/indeterminate — the test suite does not stub the
    thing it tests."""
    me = Path(__file__)
    result = classify_source(me.name, me.read_text(encoding="utf-8"))
    assert result.verdict in {"reality", "n-a"}
    assert result.verdict not in {"theater", "indeterminate", "mixed"}
