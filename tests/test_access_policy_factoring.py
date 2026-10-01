"""The shared leaf preserves the immutable owner-scoped chunk contract."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from substrate import access_policy
from substrate.graph import retrieval_gate

_REPO = Path(__file__).resolve().parents[1]
_GOLDEN = json.loads(
    (_REPO / "tests/fixtures/pa04a_chunk_gate_689846.json").read_text()
)


@pytest.mark.parametrize("case", _GOLDEN["cases"])
def test_chunk_sql_and_binds_equal_immutable_base(case):
    assert retrieval_gate.non_privileged_chunk_sql_clause(
        table_alias=case["alias"],
        policy_tag=case["policy"],
        owner_user_id=case["owner"],
    ) == (case["sql"], case["params"])


def test_omitted_defaults_equal_immutable_base():
    expected = _GOLDEN["default"]
    assert retrieval_gate.non_privileged_chunk_sql_clause() == (
        expected["sql"], expected["params"]
    )


@pytest.mark.parametrize("alias,sql", _GOLDEN["takedown_sql"].items())
def test_relocated_takedown_sql(alias, sql):
    assert access_policy.taken_down_chunk_exclusion_sql(table_alias=alias) == sql
    assert retrieval_gate.taken_down_chunk_exclusion_sql(table_alias=alias) == sql


@pytest.mark.parametrize("case", _GOLDEN["usable_owner"])
def test_relocated_owner_validation(case):
    assert access_policy._usable_owner_id(case["input"]) == case["output"]
    assert retrieval_gate._usable_owner_id(case["input"]) == case["output"]


def test_relocated_private_set():
    expected = frozenset(_GOLDEN["personal_only_content_classes"])
    assert expected == access_policy.PERSONAL_ONLY_CONTENT_CLASSES
    assert expected == retrieval_gate.PERSONAL_ONLY_CONTENT_CLASSES


def test_invalid_takedown_alias_still_raises():
    with pytest.raises(ValueError):
        access_policy.taken_down_chunk_exclusion_sql(table_alias="d.bad")


@pytest.mark.parametrize("order", [
    "substrate.rights.register,substrate.graph.retrieval_gate,substrate.graph.search,substrate.rights.document_visibility,substrate.access_policy",
    "substrate.graph.retrieval_gate,substrate.rights.register,substrate.graph.search,substrate.rights.document_visibility,substrate.access_policy",
    "substrate.graph.search,substrate.rights.document_visibility,substrate.rights.register,substrate.graph.retrieval_gate,substrate.access_policy",
    "substrate.rights.document_visibility,substrate.graph.search,substrate.graph.retrieval_gate,substrate.rights.register,substrate.access_policy",
    "substrate.access_policy,substrate.rights.document_visibility,substrate.graph.search,substrate.rights.register,substrate.graph.retrieval_gate",
])
def test_fresh_import_order(order):
    code = (
        "import importlib; "
        f"[importlib.import_module(name) for name in {order.split(',')!r}]; "
        "from substrate.rights.document_visibility import document_discoverability_sql; "
        "from substrate.graph.retrieval_gate import "
        "non_privileged_chunk_sql_clause, non_privileged_node_provenance_clause; "
        "document_discoverability_sql(owner_user_id=None); "
        "non_privileged_chunk_sql_clause(owner_user_id=None); "
        "non_privileged_node_provenance_clause(owner_user_id=None)"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_REPO)
    subprocess.run([sys.executable, "-c", code], cwd=_REPO, env=env, check=True)
