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
    enrich_keys_with_snippets,
    filter_to_new_only,
    find_stale_baseline_entries,
    load_baseline,
    normalize_snippet,
    source_line_snippet,
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


def test_filter_exact_match_consumes_slot_so_new_duplicate_is_new() -> None:
    """The grandfathered offense STAYS at its exact baseline line AND a NEW
    verbatim duplicate appears elsewhere. The exact match must release the
    snippet slot, else the duplicate hides behind a slot the exact match
    never consumed. This is the exact-match variant of the verbatim-
    duplicate masking vector (the line-shift variant is covered above)."""
    snippet = "def _send() -> httpx.Response:"
    base = ViolationKey(
        path="a.py", line=40, col=0, kind="mypy:no-untyped-def", snippet=snippet
    )
    original = ViolationKey(
        path="a.py", line=40, col=0, kind="mypy:no-untyped-def", snippet=snippet
    )
    duplicate = ViolationKey(
        path="a.py", line=200, col=0, kind="mypy:no-untyped-def", snippet=snippet
    )
    baseline = BaselineSchema(
        schema_version=SCHEMA_VERSION, lint="t", generated_at="", violations=[base]
    )
    assert filter_to_new_only([original, duplicate], baseline) == [duplicate]


def test_find_stale_exact_match_consumes_slot_so_extra_entry_is_stale() -> None:
    """Mirror: the baseline grandfathers two copies of a snippet but only one
    is still live at its exact line; the second was removed. The exact match
    must consume the live finding's slot, else the removed entry hides behind
    it and is wrongly reported not-stale (blocking honest burn-down)."""
    snippet = "x = bad()"
    b1 = ViolationKey(
        path="a.py", line=40, col=0, kind="mypy:arg-type", snippet=snippet
    )
    b2 = ViolationKey(
        path="a.py", line=60, col=0, kind="mypy:arg-type", snippet=snippet
    )
    live = ViolationKey(
        path="a.py", line=40, col=0, kind="mypy:arg-type", snippet=snippet
    )
    baseline = BaselineSchema(
        schema_version=SCHEMA_VERSION, lint="t", generated_at="", violations=[b1, b2]
    )
    assert find_stale_baseline_entries(current=[live], baseline=baseline) == [b2]


# ----- whitespace-collapsed normalization (issue #3236) ----------------------

def test_normalize_snippet_strips_and_collapses_whitespace() -> None:
    assert normalize_snippet("  x  =   bad()\t") == "x = bad()"
    assert normalize_snippet("") == ""
    assert normalize_snippet("   ") == ""


def test_filter_matches_legacy_strip_only_snippet_via_match_time_normalization() -> None:
    """Baselines written before whitespace-collapsing store strip-only
    snippets. Match-time normalization on BOTH sides keeps them matching:
    a stored snippet with an internal whitespace run equals a collapsed
    current capture of the same line."""
    base = ViolationKey(path="a.py", line=10, col=0, kind="mypy:arg-type",
                        snippet="x  =   bad()")  # legacy strip-only storage
    shifted = ViolationKey(path="a.py", line=20, col=0, kind="mypy:arg-type",
                           snippet="x = bad()")  # collapsed at capture
    baseline = BaselineSchema(
        schema_version=SCHEMA_VERSION, lint="t", generated_at="", violations=[base]
    )
    assert filter_to_new_only([shifted], baseline) == []
    assert find_stale_baseline_entries(current=[shifted], baseline=baseline) == []


# ----- exact-first two-pass: the multiset rule is order-independent ---------

