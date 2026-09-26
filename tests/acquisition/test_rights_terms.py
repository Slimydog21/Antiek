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
    assert (site.content_url, site.payment_types, site.permits) == ("/", ("purchase",), None)
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


def test_an_empty_content_url_covers_nothing_in_a_robots_linked_licence() -> None:
    """RSL 1.0 s3.3.1: ``url=""`` names "the scope established by that
    association mechanism" only when the mechanism permits it; robots.txt
    (s4.4) does not, so the empty scope covers no page and grants nothing."""
    licence = parse_rsl_licence(
        "<rsl>"
        '<content url=""><license><payment type="free"/></license></content>'
        '<content url="/open/"><license><payment type="attribution"/></license></content>'
        "</rsl>",
        license_url=f"{_ORIGIN}/license.xml",
    )

    paid = terms_covering(licence, origin=_ORIGIN, url=f"{_ORIGIN}/paid")
    assert (paid.source, paid.no_charge, paid.payment_types) == ("rsl_out_of_scope", False, ())
    assert terms_covering(licence, origin=_ORIGIN, url=f"{_ORIGIN}/open/a").payment_types == (
        "attribution",
    )


def test_every_covering_scope_contributes_its_prohibitions() -> None:
    """RSL 1.0 s3.1.1: terms are evaluated together; the most specific scope
    sets payment and permissions, and no covering prohibition is dropped."""
    licence = parse_rsl_licence(
        "<rsl>"
        '<content url="/"><license><prohibits type="usage">ai-train</prohibits>'
        '<permits type="usage">search</permits></license></content>'
        '<content url="/free/"><license><permits type="usage">ai-input</permits>'
        '<prohibits type="usage">ai-index</prohibits><payment type="free"/></license></content>'
        "</rsl>",
        license_url=f"{_ORIGIN}/license.xml",
    )

    free = terms_covering(licence, origin=_ORIGIN, url=f"{_ORIGIN}/free/a")
    assert free.content_url == "/free/"
    assert free.payment_types == ("free",)
    assert free.permits == ("usage:ai-input",)
    assert set(free.prohibits) == {"usage:ai-train", "usage:ai-index"}
    site = terms_covering(licence, origin=_ORIGIN, url=f"{_ORIGIN}/blog")
    assert (site.permits, site.prohibits) == (("usage:search",), ("usage:ai-train",))


def test_a_narrower_scope_cannot_permit_what_a_covering_scope_prohibits() -> None:
    """RSL 1.0 s3.1.1: when a term both permits and prohibits a usage, "the
    prohibition MUST take precedence and the usage MUST be treated as not
    licensed", so the narrower scope's permission of it is dropped."""
    licence = parse_rsl_licence(
        "<rsl>"
        '<content url="/"><license><prohibits type="usage">ai-train</prohibits>'
        "</license></content>"
        '<content url="/free/"><license><permits type="usage">ai-train</permits>'
        '<permits type="usage">search</permits><payment type="free"/></license></content>'
        "</rsl>",
        license_url=f"{_ORIGIN}/license.xml",
    )

    free = terms_covering(licence, origin=_ORIGIN, url=f"{_ORIGIN}/free/a")
    assert (free.permits, free.prohibits) == (("usage:search",), ("usage:ai-train",))
    assert free.payment_types == ("free",)


def test_a_malformed_licence_answers_the_same_for_every_page() -> None:
    licence = parse_rsl_licence("<rsl><content", license_url=f"{_ORIGIN}/license.xml")

    terms = terms_covering(licence, origin=_ORIGIN, url=f"{_ORIGIN}/anything")
    assert terms.source == "robots_license_directive"
    assert terms.parse_error


# --- adversarial review of 5231bd522 -----------------------------------------


def _tied(first: str, second: str) -> RightsTerms:
    licence = parse_rsl_licence(f"<rsl>{first}{second}</rsl>", license_url=f"{_ORIGIN}/license.xml")
    return terms_covering(licence, origin=_ORIGIN, url=f"{_ORIGIN}/abc")


