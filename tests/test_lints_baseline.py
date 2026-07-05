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


# ----- content-keyed matching (line-shift defect fix) -------------------

def test_filter_content_fallback_recognizes_shifted_offense() -> None:
    """A baselined offense that shifted line (mid-file insertion above it)
    is the SAME grandfathered debt — not NEW — when its source snippet
    matches a baseline entry of the same (path, kind)."""
    base = ViolationKey(path="a.py", line=10, col=0, kind="mypy:arg-type", snippet="x = bad()")
    shifted = ViolationKey(path="a.py", line=20, col=0, kind="mypy:arg-type", snippet="x = bad()")
    baseline = BaselineSchema(
        schema_version=SCHEMA_VERSION, lint="t", generated_at="", violations=[base]
    )
    assert filter_to_new_only([shifted], baseline) == []


def test_filter_does_not_mask_genuine_new_violation() -> None:
    """A genuinely new offense on a different source line is still NEW even
    when snippet matching is active (the no-mask safety property)."""
    base = ViolationKey(path="a.py", line=10, col=0, kind="mypy:arg-type", snippet="x = bad()")
    genuine = ViolationKey(path="a.py", line=20, col=0, kind="mypy:arg-type", snippet="y = worse()")
    baseline = BaselineSchema(
        schema_version=SCHEMA_VERSION, lint="t", generated_at="", violations=[base]
    )
    assert filter_to_new_only([genuine], baseline) == [genuine]


def test_filter_content_fallback_requires_kind_match() -> None:
    """Identical source text but a DIFFERENT violation kind is NOT the same
    offense → still NEW. The kind constraint bounds the content-keying
    collision risk."""
    base = ViolationKey(path="a.py", line=10, col=0, kind="mypy:arg-type", snippet="x = bad()")
    other = ViolationKey(path="a.py", line=20, col=0, kind="mypy:no-untyped-def", snippet="x = bad()")
    baseline = BaselineSchema(
        schema_version=SCHEMA_VERSION, lint="t", generated_at="", violations=[base]
    )
    assert filter_to_new_only([other], baseline) == [other]


def test_filter_no_snippet_is_exact_line_only_v1_compat() -> None:
    """Substrate-lint / v1 baselines carry no snippet → matching is exact-line
    only, byte-identical to the pre-content-keying behavior (a shifted offense
    with no snippet is still reported NEW)."""
    base = ViolationKey(path="a.py", line=10, col=0, kind="mypy:arg-type")
    shifted = ViolationKey(path="a.py", line=20, col=0, kind="mypy:arg-type")
    baseline = BaselineSchema(
        schema_version=SCHEMA_VERSION, lint="t", generated_at="", violations=[base]
    )
    assert filter_to_new_only([shifted], baseline) == [shifted]


def test_find_stale_shifted_offense_is_not_stale() -> None:
    """A shifted offense still reproduces (lower in the file) → not stale, so
    the burn-down loop won't drop still-live debt."""
    base = ViolationKey(path="a.py", line=10, col=0, kind="mypy:arg-type", snippet="x = bad()")
    shifted = ViolationKey(path="a.py", line=20, col=0, kind="mypy:arg-type", snippet="x = bad()")
    baseline = BaselineSchema(
        schema_version=SCHEMA_VERSION, lint="t", generated_at="", violations=[base]
    )
    assert find_stale_baseline_entries(current=[shifted], baseline=baseline) == []


def test_snippet_round_trips_through_json(tmp_path: Path) -> None:
    v = ViolationKey(path="a.py", line=3, col=0, kind="mypy:arg-type", snippet="x = bad()")
    out = tmp_path / "b.json"
    write_baseline(out, lint="t", violations=[v])
    data = json.loads(out.read_text())
    assert data["violations"][0]["snippet"] == "x = bad()"
    assert load_baseline(out).violations == [v]


def test_snippetless_entries_serialize_without_snippet_field(tmp_path: Path) -> None:
    """Snippet-free entries (substrate baselines) stay byte-identical: no
    empty 'snippet' key is written."""
    v = ViolationKey(path="a.py", line=3, col=0, kind="raise:Foo")
    out = tmp_path / "b.json"
    write_baseline(out, lint="t", violations=[v])
    assert "snippet" not in json.loads(out.read_text())["violations"][0]

# ----- one-to-one matching: grok (Composer 2.5) adversarial finding (cycle 26) -----

def test_filter_one_to_one_new_duplicate_beyond_count_is_new() -> None:
    """A NEW duplicate of a baselined boilerplate line (e.g. a second
    ``r.raise_for_status()`` in new code) is NOT masked once the single
    grandfathered slot is consumed. This is the case a set-based snippet
    fallback would mask and that one-to-one matching closes."""
    base = ViolationKey(path="a.py", line=40, col=0, kind="mypy:no-untyped-def",
                        snippet="def _send() -> httpx.Response:")
    shifted = ViolationKey(path="a.py", line=45, col=0, kind="mypy:no-untyped-def",
                           snippet="def _send() -> httpx.Response:")
    duplicate = ViolationKey(path="a.py", line=200, col=0, kind="mypy:no-untyped-def",
                             snippet="def _send() -> httpx.Response:")
    baseline = BaselineSchema(
        schema_version=SCHEMA_VERSION, lint="t", generated_at="", violations=[base]
    )
    # The shifted occurrence consumes the one slot; the duplicate is NEW.
    result = filter_to_new_only([shifted, duplicate], baseline)
    assert result == [duplicate]


def test_filter_grandfathered_duplicates_cover_up_to_count() -> None:
    """If the baseline grandfathers N copies of a snippet, up to N current
    occurrences are covered (honest debt), the (N+1)th is NEW."""
    b1 = ViolationKey(path="a.py", line=40, col=0, kind="mypy:arg-type", snippet="x = bad()")
    b2 = ViolationKey(path="a.py", line=60, col=0, kind="mypy:arg-type", snippet="x = bad()")
    c1 = ViolationKey(path="a.py", line=140, col=0, kind="mypy:arg-type", snippet="x = bad()")
    c2 = ViolationKey(path="a.py", line=160, col=0, kind="mypy:arg-type", snippet="x = bad()")
    c3 = ViolationKey(path="a.py", line=180, col=0, kind="mypy:arg-type", snippet="x = bad()")
    baseline = BaselineSchema(
        schema_version=SCHEMA_VERSION, lint="t", generated_at="", violations=[b1, b2]
    )
    assert filter_to_new_only([c1, c2, c3], baseline) == [c3]


def test_find_stale_one_to_one_mirror() -> None:
    """A baseline slot whose twin is still-live (consumed) is NOT stale."""
    base = ViolationKey(path="a.py", line=40, col=0, kind="mypy:arg-type", snippet="x = bad()")
    live_shifted = ViolationKey(path="a.py", line=140, col=0, kind="mypy:arg-type", snippet="x = bad()")
    baseline = BaselineSchema(
        schema_version=SCHEMA_VERSION, lint="t", generated_at="", violations=[base]
    )
    assert find_stale_baseline_entries(current=[live_shifted], baseline=baseline) == []

