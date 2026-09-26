"""RSL (Really Simple Licensing) terms — a publisher's own machine-readable
licence. The robots.txt ``License:`` directive is read per user-agent group by
:func:`acquisition.urls.robots.select_license`; this module parses the licence
XML that directive selects (SPR-10 task 4).

RSL (rslstandard.org) lets a site declare, in a form a crawler can read, what
it permits and what it wants in return: a ``License:`` directive in
``robots.txt`` points at an XML licence file whose ``<payment type="...">``
element names the price — ``free``, ``attribution``, ``subscription``,
``crawl``, ``inference``, ``purchase`` and so on. ``attribution`` and ``free``
are the literal signal Antiek is looking for: a publisher who has already
dropped the API payment gate — unless the ``<content>`` names a licence
server, in which case a client must still obtain a licence token from it
first (RSL 1.0 s3.3, s3.7). Reading the file costs nothing and needs no
membership, which is why this — and not a per-fetch marketplace — is the
bridge (``docs/decisions/tollbit-rejected-2026-09-20.md``).

A licence document names its scope: each ``<content url>`` element is the
licensed asset or collection (an RFC 9309 path pattern, RSL 1.0 s3.3), and
when several apply to one page the most specific one decides (s3.1.1). So
the document is parsed into one :class:`RightsTerms` per ``<content>``
(:class:`RslLicence`), never one blend of every element in the file, and a
page gets the terms of the scope that covers it, or
``source="rsl_out_of_scope"`` when none does.

This module is pure parsing: stdlib only, no I/O, no knowledge of hosts. The
fetch, the per-origin policy cache and the scope matching (which reuses the
robots.txt path matcher) live in ``acquisition.urls.robots``; the fetcher
surfaces the terms selected for the page's final URL on
``FetchedHtml.rights_terms``.

What the record is NOT (intellectual honesty): a rights *decision*. The
substrate's deny-by-default gates (``substrate.rights``, content_class) are
untouched by anything parsed here. ``RightsTerms`` is provenance — what the
publisher said — captured at fetch time so a later rights call can cite it.
A parse failure is recorded on the record (``parse_error``), never raised,
because a broken licence file must not block ingest any more than a missing
``robots.txt`` does.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Literal

# The RSL XML namespace (RSL 1.0). Parsing is tolerant of an absent or
# different namespace: element LOCAL names are matched, so a licence file
# that omits ``xmlns`` still parses.
RSL_NAMESPACE = "https://rslstandard.org/rsl"

# Payment types that mean "no money changes hands for use": the publisher has
# already dropped the gate. Anything else in ``payment_types`` is a price.
NO_CHARGE_PAYMENT_TYPES: frozenset[str] = frozenset({"free", "attribution"})

TermsSource = Literal[
    "rsl_license_xml", "rsl_out_of_scope", "robots_license_directive", "none"
]


@dataclass(frozen=True)
class RightsTerms:
    """What a site declared about reuse of its content, as parsed from RSL.

    ``source`` says how much was actually read:

    - ``"rsl_license_xml"`` — the ``License:`` directive was present, the
      licence XML was fetched and parsed, and the ``<content>`` scope named
      in ``content_url`` covers the page; the term tuples are that scope's.
    - ``"rsl_out_of_scope"`` — the licence XML was parsed, but none of its
      ``<content>`` scopes covers the page: nothing is known about this
      page's terms. ``license_url`` is set; the term tuples are empty.
    - ``"robots_license_directive"`` — the directive was present but the XML
      could not be read (unreachable, non-2xx, oversized, cross-origin, or
      malformed); ``license_url`` is set and ``parse_error`` says why.
    - ``"none"`` — no directive; nothing declared. See :data:`NO_TERMS`.

    ``permits`` / ``prohibits`` entries are ``"<type>:<value>"`` strings
    (e.g. ``"usage:all"``, ``"usage:train-ai"``) — the RSL element's ``type``
    attribute joined to its text, lower-cased. ``payment_types`` are the
    ``<payment type="...">`` values, lower-cased, in document order.
    ``license_servers`` are the ``<content server="...">`` values: RSL
    License Servers a client MUST obtain a licence from before access, "even
    if the license type is ``free``" (RSL 1.0 s3.3).
    """

    source: TermsSource
    license_url: str | None = None
    content_url: str | None = None
    payment_types: tuple[str, ...] = ()
    permits: tuple[str, ...] = ()
    prohibits: tuple[str, ...] = ()
    standard_urls: tuple[str, ...] = ()
    license_servers: tuple[str, ...] = ()
    parse_error: str | None = None

    @property
    def declared(self) -> bool:
        """True when the site published ANY licence signal (directive or XML)."""
        return self.source != "none"

    @property
    def token_required(self) -> bool:
        """True when a licence server is declared: a token must be obtained
        from it before access, whatever the payment type (RSL 1.0 s3.7)."""
        return bool(self.license_servers)

    @property
    def no_charge(self) -> bool:
        """True when every declared payment type is ``free`` / ``attribution``
        and no licence server stands in front of the content — the "gate
        already dropped" publisher this lane exists to find. False when
        nothing was parsed (no terms is not the same as free terms), and False
        for a free licence that still needs a server-issued token."""
        return (
            bool(self.payment_types)
            and all(p in NO_CHARGE_PAYMENT_TYPES for p in self.payment_types)
            and not self.token_required
        )

    @property
    def requires_payment(self) -> bool:
        """True when at least one declared payment type names a price."""
        return any(p not in NO_CHARGE_PAYMENT_TYPES for p in self.payment_types)


NO_TERMS = RightsTerms(source="none")


@dataclass(frozen=True)
class RslLicence:
    """One parsed licence document, before a page is matched against it.

    ``scopes`` holds one :class:`RightsTerms` per ``<content>`` element, in
    document order, each carrying its own ``content_url`` and only the terms
    declared inside that element. ``unscoped`` is set instead when the answer
    is the same for every page: :data:`NO_TERMS` when no licence was
    declared, or a degraded record (``parse_error`` set) when the declared
    licence could not be read. Choosing a scope for a URL is
    ``acquisition.urls.robots``' job."""

    license_url: str | None
    scopes: tuple[RightsTerms, ...] = ()
    unscoped: RightsTerms | None = None