_FREE_A = (
    '<content url="/a*"><license><permits type="usage">search</permits>'
    '<payment type="free"/></license></content>'
)
_PURCHASE_AB = (
    '<content url="/ab"><license><prohibits type="usage">search</prohibits>'
    '<payment type="purchase"/></license></content>'
)


def test_equally_specific_scopes_resolve_conservatively_in_either_order() -> None:
    """RSL 1.0 s3.1.1: licences "MUST be interpreted conservatively". Two
    equally specific covering scopes have no precedence over each other, so a
    priced payment wins over a free one and only what both permit is
    permitted, whichever comes first in the file."""
    for first, second in ((_FREE_A, _PURCHASE_AB), (_PURCHASE_AB, _FREE_A)):
        terms = _tied(first, second)
        assert terms.payment_types == ("purchase",), (first, terms)
        assert (terms.no_charge, terms.requires_payment) == (False, True)
        assert terms.permits == ()
        assert terms.prohibits == ("usage:search",)

    wide = (
        '<content url="/a*"><license><permits type="usage">search ai-index</permits>'
        '<payment type="free"/></license></content>'
    )
    narrow = (
        '<content url="/ab"><license><permits type="usage">search</permits>'
        '<payment type="attribution"/></license></content>'
    )
    for first, second in ((wide, narrow), (narrow, wide)):
        terms = _tied(first, second)
        assert terms.permits == ("usage:search",)
        assert set(terms.payment_types) == {"free", "attribution"}
        assert terms.no_charge is True


def test_a_permits_element_lists_space_separated_usages() -> None:
    """RSL 1.0 s3.5/s3.6: values are "separated by one or more spaces"."""
    terms = parse_rsl_xml(
        '<rsl><content url="/"><license><permits type="usage">ai-train  search</permits>'
        '<prohibits type="usage">ai-input,ai-index</prohibits></license></content></rsl>'
    )

    assert terms.permits == ("usage:ai-train", "usage:search")
    assert terms.prohibits == ("usage:ai-input", "usage:ai-index")


def test_an_umbrella_prohibition_removes_every_usage_it_covers() -> None:
    """RSL 1.0 s3.4.1.1: ``ai-all`` covers ai-train, ai-input and ai-index;
    ``all`` covers every automated use including search. A usage covered by
    a prohibited umbrella is not licensed (s3.1.1)."""

    def page(site_prohibits: str, narrow_permits: str) -> RightsTerms:
        licence = parse_rsl_licence(
            "<rsl>"
            f'<content url="/"><license><prohibits type="usage">{site_prohibits}</prohibits>'
            "</license></content>"
            f'<content url="/n/"><license>{narrow_permits}<payment type="free"/>'
            "</license></content></rsl>",
            license_url=f"{_ORIGIN}/license.xml",
        )
        return terms_covering(licence, origin=_ORIGIN, url=f"{_ORIGIN}/n/x")

    ai_all = page(
        "ai-all",
        '<permits type="usage">ai-train</permits><permits type="usage">ai-train,search</permits>',
    )
    assert ai_all.permits == ("usage:search",)
    assert ai_all.prohibits == ("usage:ai-all",)
    assert page("all", '<permits type="usage">search</permits>').permits == ()
    split = page("ai-train", '<permits type="usage">all</permits>')
    assert set(split.permits) == {"usage:ai-input", "usage:ai-index", "usage:search"}


def test_a_licence_server_on_any_covering_scope_still_requires_a_token() -> None:
    """RSL 1.0 s3.3: a client "MUST obtain a license from this server ...
    before access, even if the license type is free". A narrower free scope
    without a server does not lift that requirement (s3.1.1, conservative)."""
    licence = parse_rsl_licence(
        "<rsl>"
        '<content url="/" server="https://ls.example"><license><payment type="free"/>'
        "</license></content>"
        '<content url="/free/"><license><payment type="free"/></license></content>'
        "</rsl>",
        license_url=f"{_ORIGIN}/license.xml",
    )

    terms = terms_covering(licence, origin=_ORIGIN, url=f"{_ORIGIN}/free/x")
    assert terms.content_url == "/free/"
    assert terms.license_servers == ("https://ls.example",)
    assert (terms.token_required, terms.no_charge) == (True, False)


