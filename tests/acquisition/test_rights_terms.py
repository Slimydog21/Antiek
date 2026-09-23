"""RSL licence parsing (acquisition.urls.rights_terms)."""

from __future__ import annotations

from acquisition.urls.rights_terms import parse_rsl_xml
from acquisition.urls.robots import parse_robots


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
    assert (
        parse_robots(
            "﻿License: /license.xml\nUser-agent: *\nAllow: /\n"
        ).global_licenses
        == ("/license.xml",)
    )


def test_a_free_licence_behind_a_licence_server_still_needs_a_token() -> None:
    """RSL 1.0 s3.3: with ``<content server>``, clients "MUST obtain a license
    from this server ... before access, even if the license type is free"."""
    terms = parse_rsl_xml(
        '<rsl><content url="/" server="https://rsl.example/olp"><license>'
        '<payment type="free"/></license></content></rsl>'
    )

    assert terms.no_charge is False
    assert terms.token_required is True
    assert terms.license_servers == ("https://rsl.example/olp",)
    assert terms.payment_types == ("free",)
    assert terms.requires_payment is False


def test_a_free_licence_without_a_server_needs_no_token() -> None:
    terms = parse_rsl_xml(
        '<rsl><content url="/"><license><payment type="attribution"/></license>'
        "</content></rsl>"
    )

    assert terms.token_required is False
    assert terms.no_charge is True