NO_LICENCE = RslLicence(license_url=None, unscoped=NO_TERMS)


def _local_name(tag: str) -> str:
    """``{ns}permits`` -> ``permits``; namespace-agnostic element matching."""
    return tag.rsplit("}", 1)[-1].lower()


def _typed_value(el: ET.Element) -> str:
    kind = (el.get("type") or "").strip().lower()
    value = (el.text or "").strip().lower()
    return f"{kind}:{value}" if kind else value


def _scope_terms(
    content: ET.Element, *, license_url: str | None
) -> RightsTerms:
    """The terms declared inside one ``<content>`` element."""
    payment: list[str] = []
    permits: list[str] = []
    prohibits: list[str] = []
    standards: list[str] = []
    server = (content.get("server") or "").strip()
    for el in content.iter():
        name = _local_name(el.tag)
        if name == "payment":
            kind = (el.get("type") or "").strip().lower()
            if kind:
                payment.append(kind)
        elif name == "permits":
            permits.append(_typed_value(el))
        elif name == "prohibits":
            prohibits.append(_typed_value(el))
        elif name == "standard":
            text = (el.text or "").strip()
            if text:
                standards.append(text)
    # RSL 1.0 s3.7: "If omitted, the license is assumed to be free." A
    # <license> with no <payment> is a free licence, not an unknown one.
    for lic in content.iter():
        if _local_name(lic.tag) != "license":
            continue
        if not any(_local_name(d.tag) == "payment" for d in lic.iter() if d is not lic):
            payment.append("free")
    return RightsTerms(
        source="rsl_license_xml",
        license_url=license_url,
        content_url=content.get("url"),
        payment_types=tuple(payment),
        permits=tuple(permits),
        prohibits=tuple(prohibits),
        standard_urls=tuple(standards),
        license_servers=(server,) if server else (),
    )


def parse_rsl_licence(xml_text: str, *, license_url: str | None = None) -> RslLicence:
    """Parse an RSL licence document into one :class:`RightsTerms` per
    ``<content>`` scope.

    Never raises: a malformed document or a non-``<rsl>`` root yields an
    :class:`RslLicence` whose ``unscoped`` record has
    ``source="robots_license_directive"`` (the directive was real; the file
    was not usable) and ``parse_error`` set. Terms outside any ``<content>``
    element belong to no scope and are ignored; a ``<content>`` without a
    ``url`` is kept with ``content_url=None`` and covers no page.
    """
    degraded_source: TermsSource = "robots_license_directive" if license_url else "none"
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        return RslLicence(
            license_url=license_url,
            unscoped=RightsTerms(
                source=degraded_source,
                license_url=license_url,
                parse_error=f"{type(exc).__name__}: {exc}",
            ),
        )
    if _local_name(root.tag) != "rsl":
        return RslLicence(
            license_url=license_url,
            unscoped=RightsTerms(
                source=degraded_source,
                license_url=license_url,
                parse_error=f"root element is <{_local_name(root.tag)}>, not <rsl>",
            ),
        )
    return RslLicence(
        license_url=license_url,
        scopes=tuple(
            _scope_terms(el, license_url=license_url)
            for el in root.iter()
            if _local_name(el.tag) == "content"
        ),
    )


__all__ = [
    "NO_CHARGE_PAYMENT_TYPES",
    "NO_LICENCE",
    "NO_TERMS",
    "RSL_NAMESPACE",
    "RightsTerms",
    "RslLicence",
    "TermsSource",
    "parse_rsl_licence",
]