def test_an_unplaceable_scope_still_contributes_its_prohibitions() -> None:
    """A ``url=""`` scope establishes no page scope under the robots.txt
    association (RSL 1.0 s3.3.1, s4.4), so it grants nothing; but dropping
    its ban would expand rights (s3.1.1), so every page that other scopes
    give terms to keeps it."""
    licence = parse_rsl_licence(
        "<rsl>"
        '<content url=""><license><prohibits type="usage">ai-train</prohibits></license></content>'
        '<content url="/"><license><payment type="free"/></license></content>'
        "</rsl>",
        license_url=f"{_ORIGIN}/license.xml",
    )

    paid = terms_covering(licence, origin=_ORIGIN, url=f"{_ORIGIN}/paid")
    assert paid.prohibits == ("usage:ai-train",)
    assert paid.payment_types == ("free",)
    only_empty = parse_rsl_licence(
        '<rsl><content url=""><license><prohibits type="usage">ai-train</prohibits>'
        "</license></content></rsl>",
        license_url=f"{_ORIGIN}/license.xml",
    )
    unknown = terms_covering(only_empty, origin=_ORIGIN, url=f"{_ORIGIN}/paid")
    assert (unknown.source, unknown.prohibits) == ("rsl_out_of_scope", ())


def test_a_licence_with_too_many_content_scopes_is_not_parsed() -> None:
    """Each scope costs memory and matching time out of proportion to its
    bytes (a bare ``<content/>`` is ten), so a licence past
    MAX_LICENCE_SCOPES is recorded as unusable instead of held."""
    from acquisition.urls import rights_terms

    limit = getattr(rights_terms, "MAX_LICENCE_SCOPES", 1024)
    licence = parse_rsl_licence(
        "<rsl>" + "<content/>" * (limit + 1) + "</rsl>", license_url=f"{_ORIGIN}/license.xml"
    )

    assert licence.scopes == ()
    assert licence.unscoped is not None
    assert "scopes" in (licence.unscoped.parse_error or "")
    at_limit = parse_rsl_licence("<rsl>" + "<content/>" * limit + "</rsl>")
    assert len(at_limit.scopes) == limit


def test_an_equally_specific_scope_with_no_payment_keeps_the_page_from_free() -> None:
    """A tied scope that declares no licence says nothing about payment, and
    "unknown" combined with "free" is not "free" (RSL 1.0 s3.1.1,
    conservative), whichever comes first in the file."""
    bare = '<content url="/ab"></content>'
    for first, second in ((_FREE_A, bare), (bare, _FREE_A)):
        terms = _tied(first, second)
        assert terms.payment_types == (), (first, terms)
        assert (terms.no_charge, terms.requires_payment) == (False, False)
        # The bare scope declares no whitelist, so the other one stands.
        assert terms.permits == ("usage:search",)


def test_a_licence_whose_parsed_terms_outgrow_the_budget_is_not_parsed() -> None:
    """Splitting an element's text into one ``"<type>:<value>"`` entry per
    value repeats the ``type`` once per value, and a nested ``<content>``
    re-reads every element inside it, so a small document could expand into
    far more parsed text than it holds. Past MAX_LICENCE_TERM_CHARS the
    licence is recorded as unusable instead."""
    from acquisition.urls import rights_terms

    limit = getattr(rights_terms, "MAX_LICENCE_TERM_CHARS", 256 * 1024)
    long_type = '<rsl><content url="/"><license><permits type="{}">{}</permits></license></content></rsl>'
    nested_depth = 400
    shapes = {
        "repeated type": long_type.format("t" * 2000, "a " * 20_000),
        "nested scopes": (
            '<rsl>' + '<content url="/">' * nested_depth
            + '<license><permits type="usage">' + " ".join(f"u{i}" for i in range(2000))
            + "</permits></license>" + "</content>" * nested_depth + "</rsl>"
        ),
    }
    for name, document in shapes.items():
        assert len(document) < limit, name
        licence = parse_rsl_licence(document, license_url=f"{_ORIGIN}/license.xml")
        held = sum(
            len(entry)
            for scope in licence.scopes
            for entry in (scope.permits or ()) + scope.prohibits + scope.payment_types
        )
        assert held <= limit, (name, held)
        assert licence.unscoped is not None, name
        assert "characters" in (licence.unscoped.parse_error or ""), name
    ordinary = parse_rsl_licence(long_type.format("usage", "search ai-index"))
    assert ordinary.scopes[0].permits == ("usage:search", "usage:ai-index")


