"""Unit tests for tools/complexity_report.py (AOD SPR-01).

Synthetic fixture modules exercise each AST decision and the load-bearing
ordering property: a deep module (small interface, big body) must rank BELOW a
shallow module (fat interface, thin body). Pure ast — no substrate import, no
git, no filesystem for the analysis tests.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from tools.complexity_report import (
    analyze_source,
    build_report,
    implementation_depth,
    render_markdown,
)


def _analyze(src: str, name: str = "mod.py") -> dict:
    return analyze_source(Path(name), src)


def _ratio(src: str, name: str = "mod.py") -> float:
    a = _analyze(src, name)
    return float(a["interface_surface"]) / int(a["depth"])


# --------------------------------------------------------------------------- #
# The load-bearing ordering: deep < shallow (spec milestone-6 acceptance)      #
# --------------------------------------------------------------------------- #

DEEP_SRC = '''\
"""A deep module: one public entry over a big implementation."""
def solve(problem: str) -> int:
    total = 0
    for ch in problem:
        if ch.isdigit():
            total += int(ch)
        elif ch.isalpha():
            total -= 1
        else:
            total += 2
    while total > 100:
        total //= 2
    try:
        total = total or 1
    except Exception:
        total = 0
    return total
'''

SHALLOW_SRC = '''\
"""A shallow module: fat interface, thin bodies."""
def a(x, y): return x
def b(x, y): return y
def c(x, y): return x + y
def d(x, y): return x - y
def e(x, y): return x * y
'''

REEXPORT_SRC = '''\
"""Pure re-export shell."""
from othermod import a, b, c
__all__ = ["a", "b", "c"]
'''


def test_deep_ranks_below_shallow() -> None:
    """The whole point: Ousterhout ratio orders deep < shallow."""
    assert _ratio(DEEP_SRC) < _ratio(SHALLOW_SRC)


def test_deep_is_genuinely_low_ratio() -> None:
    a = _analyze(DEEP_SRC)
    assert a["interface_surface"] < a["depth"]  # more implementation than interface
    assert _ratio(DEEP_SRC) < 0.5


def test_reexport_detected_and_has_no_defs() -> None:
    a = _analyze(REEXPORT_SRC)
    assert a["kind"] == "reexport"
    # __all__ names that are not def/class count as bare exported symbols
    assert a["top_symbols"] == 3
    assert a["method_symbols"] == 0


def test_package_init_kind() -> None:
    assert _analyze(SHALLOW_SRC, name="__init__.py")["kind"] == "package_init"
    assert _analyze(SHALLOW_SRC, name="mod.py")["kind"] == "normal"


# --------------------------------------------------------------------------- #
# Class-cohesion discount                                                      #
# --------------------------------------------------------------------------- #

FIVE_FUNCS = "def a(): pass\ndef b(): pass\ndef c(): pass\ndef d(): pass\ndef e(): pass\n"
ONE_CLASS_FIVE_METHODS = (
    "class K:\n"
    "    def a(self): pass\n"
    "    def b(self): pass\n"
    "    def c(self): pass\n"
    "    def d(self): pass\n"
    "    def e(self): pass\n"
)


def test_class_cohesion_discount() -> None:
    """Five methods on one class cost LESS interface than five top-level funcs:
    a class is one cohesive abstraction (methods weighted 0.5)."""
    funcs = _analyze(FIVE_FUNCS)["interface_surface"]
    klass = _analyze(ONE_CLASS_FIVE_METHODS)["interface_surface"]
    assert klass < funcs
    # 5 top-level funcs = 5.0 ; 1 class + 5*0.5 methods = 1 + 2.5 = 3.5
    assert funcs == pytest.approx(5.0)
    assert klass == pytest.approx(3.5)


# --------------------------------------------------------------------------- #
# Per-decision AST edge cases                                                  #
# --------------------------------------------------------------------------- #

def test_property_one_symbol_zero_params() -> None:
    src = (
        "class K:\n"
        "    @property\n"
        "    def value(self): return self._v\n"
    )
    a = _analyze(src)
    # class(1) + 1 method symbol*0.5, zero params → 1 + 0.5 = 1.5
    assert a["method_symbols"] == 1
    assert a["param_count"] == 0
    assert a["interface_surface"] == pytest.approx(1.5)


def test_property_setter_not_double_counted() -> None:
    src = (
        "class K:\n"
        "    @property\n"
        "    def v(self): return self._v\n"
        "    @v.setter\n"
        "    def v(self, val): self._v = val\n"
    )
    # property + its setter = ONE interface concept, one symbol, zero params
    assert _analyze(src)["method_symbols"] == 1
    assert _analyze(src)["param_count"] == 0


def test_overload_counted_once() -> None:
    src = (
        "from typing import overload\n"
        "@overload\n"
        "def f(x: int) -> int: ...\n"
        "@overload\n"
        "def f(x: str) -> str: ...\n"
        "def f(x): return x\n"
    )
    # one public name `f`, counted once
    assert _analyze(src)["top_symbols"] == 1


def test_init_params_count_but_init_is_not_a_symbol() -> None:
    src = (
        "class K:\n"
        "    def __init__(self, a, b, c): pass\n"
        "    def method(self, x): pass\n"
    )
    a = _analyze(src)
    assert a["top_symbols"] == 1          # the class
    assert a["method_symbols"] == 1       # `method` (not __init__)
    assert a["param_count"] == 4          # a,b,c (init) + x (method); self excluded


def test_other_dunders_excluded() -> None:
    src = (
        "class K:\n"
        "    def __eq__(self, other): return True\n"
        "    def __enter__(self): return self\n"
        "    def real(self): pass\n"
    )
    assert _analyze(src)["method_symbols"] == 1  # only `real`


def test_varargs_kwargs_each_count_one() -> None:
    src = "def f(a, *args, **kwargs): pass\n"
    assert _analyze(src)["param_count"] == 3  # a + *args + **kwargs


def test_all_is_authoritative() -> None:
    src = (
        "__all__ = ['pub']\n"
        "def pub(): pass\n"
        "def looks_public(): pass\n"  # excluded: not in __all__
    )
    assert _analyze(src)["top_symbols"] == 1


def test_augmented_all_is_unioned() -> None:
    src = (
        "__all__ = ['a']\n"
        "__all__ += ['b']\n"
        "def a(): pass\n"
        "def b(): pass\n"
        "def c(): pass\n"
    )
    assert _analyze(src)["top_symbols"] == 2  # a and b, not c


def test_private_excluded_without_all() -> None:
    src = "def pub(): pass\ndef _priv(): pass\n"
    assert _analyze(src)["top_symbols"] == 1


def test_enum_members_not_counted_as_symbols() -> None:
    src = (
        "import enum\n"
        "class Color(enum.Enum):\n"
        "    RED = 1\n"
        "    GREEN = 2\n"
        "    BLUE = 3\n"
    )
    # the class is 1 symbol; members are class-level assignments, not methods
    assert _analyze(src)["top_symbols"] == 1
    assert _analyze(src)["method_symbols"] == 0


# --------------------------------------------------------------------------- #
# Depth                                                                        #
# --------------------------------------------------------------------------- #

def test_docstring_excluded_from_depth() -> None:
    with_doc = _analyze('"""just a docstring."""\n')
    assert with_doc["statements"] == 0

def test_branch_points_counted() -> None:
    src = (
        "def f(x):\n"
        "    if x and x > 0:\n"       # If + BoolOp(1)
        "        return 1\n"
        "    for i in range(x):\n"    # For
        "        pass\n"
        "    return [i for i in range(x) if i]\n"  # comprehension if
    )
    _, branches = implementation_depth(ast.parse(src))
    assert branches >= 4  # If, BoolOp, For, comprehension-if


def test_empty_module_depth_floored_to_one() -> None:
    a = _analyze("\n")
    assert a["depth"] == 1  # divide-by-zero defined out of existence


# --------------------------------------------------------------------------- #
# Resilience                                                                   #
# --------------------------------------------------------------------------- #

def test_syntax_error_does_not_crash() -> None:
    a = _analyze("def broken(:\n")
    assert a["kind"] == "parse_error"
    assert a["parse_error"] is not None
    assert a["depth"] == 1  # safe denominator


# --------------------------------------------------------------------------- #
# Integration: build_report over a tiny synthetic tree                         #
# --------------------------------------------------------------------------- #

def test_build_report_shape_and_ordering(tmp_path: Path) -> None:
    root = tmp_path
    sub = root / "substrate"
    sub.mkdir()
    (sub / "deep.py").write_text(DEEP_SRC, encoding="utf-8")
    (sub / "shallow.py").write_text(SHALLOW_SRC, encoding="utf-8")
    (sub / "__init__.py").write_text("", encoding="utf-8")
    report = build_report(
        root_repo=root,
        substrate_root="substrate",
        window=500,
        fence_source="specs",  # absent → no globbed citations, master prefixes only
        top=10,
    )
    assert report["schema_version"] == 1
    assert report["module_count"] == 3
    mods = {m["module"]: m for m in report["modules"]}
    assert mods["substrate/deep.py"]["ratio"] < mods["substrate/shallow.py"]["ratio"]
    # no git in tmp → churn 0 → rank_score 0 for all; report still valid
    assert all(m["churn"] == 0 for m in report["modules"])
    # markdown renders without error and mentions the head
    md = render_markdown(report, top=10)
    assert "Ousterhout deep/shallow lens" in md
    assert "Full positional index" in md


def test_report_is_json_serializable(tmp_path: Path) -> None:
    sub = tmp_path / "substrate"
    sub.mkdir()
    (sub / "m.py").write_text(SHALLOW_SRC, encoding="utf-8")
    report = build_report(
        root_repo=tmp_path, substrate_root="substrate",
        window=500, fence_source="specs", top=5,
    )
    # must round-trip (house convention: deterministic, sort_keys-friendly)
    json.dumps(report, sort_keys=True)
