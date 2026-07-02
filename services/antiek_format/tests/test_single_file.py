"""SPR-04 M5: single-file .antiek.html variant — verification gates.

Proves: a genuine file verifies; a tampered island OR tampered rendered
markup both fail (the signed scope is the whole file minus the signature
island); the variant is zero-script and self-contained; and disk round-trip
+ build determinism hold (Ed25519 is deterministic).
"""

from __future__ import annotations

import re

import pytest

from services.antiek_format.single_file import (
    build_single_file,
    verify_single_file,
    verify_single_file_html,
)
from services.html_projection.context import RenderContext
from services.html_projection.gate import assert_script_free
from services.html_projection.renderer import render

_DOC_ISLAND_RE = re.compile(
    r'<template[^>]*data-antiek="doc-model"[^>]*>.*?</template>', re.DOTALL
)
_SIG_ISLAND_RE = re.compile(
    r'<template data-antiek="signature">.*?</template>', re.DOTALL
)


def _projection() -> str:
    return render(
        {
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Hello world"}],
                }
            ],
            "title": "Shareable",
        },
        RenderContext(),
    )


def test_genuine_single_file_verifies(keypair):
    assert verify_single_file_html(build_single_file(_projection(), keypair=keypair))


def test_single_file_is_gate_clean(keypair):
    # The signature island is an inert <template>, like the doc-model island.
    assert_script_free(build_single_file(_projection(), keypair=keypair))


def test_tampered_markup_fails(keypair):
    single = build_single_file(_projection(), keypair=keypair)
    tampered = single.replace("Hello world", "Hello WORLD", 1)
    assert tampered != single
    assert verify_single_file_html(tampered) is False


def test_tampered_island_fails(keypair):
    single = build_single_file(_projection(), keypair=keypair)
    m = _DOC_ISLAND_RE.search(single)
    assert m is not None
    span = m.group(0)
    mid = len(span) // 2
    repl = "X" if span[mid] != "X" else "Y"
    tampered = single.replace(span, span[:mid] + repl + span[mid + 1 :], 1)
    assert tampered != single
    assert verify_single_file_html(tampered) is False


def test_missing_signature_island_fails(keypair):
    assert verify_single_file_html(_projection()) is False


def test_removed_signature_island_fails(keypair):
    single = build_single_file(_projection(), keypair=keypair)
    stripped = _SIG_ISLAND_RE.sub("", single, count=1)
    assert verify_single_file_html(stripped) is False


def test_double_wrap_refused(keypair):
    single = build_single_file(_projection(), keypair=keypair)
    with pytest.raises(ValueError):
        build_single_file(single, keypair=keypair)


def test_verify_from_disk(tmp_path, keypair):
    single = build_single_file(_projection(), keypair=keypair)
    p = tmp_path / "share.antiek.html"
    p.write_text(single, encoding="utf-8")
    assert verify_single_file(str(p)) is True
    p.write_text(single.replace("Hello world", "Hi", 1), encoding="utf-8")
    assert verify_single_file(str(p)) is False
    assert verify_single_file(str(tmp_path / "does-not-exist.html")) is False


def test_build_is_deterministic(keypair):
    # Ed25519 signing is deterministic, the JSON island is canonical, and the
    # injection point is fixed -> byte-identical builds.
    assert build_single_file(_projection(), keypair=keypair) == build_single_file(
        _projection(), keypair=keypair
    )
