"""Tests for the test census (tools/test_census.py).

These tests assert the census's OUTPUT — the TestFnRecord / ModuleRecord / JSON
it produces — for a hand-authored fixture corpus of known shapes. They RUN the
census; they do NOT mock it (mocking the census to test the census would be the
exact green-on-mocks disease the census exists to surface). Per the sprint's
own rigor bar, this is the census dog-fooding its own contract: every assertion
checks behavior, not call shape.

The fixture corpus lives in fixtures/census/ — one file per shape (pure
behavior, structure-only, asserts-own-mock-return, monkeypatch+env+local-fake,
no-assert smoke, mixed, and the three round-2 regression shapes: a method-call /
mock-symbol-spelling collision [B1], a mock-factory-helper caller [B2], and an
assert-helper-only test [MAJOR]). It is parsed by the census with ``ast``, never
executed by pytest (it is outside ``testpaths``).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tools.test_census import (  # noqa: E402
    TestFnRecord,
    _is_env_var_name,
    _tag_target,
    build_census,
    dumps,
    render_report,
)

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "census"


def _census():
    return build_census(_REPO, _FIXTURES)


def _by_name(c, name: str) -> TestFnRecord:
    matches = [t for t in c.tests if t.name == name]
    assert len(matches) == 1, f"expected exactly one {name}, got {len(matches)}"
    return matches[0]


# ---------------------------------------------------------------------------
# Per-shape classification — the predictive flag + mock detection
# ---------------------------------------------------------------------------


def test_pure_behavior_is_behavior_and_no_mock():
    c = _census()
    rec = _by_name(c, "test_add_returns_sum")
    assert rec.predictive == "behavior"
    assert rec.uses_mock is False
    assert rec.mock_targets == ()
    assert rec.assert_count == 1


def test_raises_is_behavior():
    c = _census()
    rec = _by_name(c, "test_divide_raises_on_zero")
    # pytest.raises is a behavior assertion even though the assert statement
    # count is zero — the raised exception IS the asserted output.
    assert rec.predictive == "behavior"


def test_structure_only_assert_called_is_structure():
    c = _census()
    rec = _by_name(c, "test_notify_calls_send_once")
    assert rec.predictive == "structure"
    assert rec.reason == "asserts-call-shape"
    assert rec.uses_mock is True


def test_structure_only_call_count_is_structure():
    c = _census()
    rec = _by_name(c, "test_notify_call_count_is_one")
    assert rec.predictive == "structure"
    assert rec.reason == "asserts-call-shape"


def test_asserts_own_mock_return_is_structure_with_reason():
    c = _census()
    rec = _by_name(c, "test_fetch_total_returns_configured_value")
    assert rec.predictive == "structure"
    assert rec.reason == "asserts-own-mock-return"
    assert rec.uses_mock is True


def test_monkeypatch_env_is_behavior_with_environmental_target():
    c = _census()
    rec = _by_name(c, "test_reads_env")
    assert rec.predictive == "behavior"
    assert rec.uses_mock is True
    assert "MY_FLAG" in rec.mock_targets
    # An env-var target is environmental, never behavioral.
    assert _tag_target("MY_FLAG") == "environmental"


def test_local_fake_present_but_asserts_behavior_is_not_structure():
    # The steelman (rigor #2): a behavioral-collaborator fake is PRESENT, but
    # the test asserts the unit's real output, so it is behavior, NOT structure.
    c = _census()
    rec = _by_name(c, "test_uses_local_fake")
    assert rec.predictive == "behavior"
    assert rec.uses_mock is True
    assert "FakeProvider" in rec.mock_targets
    assert _tag_target("FakeProvider") == "behavioral"


def test_no_assert_smoke_is_none():
    c = _census()
    assert _by_name(c, "test_smoke_runs").predictive == "none"
    assert _by_name(c, "test_trivial_true").predictive == "none"


def test_mixed_is_mixed():
    c = _census()
    rec = _by_name(c, "test_dispatches_and_returns")
    assert rec.predictive == "mixed"
    assert rec.uses_mock is True


# ---------------------------------------------------------------------------
# Round-2 regression tests — each BITES on a round-1 defect: it asserts the
# FIXED classification AND (where the failure was a misclassification) proves
# the old shape would have produced the wrong answer.
# ---------------------------------------------------------------------------


def test_B1_method_call_collision_is_not_mock(tmp_path):
    # The committed fixture: p.call(...) / client.seal() / Box.ANY are ordinary
    # product reads, not unittest.mock constructions. The FIX requires this to
    # be behavior + uses_mock=False with NO call/seal/ANY/sentinel target.
    c = _census()
    rec = _by_name(c, "test_provider_call_is_not_mock_construction")
    assert rec.uses_mock is False, "ordinary p.call() must not flag uses_mock"
    assert rec.predictive == "behavior"
    assert not (set(rec.mock_targets) & {"call", "seal", "ANY", "sentinel"}), (
        f"no mock symbol should be a target, got {rec.mock_targets}"
    )

    # BITE PROOF: the round-1 rule was "func.attr in MOCK_SYMBOLS ⇒ mock
    # construction." Replay that exact rule on the fixture's calls and confirm
    # it WOULD have fired — i.e. the fix changes the answer, the test is not
    # vacuous. (We re-run the analysed AST through the OLD predicate locally.)
    import ast as _ast

    from tools.test_census import MOCK_SYMBOLS

    src = (_FIXTURES / "test_method_call_collision.py").read_text(encoding="utf-8")
    fn = next(
        n for n in _ast.walk(_ast.parse(src))
        if isinstance(n, _ast.FunctionDef)
        and n.name == "test_provider_call_is_not_mock_construction"
    )
    old_rule_targets = {
        c.func.attr
        for c in _ast.walk(fn)
        if isinstance(c, _ast.Call)
        and isinstance(c.func, _ast.Attribute)
        and c.func.attr in MOCK_SYMBOLS
    }
    assert "call" in old_rule_targets and "seal" in old_rule_targets, (
        "the round-1 attr-in-MOCK_SYMBOLS rule WOULD have flagged this — "
        "so the fix is load-bearing, not a no-op"
    )


def test_B2_mock_factory_helper_caller_is_behavioral_mock():
    # The committed fixture: a test that builds nothing itself but CALLS a
    # module-level _make_client(handler) that returns httpx.MockTransport. The
    # FIX must flag it uses_mock=True, attribute MockTransport, and put the file
    # in the behavioral-mock set. Round-1 returned early on module-level defs and
    # never attributed a helper's mock to its caller ⇒ uses_mock=False, no target.
    c = _census()
    rec = _by_name(c, "test_adapter_parses_canned_response")
    assert rec.uses_mock is True, "a call to a MockTransport factory must mock"
    assert "MockTransport" in rec.mock_targets, rec.mock_targets
    assert _tag_target("MockTransport") == "behavioral"
    assert any(
        f.split("/")[-1] == "test_helper_mock_transport.py" for f in c.behavioral_files
    ), "the helper-mediated provider-adapter file must be a behavioral-mock file"


def test_MAJOR_assert_helper_only_is_behavior_not_none():
    # The committed fixture: tests whose entire check is an assert-helper call
    # (_assert_conserved(shares) / log.assert_phase_completed(8)). The FIX must
    # classify them behavior. Round-1 saw no bare assert ⇒ none.
    c = _census()
    assert _by_name(c, "test_pool_is_conserved").predictive == "behavior"
    assert _by_name(c, "test_phase_completed").predictive == "behavior"
    # Fairness guard: the unittest.mock call-shape family stays STRUCTURE — the
    # heuristic must not swallow assert_called_once into behavior.
    assert _by_name(c, "test_only_mock_shape_helper").predictive == "structure"

    # BITE PROOF: round-1 _classify_assert only recognised bare ast.Assert +
    # pytest.raises. Confirm the fixture's two helper tests have NO bare assert
    # and NO pytest.raises — so on the old code they had zero behavior signal and
    # were necessarily none. (If a future edit added a bare assert this proof
    # would correctly fail, flagging the test as no-longer-biting.)
    import ast as _ast

    src = (_FIXTURES / "test_assert_helper.py").read_text(encoding="utf-8")
    for name in ("test_pool_is_conserved", "test_phase_completed"):
        fn = next(
            n for n in _ast.walk(_ast.parse(src))
            if isinstance(n, _ast.FunctionDef) and n.name == name
        )
        bare_asserts = [n for n in _ast.walk(fn) if isinstance(n, _ast.Assert)]
        raises = [
            n for n in _ast.walk(fn)
            if isinstance(n, _ast.Call)
            and isinstance(n.func, _ast.Attribute)
            and n.func.attr in ("raises", "warns")
        ]
        assert not bare_asserts, f"{name} must have NO bare assert (else not biting)"
        assert not raises, f"{name} must have NO pytest.raises (else not biting)"


# ---------------------------------------------------------------------------
# Rollup + totals (ModuleRecord behavior)
# ---------------------------------------------------------------------------


def test_module_rollup_ratios_are_4dp_and_correct():
    c = _census()
    mods = {m.module.split("/")[-1]: m for m in c.modules}
    pb = mods["test_pure_behavior.py"]
    assert pb.n_tests == 3
    assert pb.n_mock_tests == 0
    assert pb.mock_ratio == 0.0
    assert pb.predictive_ratio == 1.0  # all 3 are behavior

    so = mods["test_structure_only.py"]
    assert so.n_tests == 2
    assert so.n_mock_tests == 2
    assert so.mock_ratio == 1.0
    assert so.predictive_ratio == 0.0  # both structure


def test_behavioral_mock_file_count_excludes_env_only():
    # Two files mock a behavioral surface: the local-FakeProvider file
    # (FakeProvider) and the mock-factory-helper file (MockTransport, B2). The
    # monkeypatch env override (MY_FLAG) does NOT make a file behavioral.
    c = _census()
    assert c.totals["n_behavioral_mock_files"] == 2
    assert "test_monkeypatch_env.py" in {f.split("/")[-1] for f in c.behavioral_files}
    assert "test_helper_mock_transport.py" in {f.split("/")[-1] for f in c.behavioral_files}


def test_totals_count_each_shape():
    c = _census()
    t = c.totals
    assert t["n_test_functions"] == 16
    assert t["n_test_files"] == 9
    # 4 structure: the 2 in test_structure_only.py + the asserts-own-mock-return
    # + the mock-call-shape guard in test_assert_helper.py.
    assert t["n_structure_tests"] == 4
    # 2 none: only the genuine no-assert smoke tests (the assert-helper tests
    # are now behavior, not none — MAJOR).
    assert t["n_none_tests"] == 2
    assert t["n_asserts_own_mock_return"] == 1


# ---------------------------------------------------------------------------
# Determinism (rigor #3) — byte-identical output on re-run
# ---------------------------------------------------------------------------


def test_json_is_byte_identical_on_rerun():
    a = dumps(_census(), include_generated_at=False)
    b = dumps(_census(), include_generated_at=False)
    assert a == b


def test_json_omits_generated_at_without_source_date_epoch(monkeypatch):
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    payload = json.loads(dumps(_census(), include_generated_at=False))
    assert "generated_at" not in payload
    assert "tree_sha" in payload


def test_json_sorted_keys_and_stable_test_order():
    payload = json.loads(dumps(_census(), include_generated_at=False))
    files_linenos = [(t["file"], t["lineno"]) for t in payload["tests"]]
    assert files_linenos == sorted(files_linenos)


# ---------------------------------------------------------------------------
# Behavior-sensitivity proof (acceptance criterion 5b): flip an assertion from
# a value-check to a mock-call-check and confirm the flag flips behavior →
# structure. Done on a TEMP COPY so the committed fixture is never mutated.
# ---------------------------------------------------------------------------


def test_classifier_responds_to_a_real_change(tmp_path):
    # First, a genuine value-check on a NON-mock value → behavior.
    behavior_src = (
        "def compute():\n"
        "    return 41 + 1\n\n"
        "def test_thing():\n"
        "    assert compute() == 42\n"
    )
    f = tmp_path / "test_flip.py"
    f.write_text(behavior_src, encoding="utf-8")
    c1 = build_census(tmp_path, tmp_path)
    rec1 = _by_name(c1, "test_thing")
    assert rec1.predictive == "behavior"

    # Flip the SAME-named test to assert only a mock's call shape → structure.
    structure_src = (
        "from unittest.mock import MagicMock\n\n"
        "def act(client):\n"
        "    client.do()\n\n"
        "def test_thing():\n"
        "    client = MagicMock()\n"
        "    act(client)\n"
        "    client.do.assert_called_once()\n"
    )
    f.write_text(structure_src, encoding="utf-8")
    c2 = build_census(tmp_path, tmp_path)
    rec2 = _by_name(c2, "test_thing")
    assert rec2.predictive == "structure", "flag must flip behavior → structure"

    # Revert to behavior; flag flips back (proves the classifier tracks content).
    f.write_text(behavior_src, encoding="utf-8")
    c3 = build_census(tmp_path, tmp_path)
    assert _by_name(c3, "test_thing").predictive == "behavior"


# ---------------------------------------------------------------------------
# Excludes + env-var rule + report rendering
# ---------------------------------------------------------------------------


def test_env_var_name_rule():
    assert _is_env_var_name("ANTIEK_EVENT_LOG_DIR") is True
    assert _is_env_var_name("EXA_API_KEY") is True
    assert _is_env_var_name("provider.client") is False
    assert _is_env_var_name("FakeProvider") is False
    # The env-var rule overrides a behavioral token inside the var name.
    assert _tag_target("ANTIEK_EVENT_LOG_DIR") == "environmental"


def test_env_var_rule_tightened_bare_screaming_token_is_not_demoted():
    # MINOR fix: a dotless SCREAMING token with NO underscore is a plausible
    # module-level behavioral CONSTANT (a future monkeypatch.setattr(mod,
    # "CLIENT", fake)). It must NOT be demoted to environmental — round-1
    # demoted any bare SCREAMING token, silently hiding such a swap.
    assert _is_env_var_name("CLIENT") is False
    assert _is_env_var_name("PROVIDER") is False
    # "CLIENT"/"PROVIDER" carry behavioral tokens; with the demotion gone they
    # tag behavioral, so a future setattr swap stays visible.
    assert _tag_target("CLIENT") == "behavioral"
    assert _tag_target("PROVIDER") == "behavioral"
    # Multi-word env vars (the real ones in this tree) stay environmental.
    assert _is_env_var_name("ANTIEK_LLM_PROVIDER_OVERRIDE") is True
    assert _tag_target("ANTIEK_LLM_PROVIDER_OVERRIDE") == "environmental"


def test_module_context_has_no_dead_imports_unittest_mock_field():
    # Defensibility: the round-1 _ModuleContext carried an imports_unittest_mock
    # field that was computed but never read in classification, while the
    # docstring documented a non-implemented "imports unittest.mock AND
    # references Mock" rule. The field is deleted; assert it is gone so the
    # docstring/code agreement cannot silently regress.
    import dataclasses

    from tools.test_census import _ModuleContext

    field_names = {f.name for f in dataclasses.fields(_ModuleContext)}
    assert "imports_unittest_mock" not in field_names
    assert "mock_helpers" in field_names  # the B2 replacement IS present


def test_caffenagent_paths_are_excluded(tmp_path):
    nested = tmp_path / ".caffenagent" / "wt" / "tests"
    nested.mkdir(parents=True)
    (nested / "test_scratch.py").write_text(
        "def test_x():\n    assert 1 == 1\n", encoding="utf-8"
    )
    real = tmp_path / "tests"
    real.mkdir()
    (real / "test_real.py").write_text(
        "def test_y():\n    assert 2 == 2\n", encoding="utf-8"
    )
    c = build_census(tmp_path, tmp_path)
    names = {t.name for t in c.tests}
    assert "test_y" in names
    assert "test_x" not in names, ".caffenagent paths must be excluded"


def test_report_contains_totals_and_known_limit():
    report = render_report(_census())
    assert "total test functions" in report
    assert "behavioral-mock files" in report
    assert "KNOWN LIMIT" in report  # fairness section is part of the contract


def test_cli_exit_zero_and_writes_json(tmp_path):
    out = tmp_path / "census.json"
    proc = subprocess.run(
        [sys.executable, "-m", "tools.test_census",
         "--tests-dir", str(_FIXTURES), "--json", str(out)],
        cwd=str(_REPO), capture_output=True, text=True, check=False,
        env={**os.environ},
    )
    assert proc.returncode == 0, proc.stderr  # the census never gates
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["totals"]["n_test_functions"] == 16


def test_unparseable_file_is_reported_not_crashed(tmp_path):
    (tmp_path / "test_broken.py").write_text("def test_x(:\n  pass\n", encoding="utf-8")
    (tmp_path / "test_ok.py").write_text("def test_y():\n  assert 1 == 1\n", encoding="utf-8")
    c = build_census(tmp_path, tmp_path)
    assert c.totals["n_unparseable_files"] == 1
    assert any("test_broken.py" in m for m, _ in c.unparseable)
    # the good file still parsed — one bad file never kills the census.
    assert any(t.name == "test_y" for t in c.tests)
