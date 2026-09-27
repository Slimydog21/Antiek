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
licensed asset or collection (an RFC 9309 path pattern, RSL 1.0 s3.3). So
the document is parsed into one :class:`RightsTerms` per ``<content>``
(:class:`RslLicence`), never one blend of every element in the file. When
several scopes cover one page they are evaluated together (s3.1.1): the
most specific sets payment and permissions (conservatively combined on a
tie), and every covering scope's prohibitions and licence servers stay
(``acquisition.urls.robots.terms_covering``). A page no scope covers gets
``source="rsl_out_of_scope"``.

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
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

# The RSL XML namespace (RSL 1.0). Parsing is tolerant of an absent or
# different namespace: element LOCAL names are matched, so a licence file
# that omits ``xmlns`` still parses.
RSL_NAMESPACE = "https://rslstandard.org/rsl"

# Payment types that mean "no money changes hands for use": the publisher has
# already dropped the gate. Anything else in ``payment_types`` is a price.
NO_CHARGE_PAYMENT_TYPES: frozenset[str] = frozenset({"free", "attribution"})

# RSL 1.0 s3.4.1.1: the usage vocabulary's umbrella tokens and what each one
# covers. ``all`` is "any automated processing, including AI training and
# search"; ``ai-all`` explicitly includes ai-train, ai-input and ai-index.
# Every other token (and every other ``type``) covers only itself.
USAGE_UMBRELLAS: dict[str, tuple[str, ...]] = {
    "all": ("ai-all", "search"),
    "ai-all": ("ai-train", "ai-input", "ai-index"),
}

# The most <content> scopes one licence may declare. Each parsed scope is a
# record held per agent token in the policy cache and tried against every
# page, while a bare ``<content/>`` is ten bytes, so a 256 KiB licence could
# otherwise hold 26,000 of them and outweigh the whole cache (robots.py
# MAX_CACHED_ROBOTS_BYTES) by itself. Real licences name a handful of scopes
# and use wildcards for collections; one past this is recorded as unusable.
MAX_LICENCE_SCOPES = 1024

# The most characters of parsed terms (payment, permits, prohibits and
# standard values) one licence may produce, each value charged its length
# plus _TERM_OVERHEAD, as robots.py weighs it in the cache. Parsing can
# produce far more than the document holds: every value in an element's text
# becomes its own ``"<type>:<value>"`` entry, repeating the ``type``, and a
# ``<content>`` nested in another is read again for each enclosing scope. A
# licence past this is recorded as unusable, like one past
# MAX_LICENCE_SCOPES; the cap equals robots.py MAX_LICENSE_BYTES.
MAX_LICENCE_TERM_CHARS = 256 * 1024
_TERM_OVERHEAD = 8

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
      page's terms. ``license_url`` is set; the term tuples are empty and
      ``permits`` is ``None``.
    - ``"robots_license_directive"`` — the directive was present but the XML
      could not be read (unreachable, non-2xx, oversized, cross-origin, or
      malformed); ``license_url`` is set and ``parse_error`` says why.
    - ``"none"`` — no directive; nothing declared. See :data:`NO_TERMS`.

    ``permits`` / ``prohibits`` entries are ``"<type>:<value>"`` strings
    (e.g. ``"usage:all"``, ``"usage:ai-train"``), one per value: the RSL
    element's ``type`` attribute joined to each of the values its text lists
    (RSL 1.0 s3.5/s3.6: separated by spaces; commas are accepted too),
    lower-cased. How a page's terms are combined from the scopes covering it
    is ``acquisition.urls.robots.terms_covering``'s contract; whatever the
    combination, no usage in ``prohibits``, or covered by an umbrella token
    in it (:data:`USAGE_UMBRELLAS`), is left in ``permits`` (RSL 1.0 s3.1.1:
    the prohibition takes precedence and the usage is not licensed).

    ``permits`` is ``None`` when no ``<permits>`` element was declared: RSL
    makes the element optional (s3.5), and without one only ``prohibits``
    restricts use. A tuple is a whitelist: an entry not in it, nor under an
    umbrella in it, is not licensed, and ``()`` licenses nothing (an empty
    ``<permits>``, or a combination of scopes that left nothing permitted).
    The whitelist is read across ``type`` values as one set, which is
    narrower than reading each type on its own and so never licenses more
    than the publisher did (s3.1.1, conservative).

    ``payment_types`` are the ``<payment type="...">`` values, lower-cased,
    in document order. ``license_servers`` are the ``<content server="...">``
    values: RSL License Servers a client MUST obtain a licence from before
    access, "even if the license type is ``free``" (RSL 1.0 s3.3).
    """

    source: TermsSource
    license_url: str | None = None
    content_url: str | None = None
    payment_types: tuple[str, ...] = ()
    permits: tuple[str, ...] | None = None
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


class _TermsTooLarge(Exception):
    """A licence's parsed terms would exceed :data:`MAX_LICENCE_TERM_CHARS`."""


