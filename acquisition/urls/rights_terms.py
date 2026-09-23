"""RSL (Really Simple Licensing) terms — a publisher's own machine-readable
licence, read off ``robots.txt`` (SPR-10 task 4).

RSL (rslstandard.org) lets a site declare, in a form a crawler can read, what
it permits and what it wants in return: a ``License:`` directive in
``robots.txt`` points at an XML licence file whose ``<payment type="...">``
element names the price — ``free``, ``attribution``, ``subscription``,
``crawl``, ``inference``, ``purchase`` and so on. ``attribution`` and ``free``
are the literal signal Antiek is looking for: a publisher who has already
dropped the API payment gate. Reading the file costs nothing and needs no
membership, which is why this — and not a per-fetch marketplace — is the
bridge (``docs/decisions/tollbit-rejected-2026-09-20.md``).

This module is pure parsing: stdlib only, no I/O, no knowledge of hosts. The
fetch + per-host cache live in ``acquisition.urls.robots``; the fetcher
surfaces the parsed :class:`RightsTerms` on ``FetchedHtml.rights_terms``.

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

# The robots.txt directive name (matched case-insensitively). RSL also allows
# discovery via an HTTP ``Link`` header and an HTML ``<link rel="license">``;
# only the robots.txt directive is read here — it is the one channel that
# needs no page fetch and is the one the standard puts first.
LICENSE_DIRECTIVE = "license"

# Payment types that mean "no money changes hands for use": the publisher has
# already dropped the gate. Anything else in ``payment_types`` is a price.
NO_CHARGE_PAYMENT_TYPES: frozenset[str] = frozenset({"free", "attribution"})

TermsSource = Literal["rsl_license_xml", "robots_license_directive", "none"]


@dataclass(frozen=True)
class RightsTerms:
    """What a site declared about reuse of its content, as parsed from RSL.

    ``source`` says how much was actually read:

    - ``"rsl_license_xml"`` — the ``License:`` directive was present AND the
      licence XML was fetched and parsed; the term tuples are populated.
    - ``"robots_license_directive"`` — the directive was present but the XML
      could not be read (unreachable, non-2xx, oversized, cross-origin, or
      malformed); ``license_url`` is set and ``parse_error`` says why.
    - ``"none"`` — no directive; nothing declared. See :data:`NO_TERMS`.

    ``permits`` / ``prohibits`` entries are ``"<type>:<value>"`` strings
    (e.g. ``"usage:all"``, ``"usage:train-ai"``) — the RSL element's ``type``
    attribute joined to its text, lower-cased. ``payment_types`` are the
    ``<payment type="...">`` values, lower-cased, in document order.
    """

    source: TermsSource
    license_url: str | None = None
    content_url: str | None = None
    payment_types: tuple[str, ...] = ()
    permits: tuple[str, ...] = ()
    prohibits: tuple[str, ...] = ()
    standard_urls: tuple[str, ...] = ()
    parse_error: str | None = None

    @property
    def declared(self) -> bool:
        """True when the site published ANY licence signal (directive or XML)."""
        return self.source != "none"

    @property
    def no_charge(self) -> bool:
        """True when every declared payment type is ``free`` / ``attribution`` —
        the "gate already dropped" publisher this lane exists to find. False
        when nothing was parsed (no terms is not the same as free terms)."""
        return bool(self.payment_types) and all(
            p in NO_CHARGE_PAYMENT_TYPES for p in self.payment_types
        )

    @property
    def requires_payment(self) -> bool:
        """True when at least one declared payment type names a price."""
        return any(p not in NO_CHARGE_PAYMENT_TYPES for p in self.payment_types)


NO_TERMS = RightsTerms(source="none")


def parse_license_directive(robots_txt: str) -> str | None:
    """Return the value of the first ``License:`` directive in a robots.txt
    body, or ``None``. Comments (``#``) are stripped; the key is matched
    case-insensitively; a directive with an empty value is skipped.
    ``urllib.robotparser`` ignores the line as an unknown directive, so this
    is the only reader of it."""
    for raw in robots_txt.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        if key.strip().lower() != LICENSE_DIRECTIVE:
            continue
        value = value.strip()
        if value:
            return value
    return None


def _local_name(tag: str) -> str:
    """``{ns}permits`` -> ``permits``; namespace-agnostic element matching."""
    return tag.rsplit("}", 1)[-1].lower()


def _typed_value(el: ET.Element) -> str:
    kind = (el.get("type") or "").strip().lower()
    value = (el.text or "").strip().lower()
    return f"{kind}:{value}" if kind else value


def parse_rsl_xml(xml_text: str, *, license_url: str | None = None) -> RightsTerms:
    """Parse an RSL licence document into :class:`RightsTerms`.

    Never raises: a malformed document or a non-``<rsl>`` root yields a record
    with ``source="robots_license_directive"`` (the directive was real; the
    file was not usable) and ``parse_error`` set. Only the FIRST ``<content>``
    element's ``url`` is recorded; every ``<payment>``, ``<permits>``,
    ``<prohibits>`` and ``<standard>`` in the document is collected in order.
    """
    degraded_source: TermsSource = "robots_license_directive" if license_url else "none"
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        return RightsTerms(
            source=degraded_source,
            license_url=license_url,
            parse_error=f"{type(exc).__name__}: {exc}",
        )
    if _local_name(root.tag) != "rsl":
        return RightsTerms(
            source=degraded_source,
            license_url=license_url,
            parse_error=f"root element is <{_local_name(root.tag)}>, not <rsl>",
        )

    payment: list[str] = []
    permits: list[str] = []
    prohibits: list[str] = []
    standards: list[str] = []
    content_url: str | None = None
    for el in root.iter():
        name = _local_name(el.tag)
        if name == "content":
            if content_url is None:
                content_url = el.get("url")
        elif name == "payment":
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

    return RightsTerms(
        source="rsl_license_xml",
        license_url=license_url,
        content_url=content_url,
        payment_types=tuple(payment),
        permits=tuple(permits),
        prohibits=tuple(prohibits),
        standard_urls=tuple(standards),
    )


__all__ = [
    "LICENSE_DIRECTIVE",
    "NO_CHARGE_PAYMENT_TYPES",
    "NO_TERMS",
    "RSL_NAMESPACE",
    "RightsTerms",
    "TermsSource",
    "parse_license_directive",
    "parse_rsl_xml",
]
