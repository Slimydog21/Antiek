"""Unit tests for tools/lint/info_hiding.py (AOD SPR-02).

The near-miss fixtures are the precision contract (rigor #3): each is a pattern
that LOOKS like a leak but is not, and the lint must stay quiet on it. Names
contain `near_miss` / `self_internal` so the spec's verification gates
(`pytest -k near_miss`, `-k self_internal`) select them.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from tools.lint.info_hiding import (
    ModuleInfo,
    build_module_index,
    build_report,
    find_l1_leaks,
    find_l2_leaks,
    find_l3_candidates,
)


def _mod(dotted: str, path: str, *, has_all: bool = False, all_names=(), public=()) -> ModuleInfo:
    return ModuleInfo(
        dotted=dotted, path=path, has_all=has_all,
        all_names=frozenset(all_names), public_names=frozenset(public), is_package=False,
    )


INDEX = {
    "substrate.dedup": _mod(
        "substrate.dedup", "substrate/dedup.py",
        has_all=True, all_names={"identity_key", "normalize_doi"},
        public={"identity_key", "normalize_doi", "_select_canonical", "withheld_public"},
    ),
    "substrate.graph": _mod("substrate.graph", "substrate/graph/__init__.py"),
    "substrate.graph.ops": _mod("substrate.graph.ops", "substrate/graph/ops.py"),
}


def _l1(src: str) -> list:
    return find_l1_leaks("caller.py", ast.parse(src), INDEX)


# --------------------------------------------------------------------------- #
# L1 — private-name import                                                     #
# --------------------------------------------------------------------------- #

def test_l1_flags_underscore_private_import() -> None:
    leaks = _l1("from substrate.dedup import _select_canonical\n")
    assert len(leaks) == 1
    assert leaks[0].leaked_name == "_select_canonical"
    assert leaks[0].category == "L1"


def test_l1_flags_public_name_withheld_from_all() -> None:
    # withheld_public is defined + public-looking but NOT in __all__ → withheld leak
    leaks = _l1("from substrate.dedup import withheld_public\n")
    assert len(leaks) == 1
    assert "withheld" in leaks[0].detail


def test_l1_near_miss_public_import_not_flagged() -> None:
    assert _l1("from substrate.dedup import identity_key\n") == []


def test_l1_near_miss_alias_masking_not_flagged() -> None:
    # imported name `identity_key` is PUBLIC; the underscore is only a local alias.
    # L1 must key on alias.name, never alias.asname.
    assert _l1("from substrate.dedup import identity_key as _local\n") == []


def test_l1_near_miss_submodule_import_not_flagged() -> None:
    # `ops` is a submodule of substrate.graph, not a private name.
    assert _l1("from substrate.graph import ops\n") == []


def test_l1_near_miss_relative_import_not_flagged() -> None:
    # relative imports are intra-package co-ownership, out of L1 scope.
    assert _l1("from ._helper import thing\n") == []


def test_l1_near_miss_dunder_not_flagged() -> None:
    assert _l1("from substrate.dedup import __version__\n") == []


def test_l1_near_miss_thirdparty_not_flagged() -> None:
    # non-first-party target (not in index) is out of scope (that's boundary_check).
    assert _l1("from pydantic import _internal\n") == []


# --------------------------------------------------------------------------- #
# L2 — deep attribute reach-through                                            #
# --------------------------------------------------------------------------- #

def _l2(src: str) -> list:
    return find_l2_leaks("caller.py", ast.parse(src), INDEX)


def test_l2_flags_import_rooted_private_reachthrough() -> None:
    leaks = _l2("import substrate.dedup as dedup\nx = dedup._registry._field\n")
    assert len(leaks) == 1
    assert leaks[0].category == "L2"
    assert "_registry" in leaks[0].detail


def test_l2_near_miss_self_internal_not_flagged() -> None:
    # reaching into your OWN internals via self is not a boundary leak.
    assert _l2("import substrate.dedup as dedup\ny = self._cache.value\n") == []


def test_l2_near_miss_public_chain_not_flagged() -> None:
    assert _l2("import substrate.dedup as dedup\nz = dedup.public.attr\n") == []


def test_l2_near_miss_shallow_not_flagged() -> None:
    # depth-1 access (dedup._x) is not a >=2 reach-through.
    assert _l2("import substrate.dedup as dedup\nq = dedup._x\n") == []


def test_l2_near_miss_non_import_root_not_flagged() -> None:
    # root `local` is not a first-party import → cannot confirm a boundary → skip.
    assert _l2("local = get()\nr = local._a._b\n") == []


# --------------------------------------------------------------------------- #
# L3 — logic re-implementation candidate                                       #
# --------------------------------------------------------------------------- #

def test_l3_flags_reimplementation_candidate() -> None:
    leaks = find_l3_candidates("roles/foo.py", "roles.foo", ast.parse("def identity_key(r): return r\n"))
    assert len(leaks) == 1
    assert leaks[0].category == "L3"


def test_l3_owner_does_not_flag_itself() -> None:
    # substrate.dedup defining identity_key is the canonical home, not a leak.
    assert find_l3_candidates("substrate/dedup.py", "substrate.dedup", ast.parse("def identity_key(r): return r\n")) == []


# --------------------------------------------------------------------------- #
# Integration + index                                                          #
# --------------------------------------------------------------------------- #

def test_build_module_index_and_report(tmp_path: Path) -> None:
    (tmp_path / "substrate").mkdir()
    (tmp_path / "substrate" / "dedup.py").write_text(
        "__all__ = ['identity_key']\ndef identity_key(r): return r\ndef _helper(): return 1\n",
        encoding="utf-8",
    )
    (tmp_path / "roles").mkdir()
    (tmp_path / "roles" / "caller.py").write_text(
        "from substrate.dedup import _helper\nfrom substrate.dedup import identity_key\n",
        encoding="utf-8",
    )
    files = sorted(tmp_path.rglob("*.py"))
    index = build_module_index(tmp_path, files)
    assert "substrate.dedup" in index
    assert index["substrate.dedup"].has_all

    report = build_report(root=tmp_path, ranking_path=tmp_path / "nope.json", include_l3=False)
    # exactly one L1 leak (the _helper import); the identity_key import is clean
    assert report["counts"]["L1"] == 1
    assert report["ranking_joined"] is False  # graceful degradation, honestly recorded
    assert "fenced_targets" in report
    # round-trips (house convention)
    json.dumps(report, sort_keys=True)


def test_report_degrades_without_ranking(tmp_path: Path) -> None:
    (tmp_path / "substrate").mkdir()
    (tmp_path / "substrate" / "m.py").write_text("def f(): return 1\n", encoding="utf-8")
    report = build_report(root=tmp_path, ranking_path=tmp_path / "absent.json", include_l3=True)
    assert report["ranking_joined"] is False
    assert report["include_l3"] is True