class _TermBudget:
    """The characters of parsed terms one licence may still produce."""

    __slots__ = ("remaining",)

    def __init__(self, total: int) -> None:
        self.remaining = total

    def take(self, kind: str, value: str) -> str:
        """``"<kind>:<value>"`` (``value`` alone without a kind), charged
        before it is built."""
        self.remaining -= len(kind) + 1 + len(value) + _TERM_OVERHEAD
        if self.remaining < 0:
            raise _TermsTooLarge
        return f"{kind}:{value}" if kind else value


def _typed_values(el: ET.Element, budget: _TermBudget) -> list[str]:
    """One ``"<type>:<value>"`` entry per value a permits/prohibits element
    lists (RSL 1.0 s3.5/s3.6: "separated by one or more spaces"; commas are
    accepted as well)."""
    kind = (el.get("type") or "").strip().lower()
    values = (el.text or "").replace(",", " ").lower().split()
    return [budget.take(kind, value) for value in values]


def _usage(entry: str) -> str | None:
    """The usage token of a ``"usage:<token>"`` entry, else None."""
    kind, sep, value = entry.partition(":")
    return value if sep and kind == "usage" else None


def _covering_umbrellas(token: str) -> set[str]:
    """``token`` and every umbrella usage that covers it."""
    found = {token}
    grew = True
    while grew:
        wider = {u for u, children in USAGE_UMBRELLAS.items() if found & set(children)}
        grew = not wider <= found
        found |= wider
    return found


class _Terms:
    """A set of permits or prohibits entries, read with the usage umbrellas
    of RSL 1.0 s3.4.1.1. Built once per set, so each question about one
    entry costs the same however many entries the set holds."""

    __slots__ = ("entries", "reached")

    def __init__(self, entries: tuple[str, ...]) -> None:
        self.entries = set(entries)
        # Every usage the set names, and every umbrella over one it names.
        self.reached: set[str] = set()
        for entry in self.entries:
            token = _usage(entry)
            if token is not None:
                self.reached |= _covering_umbrellas(token)

    def covers(self, entry: str) -> bool:
        """Whether the set names ``entry`` itself or, for a usage, an
        umbrella usage covering it."""
        if entry in self.entries:
            return True
        token = _usage(entry)
        return token is not None and any(
            f"usage:{u}" in self.entries for u in _covering_umbrellas(token)
        )

    def names_part_of(self, entry: str) -> bool:
        """Whether ``entry`` is an umbrella usage and the set names a usage
        it covers (so ``entry`` holds for part of what it covers only)."""
        token = _usage(entry)
        return token in USAGE_UMBRELLAS and token in self.reached


def _narrowed(
    entries: tuple[str, ...], keep: Callable[[str], bool], drop: Callable[[str], bool]
) -> tuple[str, ...]:
    """``entries`` with each one removed when ``drop`` says so, kept whole
    when ``keep`` says so, and otherwise, for an umbrella usage, replaced by
    its children judged the same way (RSL 1.0 s3.4.1.1)."""
    out: list[str] = []

    def visit(entry: str) -> None:
        if drop(entry):
            return
        if keep(entry):
            out.append(entry)
            return
        for child in USAGE_UMBRELLAS.get(_usage(entry) or "", ()):
            visit(f"usage:{child}")

    for entry in dict.fromkeys(entries):
        visit(entry)
    return tuple(dict.fromkeys(out))


