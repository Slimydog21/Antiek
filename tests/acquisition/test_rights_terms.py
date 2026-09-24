"""RSL licence parsing (acquisition.urls.rights_terms)."""

from __future__ import annotations

from acquisition.urls.rights_terms import RightsTerms, parse_rsl_licence
from acquisition.urls.robots import parse_robots, terms_covering


def parse_rsl_xml(xml_text: str) -> RightsTerms:
    """The terms of a one-``<content>`` licence document."""
    licence = parse_rsl_licence(xml_text)
    assert licence.unscoped is None
    assert len(licence.scopes) == 1
    return licence.scopes[0]


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


_ORIGIN = "https://a.example"


def _two_scopes() -> str:
    return (
        "<rsl>"
        '<content url="/"><license><payment type="purchase"/></license></content>'
        '<content url="/open/" server="https://rsl.example/olp"><license>'
        '<permits type="usage">all</permits><payment type="attribution"/>'
        "</license></content>"
        "</rsl>"
    )


def test_each_content_element_keeps_only_its_own_terms() -> None:
    licence = parse_rsl_licence(_two_scopes(), license_url=f"{_ORIGIN}/license.xml")

    site, open_scope = licence.scopes
    assert (site.content_url, site.payment_types, site.permits) == ("/", ("purchase",), ())
    assert site.license_servers == ()
    assert open_scope.content_url == "/open/"
    assert open_scope.payment_types == ("attribution",)
    assert open_scope.permits == ("usage:all",)
    assert open_scope.license_servers == ("https://rsl.example/olp",)


def test_a_page_gets_the_most_specific_covering_scope() -> None:
    licence = parse_rsl_licence(_two_scopes(), license_url=f"{_ORIGIN}/license.xml")

    assert terms_covering(licence, origin=_ORIGIN, url=f"{_ORIGIN}/open/a").content_url == "/open/"
    assert terms_covering(licence, origin=_ORIGIN, url=f"{_ORIGIN}/shop").content_url == "/"


def test_no_covering_scope_means_the_page_terms_are_unknown() -> None:
    licence = parse_rsl_licence(
        '<rsl><content url="/free"><license/></content></rsl>',
        license_url=f"{_ORIGIN}/license.xml",
    )

    terms = terms_covering(licence, origin=_ORIGIN, url=f"{_ORIGIN}/paid")
    assert terms.source == "rsl_out_of_scope"
    assert terms.license_url == f"{_ORIGIN}/license.xml"
    assert terms.declared is True
    assert (terms.no_charge, terms.requires_payment, terms.payment_types) == (False, False, ())


def test_an_absolute_content_url_covers_only_its_own_origin() -> None:
    licence = parse_rsl_licence(
        '<rsl><content url="https://b.example/"><license/></content></rsl>',
        license_url=f"{_ORIGIN}/license.xml",
    )

    assert terms_covering(licence, origin=_ORIGIN, url=f"{_ORIGIN}/x").source == "rsl_out_of_scope"
    same = parse_rsl_licence(
        f'<rsl><content url="{_ORIGIN}/docs/"><license/></content></rsl>',
        license_url=f"{_ORIGIN}/license.xml",
    )
    assert terms_covering(same, origin=_ORIGIN, url=f"{_ORIGIN}/docs/a").no_charge is True
    assert terms_covering(same, origin=_ORIGIN, url=f"{_ORIGIN}/blog").source == "rsl_out_of_scope"


def test_an_empty_content_url_covers_the_whole_origin_least_specifically() -> None:
    """RSL 1.0 s4.6.1: an empty url names the scope of the association, here
    the origin whose robots.txt declared the licence."""
    licence = parse_rsl_licence(
        "<rsl>"
        '<content url=""><license><payment type="crawl"/></license></content>'
        '<content url="/free/"><license/></content>'
        "</rsl>",
        license_url=f"{_ORIGIN}/license.xml",
    )

    assert terms_covering(licence, origin=_ORIGIN, url=f"{_ORIGIN}/a").payment_types == ("crawl",)
    assert terms_covering(licence, origin=_ORIGIN, url=f"{_ORIGIN}/free/a").no_charge is True


def test_a_malformed_licence_answers_the_same_for_every_page() -> None:
    licence = parse_rsl_licence("<rsl><content", license_url=f"{_ORIGIN}/license.xml")

    terms = terms_covering(licence, origin=_ORIGIN, url=f"{_ORIGIN}/anything")
    assert terms.source == "robots_license_directive"
    assert terms.parse_error