def test_repeated_umbrella_permits_are_combined_in_linear_time() -> None:
    """Every page fetch combines the covering scopes' terms, so that must not
    cost permits x prohibits: a licence repeating ``all`` thousands of times
    beside thousands of prohibitions is combined in milliseconds."""
    import time

    count = 7000
    licence = parse_rsl_licence(
        "<rsl>"
        f'<content url="/"><license><prohibits type="usage">'
        f'{" ".join(f"p{i}" for i in range(count))}</prohibits></license></content>'
        f'<content url="/n/"><license><permits type="usage">{"all " * count}</permits>'
        '<payment type="free"/></license></content></rsl>',
        license_url=f"{_ORIGIN}/license.xml",
    )
    assert licence.unscoped is None

    started = time.perf_counter()
    terms = terms_covering(licence, origin=_ORIGIN, url=f"{_ORIGIN}/n/x")
    elapsed = time.perf_counter() - started

    assert terms.permits == ("usage:all",)
    assert elapsed < 1.0, elapsed


# --- adversarial review of dae1d1ddd -----------------------------------------
#
# A scope with no <permits> element restricts use only through <prohibits>
# (RSL 1.0 s3.5); a combination whose whitelist ends up empty permits
# nothing. Both used to be ``permits == ()``, so the conservative answer read
# like the unrestricted one.


def test_no_permits_element_is_told_apart_from_an_empty_whitelist() -> None:
    undeclared = parse_rsl_xml(
        '<rsl><content url="/"><license><payment type="free"/></license></content></rsl>'
    )
    empty = parse_rsl_xml(
        '<rsl><content url="/"><license><permits type="usage"></permits>'
        "</license></content></rsl>"
    )

    assert undeclared.permits is None
    assert empty.permits == ()


_NO_PERMITS_A = '<content url="/a*"><license><payment type="free"/></license></content>'
_SEARCH_AB = (
    '<content url="/ab"><license><permits type="usage">search</permits>'
    '<payment type="free"/></license></content>'
)
_AI_TRAIN_AB = (
    '<content url="/ab"><license><permits type="usage">ai-train</permits>'
    '<payment type="free"/></license></content>'
)


def test_a_tied_scope_without_permits_leaves_the_other_whitelist_standing() -> None:
    """Probe case 1: equally specific scopes, one with no <permits> and one
    permitting search. The undeclared side restricts nothing, so the page's
    whitelist is search, in either document order; two undeclared sides stay
    undeclared."""
    for first, second in ((_NO_PERMITS_A, _SEARCH_AB), (_SEARCH_AB, _NO_PERMITS_A)):
        assert _tied(first, second).permits == ("usage:search",), (first, second)
    assert _tied(_NO_PERMITS_A, '<content url="/ab"></content>').permits is None


def test_disjoint_tied_whitelists_permit_nothing() -> None:
    """Probe case 2: equally specific scopes permitting ai-train and search
    only share nothing (s3.1.1, conservative): a declared, empty whitelist,
    not the ``None`` of a scope that set no whitelist."""
    for first, second in ((_AI_TRAIN_AB, _SEARCH_AB.replace("/ab", "/a*")),
                          (_SEARCH_AB.replace("/ab", "/a*"), _AI_TRAIN_AB)):
        terms = _tied(first, second)
        assert terms.permits == (), (first, terms)
        assert terms.permits is not None