def test_filter_new_duplicate_above_original_is_new() -> None:
    """The multiset rule, order-independently: baseline grandfathers ONE copy
    of snippet S at line 40; current has the SAME original at line 40 plus a
    NEW verbatim duplicate ABOVE it at line 30 (sorts first). The duplicate
    must be NEW — if content matching consumed the slot before the exact
    match released it, the original would hide behind its own slot and the
    duplicate would be masked."""
    snippet = "def _send() -> httpx.Response:"
    base = ViolationKey(path="a.py", line=40, col=0, kind="mypy:no-untyped-def",
                        snippet=snippet)
    duplicate_above = ViolationKey(path="a.py", line=30, col=0,
                                   kind="mypy:no-untyped-def", snippet=snippet)
    original = ViolationKey(path="a.py", line=40, col=0,
                            kind="mypy:no-untyped-def", snippet=snippet)
    baseline = BaselineSchema(
        schema_version=SCHEMA_VERSION, lint="t", generated_at="", violations=[base]
    )
    assert filter_to_new_only([duplicate_above, original], baseline) == [
        duplicate_above
    ]


def test_find_stale_exact_first_pass_removed_entry_is_stale() -> None:
    """Mirror of the above for staleness: baseline grandfathers TWO copies of
    snippet S (lines 40 and 60); only the line-60 copy is still live. The
    line-40 entry must be reported stale — if the shifted-twin content match
    consumed the live slot before the exact match released it, the removed
    entry would hide and burn-down would be blocked."""
    snippet = "x = bad()"
    removed = ViolationKey(path="a.py", line=40, col=0, kind="mypy:arg-type",
                           snippet=snippet)
    still_live_base = ViolationKey(path="a.py", line=60, col=0,
                                   kind="mypy:arg-type", snippet=snippet)
    live = ViolationKey(path="a.py", line=60, col=0, kind="mypy:arg-type",
                        snippet=snippet)
    baseline = BaselineSchema(
        schema_version=SCHEMA_VERSION, lint="t", generated_at="",
        violations=[removed, still_live_base],
    )
    assert find_stale_baseline_entries(current=[live], baseline=baseline) == [
        removed
    ]


def test_find_stale_multiset_two_identical_one_removed_shifted() -> None:
    """Multiplicity rule with a shift: two identical-text baseline entries,
    one occurrence removed and the survivor SHIFTED to a new line — exactly
    one entry is stale (the survivor content-matches one slot)."""
    snippet = "x = bad()"
    b1 = ViolationKey(path="a.py", line=40, col=0, kind="mypy:arg-type",
                      snippet=snippet)
    b2 = ViolationKey(path="a.py", line=60, col=0, kind="mypy:arg-type",
                      snippet=snippet)
    survivor_shifted = ViolationKey(path="a.py", line=160, col=0,
                                    kind="mypy:arg-type", snippet=snippet)
    baseline = BaselineSchema(
        schema_version=SCHEMA_VERSION, lint="t", generated_at="",
        violations=[b1, b2],
    )
    stale = find_stale_baseline_entries(current=[survivor_shifted], baseline=baseline)
    assert len(stale) == 1
    assert stale[0] in (b1, b2)


# ----- snippet capture helpers ----------------------------------------------

def test_source_line_snippet_reads_and_normalizes(tmp_path: Path) -> None:
    src = tmp_path / "a.py"
    src.write_text("import os\n\n    y   =   bad_call()\n", encoding="utf-8")
    assert source_line_snippet(src, 3) == "y = bad_call()"
    assert source_line_snippet(src, 1) == "import os"
    assert source_line_snippet(src, 2) == ""  # blank line normalizes to empty
    assert source_line_snippet(src, 99) == ""  # out of range
    assert source_line_snippet(tmp_path / "missing.py", 1) == ""  # unreadable


def test_enrich_keys_with_snippets_stamps_source_text(tmp_path: Path) -> None:
    src = tmp_path / "pkg" / "a.py"
    src.parent.mkdir(parents=True)
    src.write_text("import os\nx = 1\n", encoding="utf-8")
    keys = [
        ViolationKey(path="pkg/a.py", line=2, col=0, kind="mypy:arg-type"),
        ViolationKey(path="pkg/missing.py", line=2, col=0, kind="mypy:arg-type"),
    ]
    enriched = enrich_keys_with_snippets(keys, tmp_path)
    assert enriched[0].snippet == "x = 1"
    assert enriched[1].snippet == ""
    # Identity fields untouched.
    assert [(k.path, k.line, k.col, k.kind) for k in enriched] == [
        (k.path, k.line, k.col, k.kind) for k in keys
    ]


