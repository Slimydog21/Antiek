"""§9.0: the audit trail must not carry paper content under ANY key (audit wave 3, #19)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest

from substrate.audit.arxiv_audit import _MAX_DETAIL_STRING_CHARS, _reject_body_in_detail

BODY = "lorem ipsum " * 200   # ~2400 chars, body-shaped

def test_control_named_key_still_rejected():
    with pytest.raises(ValueError):
        _reject_body_in_detail({"body": "x"})

def test_body_under_an_unlisted_key_is_rejected():
    with pytest.raises(ValueError, match="body-shaped"):
        _reject_body_in_detail({"excerpt": BODY})

def test_body_inside_a_list_is_rejected():
    with pytest.raises(ValueError, match=r"detail\.notes\[1\]"):
        _reject_body_in_detail({"notes": ["short", BODY]})

def test_body_nested_under_a_neutral_key_is_rejected():
    with pytest.raises(ValueError, match="body-shaped"):
        _reject_body_in_detail({"meta": {"reason": BODY}})

def test_refs_and_counts_are_accepted():
    _reject_body_in_detail({"arxiv_id": "2401.01234v2", "document_id": "doc-" + "a" * 36, "chunks": 12,
                            "reason": "takedown request received", "refs": ["2401.01234", "2401.05678"]})

def test_cap_boundary():
    _reject_body_in_detail({"reason": "r" * _MAX_DETAIL_STRING_CHARS})
    with pytest.raises(ValueError):
        _reject_body_in_detail({"reason": "r" * (_MAX_DETAIL_STRING_CHARS + 1)})