def test_a_whitelist_emptied_by_a_prohibition_permits_nothing() -> None:
    """Probe case 3: a narrow scope permits only ai-train and the site-wide
    scope prohibits ai-train. Nothing is left to permit; a narrow scope that
    set no whitelist keeps ``None`` and the prohibition alone restricts it."""

    def page(narrow_permits: str) -> RightsTerms:
        licence = parse_rsl_licence(
            "<rsl>"
            '<content url="/"><license><prohibits type="usage">ai-train</prohibits>'
            "</license></content>"
            f'<content url="/free/"><license>{narrow_permits}<payment type="free"/>'
            "</license></content></rsl>",
            license_url=f"{_ORIGIN}/license.xml",
        )
        return terms_covering(licence, origin=_ORIGIN, url=f"{_ORIGIN}/free/x")

    emptied = page('<permits type="usage">ai-train</permits>')
    assert emptied.permits == ()
    assert emptied.prohibits == ("usage:ai-train",)
    undeclared = page("")
    assert undeclared.permits is None
    assert undeclared.prohibits == ("usage:ai-train",)


def test_the_permit_combinators_treat_an_undeclared_whitelist_as_the_identity() -> None:
    from acquisition.urls.rights_terms import permits_in_both, permits_without

    search = ("usage:search",)
    assert permits_in_both(None, search) == search
    assert permits_in_both(search, None) == search
    assert permits_in_both(None, None) is None
    assert permits_without(None, ("usage:ai-train",)) is None
    assert permits_without(("usage:ai-train",), ("usage:ai-train",)) == ()


def test_a_site_wide_whitelist_survives_a_narrower_scope_that_sets_none() -> None:
    """Review probe 1k (RSL 1.0 s3.1.1, "interpreted conservatively to avoid
    the unintended expansion of rights"): the site-wide scope licenses only
    search. A narrower scope that declares no <permits> says nothing about
    permissions, so it cannot license ai-train on /x/a; the site-wide
    whitelist stands, and the narrower scope still sets payment and adds its
    prohibition."""
    licence = parse_rsl_licence(
        "<rsl>"
        '<content url="/"><license><permits type="usage">search</permits></license></content>'
        '<content url="/x/"><license><prohibits type="usage">ai-input</prohibits>'
        '<payment type="free"/></license></content>'
        "</rsl>",
        license_url=f"{_ORIGIN}/license.xml",
    )

    terms = terms_covering(licence, origin=_ORIGIN, url=f"{_ORIGIN}/x/a")

    assert terms.permits == ("usage:search",)
    assert terms.prohibits == ("usage:ai-input",)
    assert terms.payment_types == ("free",)
    assert terms.content_url == "/x/"


def test_the_nearest_declared_whitelist_decides_a_page_whose_scope_sets_none() -> None:
    """Three nested scopes: / permits search, /x/ permits search and ai-train,
    /x/y/ declares no <permits>. The most specific declaration of permissions
    (/x/) takes precedence over the less specific one (/), as for any other
    term; a scope declaring none leaves that declaration standing."""
    licence = parse_rsl_licence(
        "<rsl>"
        '<content url="/"><license><permits type="usage">search</permits></license></content>'
        '<content url="/x/"><license><permits type="usage">search,ai-train</permits>'
        "</license></content>"
        '<content url="/x/y/"><license><payment type="free"/></license></content>'
        "</rsl>",
        license_url=f"{_ORIGIN}/license.xml",
    )

    deep = terms_covering(licence, origin=_ORIGIN, url=f"{_ORIGIN}/x/y/z")
    top = terms_covering(licence, origin=_ORIGIN, url=f"{_ORIGIN}/other")

    assert set(deep.permits or ()) == {"usage:search", "usage:ai-train"}
    assert deep.permits is not None
    assert top.permits == ("usage:search",)
