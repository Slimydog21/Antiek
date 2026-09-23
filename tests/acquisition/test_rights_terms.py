"""RSL licence parsing (acquisition.urls.rights_terms)."""

from __future__ import annotations

from acquisition.urls.rights_terms import parse_license_directive, parse_rsl_xml


def test_a_licence_with_no_payment_element_is_free() -> None:
    """RSL 1.0 s3.7: "If omitted, the license is assumed to be free"."""
    terms = parse_rsl_xml(
        '<rsl xmlns="https://rslstandard.org/rsl"><content url="/"><license>'
        '<permits type="usage">all</permits></license></content></rsl>'
    )

    assert terms.payment_types == ("free",)
    assert terms.no_charge is True


def test_an_explicit_payment_is_not_overridden_by_the_default() -> None:
    terms = parse_rsl_xml(
        '<rsl><content url="/"><license><payment type="crawl"/></license></content></rsl>'
    )

    assert terms.payment_types == ("crawl",)
    assert terms.requires_payment is True


def test_a_document_without_a_licence_declares_no_payment() -> None:
    terms = parse_rsl_xml('<rsl><content url="/"></content></rsl>')

    assert terms.payment_types == ()
    assert terms.no_charge is False


def test_the_licence_directive_survives_a_byte_order_mark() -> None:
    assert parse_license_directive("﻿License: /license.xml\n") == "/license.xml"
