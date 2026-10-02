"""A revocation is honoured for any affirmative value, not only JSON true (audit wave 3, #11)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest

from acquisition.opt_in.manifest import (
    ManifestEntry,
    _withdrawn_is_affirmative,
    validate_grant,
)


@pytest.mark.parametrize("value", [True, "yes", "YES", 1, 2.0, "2026-01-01", "revoked", {"at": "2026-01-01"}, ["x"]])
def test_affirmative_values_mean_withdrawn(value):
    assert _withdrawn_is_affirmative(value) is True

@pytest.mark.parametrize("value", [None, False, 0, "", "false", "No", "n", "0", "null"])
def test_negative_values_mean_not_withdrawn(value):
    assert _withdrawn_is_affirmative(value) is False

def test_control_json_true_still_gates():
    v = validate_grant(
        ManifestEntry(title="X", grant={"statement": "I authorise Antiek to serve this work.", "withdrawn": True}),
        catalog_grant=None,
    )
    assert v.valid is False and "withdrawn" in v.reason

def test_string_yes_now_gates_too():
    v = validate_grant(
        ManifestEntry(title="X", grant={"statement": "I authorise Antiek to serve this work.", "withdrawn": "yes"}),
        catalog_grant=None,
    )
    assert v.valid is False, "withdrawn='yes' was ignored — a revoked grant stayed servable"
    assert "withdrawn" in v.reason