def test_enrich_keys_with_snippets_accepts_absolute_paths(tmp_path: Path) -> None:
    src = tmp_path / "abs.py"
    src.write_text("raise CustomDomainError('x')\n", encoding="utf-8")
    keys = [ViolationKey(path=str(src), line=1, col=4, kind="raise:CustomDomainError")]
    enriched = enrich_keys_with_snippets(keys, tmp_path)
    assert enriched[0].snippet == "raise CustomDomainError('x')"


# ── A baselined COORDINATE is not a blank cheque ────────────────────────────
#
# Pass 1 matched on (path, line, col, kind) alone. As code moves, a wholly
# different violation of the same kind lands on a baselined coordinate and was
# absorbed silently. On a REQUIRED merge gate that turns every occupied
# coordinate into a free pass — 2,267 of them across the mypy and ruff
# baselines at the time this was found.


def test_a_different_violation_at_a_baselined_coordinate_is_reported_new():
    baseline = BaselineSchema(
        schema_version=1,
        lint="declared_bar",
        generated_at="2026-09-20T00:00:00Z",
        violations=[
            ViolationKey(
                path="tests/t.py", line=29, col=1, kind="ruff:E402",
                snippet="import os",
            )
        ],
    )
    intruder = ViolationKey(
        path="tests/t.py", line=29, col=1, kind="ruff:E402",
        snippet="from zzz.malicious import backdoor",
    )

    new = filter_to_new_only([intruder], baseline)

    assert len(new) == 1, (
        "a different violation at a baselined coordinate was absorbed; every "
        "baselined coordinate is then a free pass on a required gate"
    )
    assert new[0].snippet == "from zzz.malicious import backdoor"


def test_the_same_violation_at_its_baselined_coordinate_is_still_absorbed():
    """The grandfathering this gate exists for must keep working."""
    baseline = BaselineSchema(
        schema_version=1, lint="declared_bar", generated_at="x",
        violations=[
            ViolationKey(
                path="tests/t.py", line=29, col=1, kind="ruff:E402",
                snippet="import os",
            )
        ],
    )
    same = ViolationKey(
        path="tests/t.py", line=29, col=1, kind="ruff:E402", snippet="import os"
    )
    assert filter_to_new_only([same], baseline) == []


def test_a_shifted_baselined_violation_is_still_absorbed():
    """Drift robustness — the whole reason the snippet exists — is preserved."""
    baseline = BaselineSchema(
        schema_version=1, lint="declared_bar", generated_at="x",
        violations=[
            ViolationKey(
                path="tests/t.py", line=29, col=1, kind="ruff:E402",
                snippet="import os",
            )
        ],
    )
    shifted = ViolationKey(
        path="tests/t.py", line=44, col=1, kind="ruff:E402", snippet="import os"
    )
    assert filter_to_new_only([shifted], baseline) == []


def test_a_snippetless_legacy_baseline_still_matches_on_coordinate_alone():
    """v1 and substrate-lint baselines carry no snippet; they must not regress.

    Without this, tightening pass 1 would report every grandfathered v1 entry
    as NEW the moment a lint started emitting snippets — turning a safety fix
    into a mass false-positive event on a required gate.
    """
    baseline = BaselineSchema(
        schema_version=1, lint="substrate", generated_at="x",
        violations=[
            ViolationKey(path="tests/t.py", line=29, col=1, kind="raise:ValueError")
        ],
    )
    current_no_snippet = ViolationKey(
        path="tests/t.py", line=29, col=1, kind="raise:ValueError"
    )
    current_with_snippet = ViolationKey(
        path="tests/t.py", line=29, col=1, kind="raise:ValueError",
        snippet="raise ValueError('x')",
    )
    assert filter_to_new_only([current_no_snippet], baseline) == []
    assert filter_to_new_only([current_with_snippet], baseline) == [], (
        "a snippet-bearing current finding must still match a snippetless "
        "baseline entry at the same coordinate, or every legacy baseline "
        "erupts the day its lint learns to capture snippets"
    )
