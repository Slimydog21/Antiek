"""Tests for pure deep-research source pack builder."""

from __future__ import annotations

import pytest

from substrate.research_sources.readiness import SourceReadiness
from substrate.research_sources.source_pack import SourcePackError, build_source_pack


def _ready(source: str = "arxiv") -> SourceReadiness:
    return SourceReadiness(
        source=source,  # type: ignore[arg-type]
        status="ready",
        adapter_importable=True,
        callables_present=True,
        offline_probe_ok=True,
        runner_consumes_today=False,
        external_call_would_be_required=True,
        note="import ok",
        details=[],
    )


def test_build_includes_ready_selected() -> None:
    pack = build_source_pack(
        ["arxiv", "substack"],
        {
            "arxiv": _ready("arxiv"),
            "substack": SourceReadiness(
                source="substack",
                status="gated",
                adapter_importable=True,
                callables_present=True,
                offline_probe_ok=False,
                runner_consumes_today=False,
                external_call_would_be_required=True,
                note="gated",
                details=[],
            ),
        },
    )
    d = pack.to_dict()
    assert d["live_fetch_authorized"] is False
    assert d["authority"] == "advisory_preflight"
    assert d["included_count"] == 2
    assert "arxiv" in d["pack_text"]
    assert any("offline_probe_ok" in n for n in d["notes"])


def test_unavailable_selected_not_included() -> None:
    pack = build_source_pack(
        ["arxiv"],
        {
            "arxiv": SourceReadiness(
                source="arxiv",
                status="unavailable",
                adapter_importable=False,
                callables_present=False,
                offline_probe_ok=False,
                runner_consumes_today=False,
                external_call_would_be_required=True,
                note="missing",
                details=[],
            ),
        },
    )
    assert pack.included_count == 0
    assert any("unavailable" in n for n in pack.notes)


def test_unknown_source_rejected() -> None:
    with pytest.raises(SourcePackError, match="unknown source"):
        build_source_pack(["not-a-source"])


def test_empty_selected_rejected() -> None:
    with pytest.raises(SourcePackError, match="selected"):
        build_source_pack([])


def test_runner_true_with_unavailable_rejected() -> None:
    with pytest.raises(SourcePackError, match="runner_consumes_today"):
        build_source_pack(
            ["arxiv"],
            {
                "arxiv": {
                    "status": "unavailable",
                    "adapter_importable": False,
                    "offline_probe_ok": False,
                    "runner_consumes_today": True,
                    "note": "bad",
                },
            },
        )


def test_mapping_requires_bool_fields() -> None:
    with pytest.raises(SourcePackError, match="offline_probe_ok"):
        build_source_pack(
            ["web"],
            {
                "web": {
                    "status": "ready",
                    "adapter_importable": True,
                    "offline_probe_ok": "yes",
                    "runner_consumes_today": False,
                    "note": "x",
                },
            },
        )


def test_missing_readiness_uses_null_bools_not_false() -> None:
    pack = build_source_pack(["arxiv"], {})
    arxiv = next(e for e in pack.entries if e.source == "arxiv")
    assert arxiv.runner_consumes_today is None
    assert arxiv.offline_probe_ok is None
    assert arxiv.adapter_importable is None


def test_readiness_key_case_normalized() -> None:
    pack = build_source_pack(
        ["arxiv"],
        {
            "ARXIV": {
                "status": "ready",
                "adapter_importable": True,
                "offline_probe_ok": True,
                "runner_consumes_today": False,
                "note": "ok",
            },
        },
    )
    assert pack.included_count == 1