def permits_without(
    permits: tuple[str, ...] | None, prohibits: tuple[str, ...]
) -> tuple[str, ...] | None:
    """``permits`` minus every usage ``prohibits`` names or covers (RSL 1.0
    s3.1.1: the prohibition takes precedence). A permitted umbrella of which
    only part is prohibited is split into the children still licensed, so
    ``usage:all`` minus ``usage:ai-train`` is ai-input, ai-index and search.
    A whitelist that loses every entry is ``()``, licensing nothing; no
    whitelist (``None``) stays ``None``, since ``prohibits`` alone already
    carries the restriction."""
    if permits is None:
        return None
    banned = _Terms(prohibits)
    return _narrowed(
        permits,
        keep=lambda entry: not banned.names_part_of(entry),
        drop=banned.covers,
    )


def permits_in_both(
    first: tuple[str, ...] | None, second: tuple[str, ...] | None
) -> tuple[str, ...] | None:
    """What ``first`` and ``second`` both permit, umbrella usages included:
    ``usage:all`` and ``usage:search`` share only ``usage:search``, and
    disjoint whitelists share ``()``, licensing nothing. ``None`` (no
    whitelist declared) restricts nothing, so it is the identity."""
    if first is None:
        return second
    if second is None:
        return first
    other = _Terms(second)
    return _narrowed(
        first,
        keep=other.covers,
        drop=lambda entry: not other.covers(entry) and not other.names_part_of(entry),
    )


def _scope_terms(
    content: ET.Element, *, license_url: str | None, budget: _TermBudget
) -> RightsTerms:
    """The terms declared inside one ``<content>`` element, each value
    charged to ``budget``."""
    payment: list[str] = []
    permits: list[str] = []
    permits_declared = False
    prohibits: list[str] = []
    standards: list[str] = []
    server = (content.get("server") or "").strip()
    for el in content.iter():
        name = _local_name(el.tag)
        if name == "payment":
            kind = (el.get("type") or "").strip().lower()
            if kind:
                payment.append(budget.take("", kind))
        elif name == "permits":
            permits_declared = True
            permits.extend(_typed_values(el, budget))
        elif name == "prohibits":
            prohibits.extend(_typed_values(el, budget))
        elif name == "standard":
            text = (el.text or "").strip()
            if text:
                standards.append(budget.take("", text))
    # RSL 1.0 s3.7: "If omitted, the license is assumed to be free." A
    # <license> with no <payment> is a free licence, not an unknown one.
    for lic in content.iter():
        if _local_name(lic.tag) != "license":
            continue
        if not any(_local_name(d.tag) == "payment" for d in lic.iter() if d is not lic):
            payment.append(budget.take("", "free"))
    return RightsTerms(
        source="rsl_license_xml",
        license_url=license_url,
        content_url=content.get("url"),
        payment_types=tuple(payment),
        permits=tuple(permits) if permits_declared else None,
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
    ``url`` is kept with ``content_url=None`` and covers no page, as does
    one with ``url=""``, which the robots.txt association gives no scope
    (RSL 1.0 s3.3.1, s4.4). A document declaring more than
    :data:`MAX_LICENCE_SCOPES` scopes, or whose parsed terms would exceed
    :data:`MAX_LICENCE_TERM_CHARS`, is degraded the same way.
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
    contents = [el for el in root.iter() if _local_name(el.tag) == "content"]
    too_large: str | None = None
    scopes: tuple[RightsTerms, ...] = ()
    if len(contents) > MAX_LICENCE_SCOPES:
        too_large = f"licence declares {len(contents)} <content> scopes (> {MAX_LICENCE_SCOPES})"
    else:
        budget = _TermBudget(MAX_LICENCE_TERM_CHARS)
        try:
            scopes = tuple(
                _scope_terms(el, license_url=license_url, budget=budget) for el in contents
            )
        except _TermsTooLarge:
            too_large = f"licence terms exceed {MAX_LICENCE_TERM_CHARS} characters once parsed"
    if too_large is not None:
        return RslLicence(
            license_url=license_url,
            unscoped=RightsTerms(
                source=degraded_source,
                license_url=license_url,
                parse_error=f"{too_large}; not parsed",
            ),
        )
    return RslLicence(license_url=license_url, scopes=scopes)


__all__ = [
    "MAX_LICENCE_SCOPES",
    "MAX_LICENCE_TERM_CHARS",
    "NO_CHARGE_PAYMENT_TYPES",
    "NO_LICENCE",
    "NO_TERMS",
    "RSL_NAMESPACE",
    "RightsTerms",
    "RslLicence",
    "TermsSource",
    "USAGE_UMBRELLAS",
    "parse_rsl_licence",
    "permits_in_both",
    "permits_without",
]
