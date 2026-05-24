"""Tests for tools.lints.baseline — the baseline-mode helper."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.lints.baseline import (
    SCHEMA_VERSION,
    BaselineSchema,
    ViolationKey,
    compute_keys,
    filter_to_new_only,
    find_stale_baseline_entries,
    load_baseline,
    write_baseline,
)


def test_violation_key_equality_on_all_fields() -> None:
    a = ViolationKey(path="x.py", line=1, col=0, kind="raise:Foo")
    b = ViolationKey(path="x.py", line=1, col=0, kind="raise:Foo")
    assert a == b


def test_violation_key_different_if_any_field_differs() -> None:
    base = ViolationKey(path="x.py", line=1, col=0, kind="raise:Foo")
    assert base != ViolationKey(path="y.py", line=1, col=0, kind="raise:Foo")
    assert base != ViolationKey(path="x.py", line=2, col=0, kind="raise:Foo")
    assert base != ViolationKey(path="x.py", line=1, col=5, kind="raise:Foo")
    assert base != ViolationKey(path="x.py", line=1, col=0, kind="raise:Bar")


def test_violation_key_sort_is_path_major() -> None:
    keys = [
        ViolationKey(path="z.py", line=1, col=0, kind="a"),
        ViolationKey(path="a.py", line=99, col=0, kind="b"),
        ViolationKey(path="a.py", line=5, col=10, kind="c"),
        ViolationKey(path="a.py", line=5, col=0, kind="d"),
    ]
    s = sorted(keys)
    assert s[0].path == "a.py" and s[0].line == 5 and s[0].col == 0
    assert s[1].path == "a.py" and s[1].line == 5 and s[1].col == 10
    assert s[2].path == "a.py" and s[2].line == 99
    assert s[3].path == "z.py"


def test_violation_key_is_hashable() -> None:
    k = ViolationKey(path="x.py", line=1, col=0, kind="raise:Foo")
    assert k in {k}


def test_baseline_schema_round_trip() -> None:
    schema = BaselineSchema(
        schema_version=SCHEMA_VERSION,
        lint="no_raise",
        generated_at="2026-05-24T12:00:00+00:00",
        violations=[
            ViolationKey(path="x.py", line=10, col=4, kind="raise:Foo"),
            ViolationKey(path="a.py", line=1, col=0, kind="raise:Bar"),
        ],
    )
    restored = BaselineSchema.from_json(schema.to_json())
    assert restored.violations == sorted(schema.violations)
    assert restored.lint == schema.lint


def test_baseline_schema_rejects_wrong_version() -> None:
    with pytest.raises(ValueError, match="schema_version"):
        BaselineSchema.from_json({"schema_version": 99, "violations": []})


def test_baseline_schema_handles_missing_optional_fields() -> None:
    minimal = {"schema_version": SCHEMA_VERSION}
    schema = BaselineSchema.from_json(minimal)
    assert schema.violations == []
    assert schema.lint == "<unknown>"


def test_write_baseline_sorts_violations(tmp_path: Path) -> None:
    unsorted = [
        ViolationKey(path="z.py", line=10, col=0, kind="raise:Z"),
        ViolationKey(path="a.py", line=1, col=0, kind="raise:A"),
    ]
    out = tmp_path / "b.json"
    write_baseline(out, lint="t", violations=unsorted)
    data = json.loads(out.read_text())
    assert data["violations"][0]["path"] == "a.py"
    assert data["violations"][1]["path"] == "z.py"


def test_write_baseline_violations_array_deterministic(tmp_path: Path) -> None:
    violations = [
        ViolationKey(path="a.py", line=1, col=0, kind="raise:A"),
        ViolationKey(path="b.py", line=2, col=4, kind="raise:B"),
    ]
    out1 = tmp_path / "b1.json"
    out2 = tmp_path / "b2.json"
    write_baseline(out1, lint="t", violations=violations)
    write_baseline(out2, lint="t", violations=violations)
    d1 = json.loads(out1.read_text())
    d2 = json.loads(out2.read_text())
    assert d1["violations"] == d2["violations"]


def test_load_baseline_round_trip(tmp_path: Path) -> None:
    violations = [ViolationKey(path="a.py", line=1, col=0, kind="raise:A")]
    out = tmp_path / "b.json"
    write_baseline(out, lint="t", violations=violations)
    assert load_baseline(out).violations == violations


def test_load_baseline_missing_raises_fnfe() -> None:
    with pytest.raises(FileNotFoundError):
        load_baseline(Path("/nonexistent/baseline.json"))


def test_compute_keys_applies_adapter_and_sorts() -> None:
    class FakeViolation:
        def __init__(self, p: str, ln: int, col: int, k: str) -> None:
            self.p, self.ln, self.col, self.k = p, ln, col, k

    def adapter(v: object) -> ViolationKey:
        assert isinstance(v, FakeViolation)
        return ViolationKey(path=v.p, line=v.ln, col=v.col, kind=v.k)

    keys = compute_keys(
        [FakeViolation("z.py", 5, 0, "a"), FakeViolation("a.py", 1, 0, "b")],
        adapter,
    )
    assert keys[0].path == "a.py"
    assert keys[1].path == "z.py"


def test_filter_to_new_only_returns_only_new() -> None:
    grand = ViolationKey(path="legacy.py", line=1, col=0, kind="raise:Old")
    new = ViolationKey(path="new.py", line=1, col=0, kind="raise:New")
    baseline = BaselineSchema(
        schema_version=SCHEMA_VERSION, lint="t", generated_at="",
        violations=[grand],
    )
    assert filter_to_new_only([grand, new], baseline) == [new]


def test_filter_to_new_only_empty_baseline_returns_all() -> None:
    a = ViolationKey(path="a.py", line=1, col=0, kind="raise:A")
    b = ViolationKey(path="b.py", line=1, col=0, kind="raise:B")
    baseline = BaselineSchema(
        schema_version=SCHEMA_VERSION, lint="t", generated_at="", violations=[],
    )
    assert filter_to_new_only([a, b], baseline) == [a, b]


def test_filter_to_new_only_all_grandfathered_returns_empty() -> None:
    a = ViolationKey(path="a.py", line=1, col=0, kind="raise:A")
    baseline = BaselineSchema(
        schema_version=SCHEMA_VERSION, lint="t", generated_at="", violations=[a],
    )
    assert filter_to_new_only([a], baseline) == []


def test_find_stale_entries_returns_fixed_ones() -> None:
    fixed = ViolationKey(path="fixed.py", line=1, col=0, kind="raise:Old")
    still = ViolationKey(path="still.py", line=1, col=0, kind="raise:Old")
    baseline = BaselineSchema(
        schema_version=SCHEMA_VERSION, lint="t", generated_at="",
        violations=[fixed, still],
    )
    assert find_stale_baseline_entries(current=[still], baseline=baseline) == [fixed]


def test_find_stale_entries_empty_when_nothing_fixed() -> None:
    a = ViolationKey(path="a.py", line=1, col=0, kind="raise:A")
    baseline = BaselineSchema(
        schema_version=SCHEMA_VERSION, lint="t", generated_at="", violations=[a],
    )
    assert find_stale_baseline_entries(current=[a], baseline=baseline) == []
