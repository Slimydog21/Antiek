"""Red-proofs: HTML-native view preference gate."""

from __future__ import annotations

from substrate.books.html_preference import prefer_html_view


def test_prefer_html_when_ready() -> None:
    d = prefer_html_view(html_ready=True, pdf_available=True, require_html=True)
    assert d.mode == "html"
    assert d.preferred is True
    assert d.reason == "html_ready"


def test_html_wins_even_when_pdf_present() -> None:
    d = prefer_html_view(html_ready=True, pdf_available=True, require_html=False)
    assert d.mode == "html"
    assert d.preferred is True


def test_pdf_blocked_when_require_html() -> None:
    d = prefer_html_view(html_ready=False, pdf_available=True, require_html=True)
    assert d.mode == "metadata_only"
    assert d.preferred is False
    assert d.reason == "pdf_blocked_by_html_policy"
    assert any("require_html" in n for n in d.notes)


def test_pdf_fallback_when_policy_allows() -> None:
    d = prefer_html_view(html_ready=False, pdf_available=True, require_html=False)
    assert d.mode == "pdf"
    assert d.preferred is False
    assert d.reason == "pdf_fallback"


def test_unavailable_when_nothing() -> None:
    d = prefer_html_view(html_ready=False, pdf_available=False)
    assert d.mode == "unavailable"
    assert d.preferred is False
    assert d.reason == "no_viewable_representation"


def test_to_dict_shape() -> None:
    d = prefer_html_view(html_ready=True, asset_id="doc-1")
    payload = d.to_dict()
    assert payload["mode"] == "html"
    assert payload["preferred"] is True
    assert any("doc-1" in n for n in payload["notes"])


def test_decision_notes_are_immutable_and_dict_is_detached() -> None:
    decision = prefer_html_view(html_ready=True, asset_id="doc-1")
    assert isinstance(decision.notes, tuple)

    payload = decision.to_dict()
    payload["notes"].append("caller mutation")

    assert "caller mutation" not in decision.notes


def test_rejects_truthy_string_as_ready() -> None:
    import pytest

    with pytest.raises(TypeError, match="html_ready"):
        prefer_html_view(html_ready="false")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="pdf_available"):
        prefer_html_view(html_ready=False, pdf_available="true")  # type: ignore[arg-type]
