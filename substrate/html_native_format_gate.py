r"""HTML-native format gate — is every viewed asset served as HTML, never PDF/EPUB/raw?

Operator vision (ask #6): *"I want to stay true to my HTML vision (as it is so easily
controllable with coding agents) and move away from PDFs so make sure every information asset
(including books and human-viewable research output) that gets viewed is in HTML (I have
reasoned on this and have specs on this)."* This module is that invariant as falsifiable code —
the decision-independent atom that the view path consults to confirm an asset reaches the viewer
as HTML, regardless of whether the asset is a book, a paper, or a human-viewable research output.
It catches two distinct violations of the HTML-native vision:

  (a) **Direct non-HTML serving** — a PDF/EPUB/raw-binary asset handed to the viewer without
      being ported to HTML (the explicit "move away from PDFs" break).
  (b) **Unprovenanced HTML** — an asset whose SOURCE was non-HTML (PDF/EPUB) now served as HTML
      but with NO record of the port that produced it. This is the integrity gap: HTML served
      without port provenance is suspect — either the port happened unrecorded (a provenance
      hole) or the HTML was fabricated. The honest reading is "claims HTML, no port evidence,"
      distinct from a clean ported asset.

**Genuinely distinct from the books surface (load-bearing):**

* ``substrate/books/servability`` (on main): the RIGHTS gate — *given a book's license state,
  may Antiek serve its full text?* It derives servable/gated from ``content_class`` +
  ``taken_down`` (Hachette v. IA / Bartz v. Anthropic lineage). It answers a LEGAL question
  (may-we-serve). THIS answers a FORMAT question (is-it-served-AS-html). A work can be fully
  rights-servable (public domain, not taken down) yet format-violating (served as a raw PDF) —
  servability says "yes you may serve it," the format gate says "but not as a PDF." Different
  axis, different question; both gates must pass for an asset to reach the HTML viewer.
* ``sanitize_book_html`` (#729, on main): the XSS/allowlist reconstruction that makes served
  HTML *safe*. THIS runs BEFORE that — it confirms the asset is HTML at all (sanitize assumes
  HTML input; a PDF never reaches it on the HTML-native path). Format gate is the format
  invariant; sanitize is the safety invariant.
* ``substrate/book_provenance_chain`` (#2035, off main): the acquisition receipt-chain
  integrity (source->authorization->ingest->sanitize->host). The chain's SANITIZE stage is where
  the port happens; THIS is the standalone format check the view path runs to confirm the host
  stage actually delivered HTML. A book can have an intact chain yet be served as PDF if the
  host path regressed — the chain verifies the process, the format gate verifies the bytes.

**The verification (hard to vary).**

An asset is described by three pure fields (the route/view layer supplies these from the asset's
stored metadata, no I/O):

  * ``source_format`` — the format the asset ORIGINALLY arrived in (``html`` / ``pdf`` / ``epub``
    / ``mobi`` / ``docx`` / ``unknown``).
  * ``serve_format`` — the format the view path is DELIVERING to the viewer (``html`` / ``pdf`` /
    ``epub`` / ``mobi`` / ``raw_binary`` / ``unknown``).
  * ``port_recorded`` — whether a port provenance exists (an html output with a recorded
    source->html port, e.g. the sanitize stage of the acquisition chain, or the EPUB->HTML
    projection). Bool; ``None`` when uncheckable.

The gate folds these into one verdict:

* ``serve_format != html`` (and not unknown) -> ``non_html_served`` (VIOLATION — the explicit
  ask-#6 break; a PDF/EPUB/raw asset reached the viewer). The offending serve_format is carried.
* ``serve_format == html`` AND ``source_format == html`` -> ``html_native`` (cleanest — source
  was already HTML, no port needed, served HTML).
* ``serve_format == html`` AND ``source_format`` is non-HTML AND ``port_recorded`` is True ->
  ``ported_to_html`` (clean — a real port produced the HTML, provenance exists).
* ``serve_format == html`` AND ``source_format`` is non-HTML AND ``port_recorded`` is False ->
  ``unported_html_served`` (integrity gap — HTML served without port provenance; suspect).
* ``serve_format == unknown`` -> ``unknown`` (cannot verify the format; defer, never fabricate).
* ``serve_format == html`` AND ``source_format`` is non-HTML AND ``port_recorded is None`` ->
  ``unknown`` (the port check is uncheckable, so the clean-vs-suspect distinction cannot be
  resolved — honest unknown, not a fabricated clean verdict).

**``html_native``** (the end-to-end fold): ``True`` only for ``html_native`` or
``ported_to_html`` (clean states); ``False`` for ``non_html_served`` / ``unported_html_served``
(violations); ``None`` for ``unknown`` (unverifiable). Distinct honest states never collapse.

**Key properties (load-bearing):**

* The gate VERIFIES, it does not transform. ``authority = "advisory"`` — it never re-ports,
  never converts, never serves. It reports the verdict; the view layer refuses to render on a
  ``False`` verdict (the operator's HTML vision enforced as a render-time check). Re-running on
  identical metadata reproduces the identical verdict (defensibility).
* ``non_html_served`` and ``unported_html_served`` are TWO distinct violations that never
  collapse: the first is "wrong format served" (the PDF break), the second is "right format,
  missing provenance" (the integrity gap). Both fail ``html_native``, but for different reasons
  the operator can read and act on.
* Unknowns surface as ``None``, never fabricated. ``serve_format == unknown`` and
  ``port_recorded is None`` both yield honest ``unknown`` rather than guessing clean or dirty.
* The format vocabulary is a documented set; an unknown format string is flagged
  ``non_html_served`` ONLY if it is the SERVE format (a served format we don't recognize is
  treated as a non-HTML serve — conservative, because an unrecognized serve format is NOT html),
  but an unrecognized SOURCE format is carried as ``unknown`` source (a book whose origin format
  we can't classify is not a violation in itself — only what reaches the viewer matters).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "KNOWN_FORMATS",
    "HTML_FORMAT",
    "AssetFormatDescriptor",
    "HtmlNativeFormatReport",
    "HtmlNativeFormatError",
    "verify_html_native_format",
]

# The canonical format vocabulary. A format outside this set is "unknown" — but
# unknown is interpreted differently for source (deferred) vs serve (conservative
# non-html) per the module docstring. HTML is the only format the view path may
# deliver on the HTML-native path.
HTML_FORMAT = "html"
KNOWN_FORMATS: frozenset[str] = frozenset(
    {"html", "pdf", "epub", "mobi", "docx", "raw_binary"}
)

# Descriptive verdict tokens — stable strings the view layer + tests key off.
VERDICT_HTML_NATIVE = "html_native"
VERDICT_PORTED_TO_HTML = "ported_to_html"
VERDICT_UNPORTED_HTML_SERVED = "unported_html_served"
VERDICT_NON_HTML_SERVED = "non_html_served"
VERDICT_UNKNOWN = "unknown"


@dataclass(frozen=True)
class AssetFormatDescriptor:
    """One asset's format metadata — the pure inputs the gate verifies against.
    Supplied by the route/view layer from stored asset metadata (no I/O here)."""

    asset_id: str
    source_format: str
    serve_format: str
    port_recorded: bool | None


@dataclass(frozen=True)
class HtmlNativeFormatReport:
    """The reproducible HTML-native verdict for one asset. ``html_native`` is the
    end-to-end fold: True only for clean states, False for violations, None when
    unverifiable. ``violation`` names the break (None when clean or unknown)."""

    asset_id: str
    source_format: str
    serve_format: str
    port_recorded: bool | None
    verdict: str
    html_native: bool | None
    violation: str | None
    notes: tuple[str, ...] = ()
    authority: str = "advisory"


class HtmlNativeFormatError(ValueError):
    """Raised when a descriptor is malformed (empty asset_id). A format string
    outside KNOWN_FORMATS is NOT an error — it is interpreted per the module
    docstring (unknown source deferred, unknown serve treated as non-html)."""


def _is_html(fmt: str) -> bool:
    return fmt == HTML_FORMAT


def _verdict_for(descriptor: AssetFormatDescriptor) -> tuple[str, bool | None, str | None]:
    """Derive (verdict, html_native, violation) from the descriptor's shape. The
    five honest states never collapse; the conservative reading of an unrecognized
    SERVE format is non_html_served (it is not html)."""
    source, serve, port = descriptor.source_format, descriptor.serve_format, descriptor.port_recorded

    if _is_html(serve):
        if _is_html(source):
            return VERDICT_HTML_NATIVE, True, None
        # non-html source served as html — clean only if the port is recorded.
        if port is True:
            return VERDICT_PORTED_TO_HTML, True, None
        if port is False:
            return VERDICT_UNPORTED_HTML_SERVED, False, VERDICT_UNPORTED_HTML_SERVED
        return VERDICT_UNKNOWN, None, None

    # serve is not html
    if serve == "unknown":
        return VERDICT_UNKNOWN, None, None
    # a known non-html serve format (pdf/epub/mobi/docx/raw_binary) OR an
    # unrecognized serve format (conservatively non-html — not html) is a violation.
    return VERDICT_NON_HTML_SERVED, False, VERDICT_NON_HTML_SERVED


def verify_html_native_format(
    descriptor: AssetFormatDescriptor,
) -> HtmlNativeFormatReport:
    """Verify one asset's HTML-native format invariant (ask #6).

    Returns a :class:`HtmlNativeFormatReport` with the verdict + end-to-end
    ``html_native`` fold. The view layer refuses to render on a ``False`` verdict.
    See the module docstring for the full state semantics.

    A malformed descriptor (empty ``asset_id``) raises
    :class:`HtmlNativeFormatError`.
    """
    if not descriptor.asset_id:
        raise HtmlNativeFormatError("AssetFormatDescriptor.asset_id must be non-empty")

    verdict, html_native, violation = _verdict_for(descriptor)

    notes: list[str] = []
    if descriptor.serve_format not in KNOWN_FORMATS and descriptor.serve_format != "unknown":
        notes.append(
            f"serve_format {descriptor.serve_format!r} is not in the known vocabulary "
            f"({sorted(KNOWN_FORMATS)}) — treated conservatively as non-html"
        )
    if descriptor.source_format not in KNOWN_FORMATS and descriptor.source_format != "unknown":
        notes.append(
            f"source_format {descriptor.source_format!r} is not in the known vocabulary "
            f"({sorted(KNOWN_FORMATS)}) — carried as an unrecognized origin"
        )

    if verdict == VERDICT_NON_HTML_SERVED:
        notes.append(
            f"asset served as {descriptor.serve_format!r} (not html) — direct violation of "
            "the HTML-native vision (ask #6); the view layer must refuse to render"
        )
    elif verdict == VERDICT_UNPORTED_HTML_SERVED:
        notes.append(
            "asset served as html with a non-html source but NO recorded port provenance — "
            "integrity gap (html without provenance is suspect, not a clean port)"
        )
    elif verdict == VERDICT_PORTED_TO_HTML:
        notes.append(
            f"asset ported {descriptor.source_format!r} -> html with recorded provenance — "
            "the clean acquisition/reading port path"
        )
    elif verdict == VERDICT_HTML_NATIVE:
        notes.append("asset is html-native (source html, served html) — cleanest path")
    else:  # unknown
        if descriptor.serve_format == "unknown":
            notes.append("serve_format unknown — cannot verify the HTML-native invariant")
        elif descriptor.port_recorded is None:
            notes.append(
                "port_recorded is None with a non-html source served as html — cannot "
                "resolve clean port vs suspect unported (honest unknown)"
            )

    return HtmlNativeFormatReport(
        asset_id=descriptor.asset_id,
        source_format=descriptor.source_format,
        serve_format=descriptor.serve_format,
        port_recorded=descriptor.port_recorded,
        verdict=verdict,
        html_native=html_native,
        violation=violation,
        notes=tuple(notes),
    )


def verify_html_native_batch(
    descriptors: Sequence[AssetFormatDescriptor],
) -> tuple[HtmlNativeFormatReport, ...]:
    """Verify a batch of assets and return per-asset reports in input order.

    Convenience for the view layer that checks a library/listing at once. The
    batch is never aggregated into a single pass/fail here — the caller decides
    policy (e.g. "render all clean, quarantine all violations"); this returns the
    per-asset evidence so that decision is auditable. Re-runs reproduce the order.
    """
    return tuple(verify_html_native_format(descriptor) for descriptor in descriptors)
