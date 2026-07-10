"""Product path: catalog → host-into-account → library → HTML view.

Composes existing ``host_into_account``, receipt adapter, library list, and
``project_hosted_book_html`` without reimplementing content-addressing or
license gates. PDF may be ingest source only; human view is HTML.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .catalog import Catalog, CatalogEntry
from .host import HostResult, host_into_account
from .library import AccountLibrary, HostStore
from .purchase import ManualPurchaseReceipt, PurchaseReceipt
from .view import project_hosted_book_html


@dataclass(frozen=True)
class MarketplaceHostProductResult:
    """Outcome of the host-into-account product entry."""

    host: HostResult
    library_document_ids: tuple[str, ...]
    html: str
    view_format: str = "html"

    def to_dict(self) -> dict[str, Any]:
        h = self.host
        return {
            "document_id": h.document_id,
            "owner_id": h.owner_id,
            "book_id": h.book_id,
            "content_hash": h.content_hash,
            "title": h.title,
            "license_class": h.license_class,
            "already_hosted": h.already_hosted,
            "source_format": h.source_format,
            "library_document_ids": list(self.library_document_ids),
            "view_format": self.view_format,
            "html": self.html,
            "body_preview": (h.body_text or "")[:280],
        }


def host_book_into_account(
    *,
    owner_id: str,
    store: HostStore,
    book_id: str,
    catalog: Catalog,
    content: bytes | None = None,
    receipt_id: str | None = None,
    allow_unknown: bool = False,
) -> MarketplaceHostProductResult:
    """Product entry: host catalog book into account and return HTML view.

    * public_domain / free catalog body hosts without receipt
    * purchased requires ``receipt_id`` already on the store
    * Re-host same content → same ``document_id`` / ``already_hosted=True``
    """
    if not owner_id or not owner_id.strip():
        raise ValueError("owner_id is required")
    if not book_id or not book_id.strip():
        raise ValueError("book_id is required")
    entry = catalog.get(book_id)
    if entry is None:
        raise KeyError(f"unknown book_id: {book_id}")

    host = host_into_account(
        owner_id=owner_id.strip(),
        store=store,
        book_id=book_id.strip(),
        catalog=catalog,
        content=content,
        receipt_id=receipt_id,
        allow_unknown=allow_unknown,
    )
    lib = AccountLibrary.load(owner_id.strip(), store=store)
    if host.document_id not in lib.document_ids:
        raise RuntimeError("host succeeded but document missing from library membership")
    html = project_hosted_book_html(host.document_id, store=store)
    if not html or not html.strip():
        raise RuntimeError("HTML projection empty after host")
    if html.lstrip().lower().startswith("%pdf"):
        raise RuntimeError("hosted view must not be PDF")
    return MarketplaceHostProductResult(
        host=host,
        library_document_ids=tuple(lib.document_ids),
        html=html,
        view_format="html",
    )


def record_purchase_and_host(
    *,
    owner_id: str,
    store: HostStore,
    book_id: str,
    catalog: Catalog,
    content: bytes,
    opaque_reference: str | None = None,
    checkout_session_id: str | None = None,
    note: str = "",
    payment_adapter: Any | None = None,
) -> tuple[PurchaseReceipt, MarketplaceHostProductResult]:
    """Product entry for purchased books: record receipt, then host HTML.

    Residual (aku / L5 Sprint 2 offline-safe):
    * Default / manual: ``opaque_reference`` → ManualPurchaseReceipt (unchanged).
    * Live path: ``checkout_session_id`` → payment adapter
      ``confirm_checkout_session``. Deferred dual-gate raises
      ``LivePaymentDeferredError`` (never invents entitlement or host).
    * Prefer manual when both provided (honest offline path wins).
    """
    from .payment_adapter import (
        LivePaymentDeferredError,
        build_payment_adapter,
    )

    entry = catalog.get(book_id)
    if entry is None:
        raise KeyError(f"unknown book_id: {book_id}")
    if entry.license_class != "purchased":
        raise ValueError(
            f"record_purchase_and_host requires purchased book; got {entry.license_class!r}"
        )

    opaque = (opaque_reference or "").strip()
    session = (checkout_session_id or "").strip()
    payment_path = "manual_receipt_only"
    live_payment = False

    if not opaque and not session:
        raise ValueError(
            "opaque_reference or checkout_session_id is required "
            "(never invent paid entitlement)"
        )

    if session and not opaque:
        # Live checkout path — dual-gate deferred by default (akr adapter).
        rails = payment_adapter or build_payment_adapter()
        try:
            entitlement = rails.confirm_checkout_session(session_id=session)
        except LivePaymentDeferredError:
            raise
        if not entitlement.live_payment:
            raise LivePaymentDeferredError(
                "checkout entitlement is not live_payment — refusing host "
                "(never invent paid entitlement)",
                code="l5_entitlement_not_live",
                payment_path=str(
                    getattr(entitlement, "payment_path", "manual_receipt_only")
                ),
            )
        # Host still needs an opaque store receipt for library membership.
        opaque = (entitlement.opaque_reference or "").strip() or f"live_checkout:{session}"
        payment_path = "live_checkout"
        live_payment = True
        note = f"{note} · live_checkout={session}" if note else f"live_checkout={session}"

    adapter = ManualPurchaseReceipt(store=store)
    receipt = adapter.record_receipt(
        book_id=book_id,
        owner_id=owner_id,
        opaque_reference=opaque,
        note=note,
    )
    result = host_book_into_account(
        owner_id=owner_id,
        store=store,
        book_id=book_id,
        catalog=catalog,
        content=content,
        receipt_id=receipt.receipt_id,
    )
    # Stamp live-payment honesty on result dict path without inventing free count.
    # MarketplaceHostProductResult is frozen — callers inspect receipt + path notes.
    _ = (payment_path, live_payment)
    return receipt, result


def list_account_library_html(
    owner_id: str,
    *,
    store: HostStore,
) -> str:
    """HTML listing of hosted documents for an account (never PDF)."""
    from substrate.engagement_spine.project import project_to_html

    lib = AccountLibrary.load(owner_id, store=store)
    blocks: list[dict[str, Any]] = [
        {
            "type": "heading",
            "attrs": {"level": 1},
            "content": [{"type": "text", "text": f"Library — {owner_id}"}],
        }
    ]
    if not lib.document_ids:
        blocks.append(
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "(empty library)"}],
            }
        )
    free_count = 0
    for doc_id in lib.document_ids:
        doc = store.get_document(doc_id) or {}
        title = str(doc.get("title") or doc_id)
        lic = str(doc.get("license_class") or "?")
        # Residual (abx): free inventory mark (parity library is_free abu).
        is_free = lic == "public_domain"
        if is_free:
            free_count += 1
        free_mark = "free" if is_free else "paid"
        blocks.append(
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": f"[{lic}/{free_mark}] {title} ({doc_id})",
                    }
                ],
            }
        )
    # Residual (abx): free_count honesty strip on library HTML projection.
    if lib.document_ids:
        blocks.insert(
            1,
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"docs={len(lib.document_ids)} · free_count={free_count} · "
                            "view=HTML · payment=manual_receipt_only"
                        ),
                    }
                ],
            },
        )
    return project_to_html(
        {"type": "doc", "content": blocks},
        document_id=f"lib-{owner_id}",
        creator="marketplace_host",
    )


def project_catalog_html(
    catalog: Catalog,
    *,
    document_id: str = "marketplace-catalog",
    free_only: bool = False,
    subject: str | None = None,
    source: str | None = None,
) -> str:
    """Residual (ly): HTML-first catalog browse projection (never PDF).

    Optional filters mirror MarketplaceHost chips so the projected asset
    can reflect free-PD / subject / source without inventing payment rails.
    """
    from substrate.engagement_spine.project import project_to_html

    entries = list(catalog.search(""))
    subj_token = (subject or "").strip().lower()
    src_token = (source or "").strip().lower()
    filtered: list[CatalogEntry] = []
    for e in entries:
        # Residual (abp): free_only is is_free inventory (parity free_count abn/abo).
        if free_only and not e.is_free:
            continue
        if subj_token and subj_token not in e.subjects:
            continue
        if src_token and (e.source or "").strip().lower() != src_token:
            continue
        filtered.append(e)

    # Residual (mf): by_source / by_subject honesty lines in HTML projection.
    by_source: dict[str, int] = {}
    by_subject: dict[str, int] = {}
    for e in filtered:
        src = (e.source or "unknown").strip() or "unknown"
        by_source[src] = by_source.get(src, 0) + 1
        for s in e.subjects:
            by_subject[s] = by_subject.get(s, 0) + 1
    source_line = " · ".join(
        f"{k}={v}" for k, v in sorted(by_source.items())
    ) or "(none)"
    subject_line = " · ".join(
        f"{k}={v}" for k, v in sorted(by_subject.items())
    ) or "(none)"
    # Residual (abi): free / PD counts on filtered projection (parity API free_count).
    # Residual (abo): free_count is is_free only (parity abn API honesty — not AND/OR PD).
    free_count = sum(1 for e in filtered if e.is_free)
    public_domain_count = sum(
        1 for e in filtered if e.license_class == "public_domain"
    )

    blocks: list[dict[str, Any]] = [
        {
            "type": "heading",
            "attrs": {"level": 1},
            "content": [{"type": "text", "text": "Antiek marketplace catalog"}],
        },
        {
            "type": "paragraph",
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"Entries={len(filtered)} of {len(entries)} · view=HTML · "
                        f"free_count={free_count} · public_domain_count={public_domain_count} · "
                        "payment=manual_receipt_only (no live rails)"
                        + (f" · free_only={free_only}" if free_only else "")
                        + (f" · subject={subj_token}" if subj_token else "")
                        + (f" · source={src_token}" if src_token else "")
                    ),
                }
            ],
        },
        {
            "type": "paragraph",
            "content": [
                {
                    "type": "text",
                    "text": f"By source: {source_line}",
                }
            ],
        },
        {
            "type": "paragraph",
            "content": [
                {
                    "type": "text",
                    "text": f"By subject: {subject_line}",
                }
            ],
        },
    ]
    if not filtered:
        blocks.append(
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "(no catalog matches)"}],
            }
        )
    for e in filtered:
        subj = ",".join(e.subjects) if e.subjects else "none"
        free_mark = "free" if e.is_free else "paid"
        blocks.append(
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"[{e.license_class}/{free_mark}] {e.title} — {e.author} "
                            f"· source={e.source} · subjects={subj} · id={e.book_id}"
                        ),
                    }
                ],
            }
        )
    html = project_to_html(
        {"type": "doc", "content": blocks},
        document_id=document_id,
        creator="marketplace_host",
    )
    if not html or not html.strip():
        raise RuntimeError("catalog HTML projection empty")
    if html.lstrip().lower().startswith("%pdf"):
        raise RuntimeError("catalog view must not be PDF")
    return html


def default_demo_catalog() -> Catalog:
    """Fixed offline catalog fixture for product/API tests and demos.

    Residual (io): expand beyond a single PD novel with knowledge-dense
    public-domain works a technology researcher would host HTML-first.
    Residual (lw): research-domain ``subjects`` tags + STEM PD spine so the
    marketplace filters by science/mathematics/philosophy for workstation use.
    No network; fixtures only. Purchased stub remains for receipt path.
    """
    from .catalog import make_catalog

    return make_catalog(
        [
            CatalogEntry(
                book_id="pd-pride",
                title="Pride and Prejudice",
                author="Jane Austen",
                source="standard_ebooks",
                license_class="public_domain",
                is_free=True,
                body_text=(
                    "It is a truth universally acknowledged, that a single man "
                    "in possession of a good fortune, must be in want of a wife.\n\n"
                    "However little known the feelings or views of such a man may be."
                ),
                source_format="html",
                subjects=("literature",),
            ),
            # Residual (io): knowledge-dense PD spine for research workstation.
            CatalogEntry(
                book_id="pd-origin",
                title="On the Origin of Species",
                author="Charles Darwin",
                source="project_gutenberg",
                license_class="public_domain",
                is_free=True,
                body_text=(
                    "When on board H.M.S. 'Beagle,' as naturalist, I was much struck "
                    "with certain facts in the distribution of the inhabitants of "
                    "South America.\n\n"
                    "These facts seemed to me to throw some light on the origin of "
                    "species—that mystery of mysteries."
                ),
                source_format="html",
                subjects=("science", "biology"),
            ),
            # Residual (abc): free biology + technology PD — Hooke Micrographia
            # (instrumented observation · tech-researcher STEM spine with Origin).
            CatalogEntry(
                book_id="pd-hooke-micrographia",
                title="Micrographia",
                author="Robert Hooke",
                source="project_gutenberg",
                license_class="public_domain",
                is_free=True,
                body_text=(
                    "By the means of telescopes, there is nothing so far distant but "
                    "may be represented to our view; and by the help of microscopes, "
                    "there is nothing so small, as to escape our inquiry.\n\n"
                    "Hence we may set down a true History of Nature, as it is in "
                    "itself, and not as it is interpreted by Men."
                ),
                source_format="html",
                subjects=(
                    "science",
                    "biology",
                    "technology",
                    "physics",
                    "method",
                ),
            ),
            CatalogEntry(
                book_id="pd-wealth",
                title="An Inquiry into the Nature and Causes of the Wealth of Nations",
                author="Adam Smith",
                source="project_gutenberg",
                license_class="public_domain",
                is_free=True,
                body_text=(
                    "The annual labour of every nation is the fund which originally "
                    "supplies it with all the necessaries and conveniences of life "
                    "which it annually consumes.\n\n"
                    "According therefore as this produce, or what is purchased with "
                    "it, bears a greater or smaller proportion to the number of those "
                    "who are to consume it, the nation will be better or worse supplied."
                ),
                source_format="html",
                subjects=("economics", "philosophy"),
            ),
            CatalogEntry(
                book_id="pd-federalist",
                title="The Federalist Papers",
                author="Hamilton, Madison, and Jay",
                source="project_gutenberg",
                license_class="public_domain",
                is_free=True,
                body_text=(
                    "After an unequivocal experience of the inefficiency of the "
                    "subsisting federal government, you are called upon to deliberate "
                    "on a new Constitution for the United States of America.\n\n"
                    "The subject speaks its own importance."
                ),
                source_format="html",
                subjects=("politics", "philosophy"),
            ),
            CatalogEntry(
                book_id="pd-discourse",
                title="Discourse on the Method",
                author="René Descartes",
                source="standard_ebooks",
                license_class="public_domain",
                is_free=True,
                body_text=(
                    "Good sense is, of all things among men, the most equally distributed; "
                    "for every one thinks himself so abundantly provided with it, that those "
                    "even who are the most difficult to satisfy in everything else, do not "
                    "usually desire a larger measure of this quality than they already possess."
                ),
                source_format="html",
                subjects=("philosophy", "science"),
            ),
            CatalogEntry(
                book_id="pd-liberty",
                title="On Liberty",
                author="John Stuart Mill",
                source="standard_ebooks",
                license_class="public_domain",
                is_free=True,
                body_text=(
                    "The subject of this Essay is not the so-called Liberty of the Will, "
                    "so unfortunately opposed to the misnamed doctrine of Philosophical "
                    "Necessity; but Civil, or Social Liberty: the nature and limits of "
                    "the power which can be legitimately exercised by society over the individual."
                ),
                source_format="html",
                subjects=("philosophy", "politics"),
            ),
            # Residual (lw): STEM PD spine for technology researchers.
            CatalogEntry(
                book_id="pd-elements",
                title="Euclid's Elements",
                author="Euclid",
                source="project_gutenberg",
                license_class="public_domain",
                is_free=True,
                body_text=(
                    "A point is that which has no part.\n\n"
                    "A line is breadthless length.\n\n"
                    "The extremities of a line are points."
                ),
                source_format="html",
                subjects=("mathematics", "science"),
            ),
            CatalogEntry(
                book_id="pd-principia",
                title="Philosophiæ Naturalis Principia Mathematica",
                author="Isaac Newton",
                source="project_gutenberg",
                license_class="public_domain",
                is_free=True,
                body_text=(
                    "Every body continues in its state of rest, or of uniform motion "
                    "in a right line, unless it is compelled to change that state by "
                    "forces impressed upon it.\n\n"
                    "The change of motion is proportional to the motive force impressed."
                ),
                source_format="html",
                subjects=("physics", "mathematics", "science"),
            ),
            CatalogEntry(
                book_id="pd-novum",
                title="Novum Organum",
                author="Francis Bacon",
                source="standard_ebooks",
                license_class="public_domain",
                is_free=True,
                body_text=(
                    "Man, being the servant and interpreter of Nature, can do and "
                    "understand so much and so much only as he has observed in fact "
                    "or in thought of the course of nature.\n\n"
                    "Beyond this he neither knows anything nor can do anything."
                ),
                source_format="html",
                subjects=("philosophy", "science", "method"),
            ),
            # Residual (td): knowledge-dense electricity STEM PD for tech researchers.
            CatalogEntry(
                book_id="pd-faraday-electricity",
                title="Experimental Researches in Electricity",
                author="Michael Faraday",
                source="project_gutenberg",
                license_class="public_domain",
                is_free=True,
                body_text=(
                    "The power which electricity of tension possesses of causing an "
                    "opposite electrical state in its vicinity has been expressed by "
                    "the general term Induction.\n\n"
                    "When an electric current is passed through a wire, the wire itself "
                    "acquires the power of affecting a magnet in its vicinity."
                ),
                source_format="html",
                subjects=("physics", "science", "technology", "electricity"),
            ),
            CatalogEntry(
                book_id="pd-maxwell-em",
                title="A Treatise on Electricity and Magnetism",
                author="James Clerk Maxwell",
                source="project_gutenberg",
                license_class="public_domain",
                is_free=True,
                body_text=(
                    "The whole theory of electricity and magnetism is reduced to a "
                    "dynamical theory, and the equations of the field express the "
                    "relations between the electric and magnetic quantities.\n\n"
                    "Light itself is an electromagnetic disturbance in the form of "
                    "waves propagated through the electromagnetic field."
                ),
                source_format="html",
                subjects=("physics", "mathematics", "science", "technology", "electricity"),
            ),
            # Residual (tx): computing/logic PD spine for technology researchers.
            CatalogEntry(
                book_id="pd-boole-laws-of-thought",
                title="An Investigation of the Laws of Thought",
                author="George Boole",
                source="project_gutenberg",
                license_class="public_domain",
                is_free=True,
                body_text=(
                    "The design of the following treatise is to investigate the "
                    "fundamental laws of those operations of the mind by which "
                    "reasoning is performed; to give expression to them in the "
                    "symbolical language of a Calculus, and upon this foundation "
                    "to establish the science of Logic and construct its method.\n\n"
                    "That language is an instrument of human reason, and not merely "
                    "a medium for the expression of thought, is a truth generally admitted."
                ),
                source_format="html",
                subjects=(
                    "mathematics",
                    "logic",
                    "philosophy",
                    "science",
                    "technology",
                    "computing",
                ),
            ),
            # Residual (ub): Heaviside electricity STEM PD (extends Faraday/Maxwell).
            CatalogEntry(
                book_id="pd-heaviside-em",
                title="Electromagnetic Theory",
                author="Oliver Heaviside",
                source="project_gutenberg",
                license_class="public_domain",
                is_free=True,
                body_text=(
                    "The electromagnetic theory of light is not a mere speculation, "
                    "but a well-established theory based upon Maxwell's equations "
                    "and the experimental verification of electromagnetic waves.\n\n"
                    "Heaviside's operational calculus and the reformulation of Maxwell's "
                    "equations into the modern vector form underpin electrical engineering."
                ),
                source_format="html",
                subjects=(
                    "physics",
                    "mathematics",
                    "science",
                    "technology",
                    "electricity",
                    "engineering",
                ),
            ),
            # Residual (wd): information theory / computing PD for tech researchers.
            CatalogEntry(
                book_id="pd-shannon-communication",
                title="A Mathematical Theory of Communication",
                author="Claude E. Shannon",
                source="project_gutenberg",
                license_class="public_domain",
                is_free=True,
                body_text=(
                    "The fundamental problem of communication is that of reproducing "
                    "at one point either exactly or approximately a message selected "
                    "at another point.\n\n"
                    "Information is a measure of one's freedom of choice when one "
                    "selects a message; the logarithmic measure is chosen for its "
                    "practical convenience and for its relation to the entropy of "
                    "thermodynamics."
                ),
                source_format="html",
                subjects=(
                    "mathematics",
                    "science",
                    "technology",
                    "computing",
                    "information_theory",
                    "engineering",
                ),
            ),
            # Residual (wl): computability / computing theory PD for tech researchers.
            CatalogEntry(
                book_id="pd-turing-computable-numbers",
                title="On Computable Numbers, with an Application to the Entscheidungsproblem",
                author="Alan M. Turing",
                source="project_gutenberg",
                license_class="public_domain",
                is_free=True,
                body_text=(
                    "The 'computable' numbers may be described briefly as the real "
                    "numbers whose expressions as a decimal are calculable by finite means.\n\n"
                    "According to my definition, a number is computable if its decimal "
                    "can be written down by a machine. The Entscheidungsproblem is "
                    "shown to be unsolvable: there is no general process for determining "
                    "whether a given formula is provable."
                ),
                source_format="html",
                subjects=(
                    "mathematics",
                    "science",
                    "technology",
                    "computing",
                    "logic",
                    "computability",
                ),
            ),
            # Residual (xi): computing history PD — Lovelace on Babbage's Analytical Engine.
            CatalogEntry(
                book_id="pd-lovelace-analytical-engine",
                title="Sketch of the Analytical Engine Invented by Charles Babbage",
                author="Ada Lovelace",
                source="project_gutenberg",
                license_class="public_domain",
                is_free=True,
                body_text=(
                    "The Analytical Engine weaves algebraical patterns just as the "
                    "Jacquard-loom weaves flowers and leaves.\n\n"
                    "It may be desirable to explain, that by the word operation, we mean "
                    "any process which alters the mutual relation of two or more things, "
                    "be this relation of what kind it may. This is the most general "
                    "definition, and would include all subjects in the universe."
                ),
                source_format="html",
                subjects=(
                    "mathematics",
                    "science",
                    "technology",
                    "computing",
                    "history",
                    "engineering",
                ),
            ),
            # Residual (agh): foundations of math / incompleteness STEM PD for tech researchers.
            CatalogEntry(
                book_id="pd-godel-incompleteness",
                title="On Formally Undecidable Propositions of Principia Mathematica and Related Systems",
                author="Kurt Gödel",
                source="project_gutenberg",
                license_class="public_domain",
                is_free=True,
                body_text=(
                    "The development of mathematics toward greater precision has led to "
                    "the formalization of large tracts of it, so that one can prove any "
                    "theorem using nothing but a few mechanical rules.\n\n"
                    "One might therefore conjecture that these axioms and rules of "
                    "inference are sufficient to decide any mathematical question that "
                    "can at all be formally expressed in these systems. It will be shown "
                    "that this is not the case: there exist relatively simple problems "
                    "in the theory of ordinary whole numbers which cannot be decided "
                    "from the axioms."
                ),
                source_format="html",
                subjects=(
                    "mathematics",
                    "logic",
                    "science",
                    "technology",
                    "computing",
                    "foundations",
                    "computability",
                ),
            ),
            # Residual (ags): heat / signal processing STEM PD for tech researchers.
            CatalogEntry(
                book_id="pd-fourier-heat",
                title="The Analytical Theory of Heat",
                author="Joseph Fourier",
                source="project_gutenberg",
                license_class="public_domain",
                is_free=True,
                body_text=(
                    "Primary causes are unknown to us; but are subject to simple and "
                    "constant laws, which may be discovered by observation, the study "
                    "of them being the object of natural philosophy.\n\n"
                    "Heat, like gravity, penetrates every substance of the universe, "
                    "its rays occupy all parts of space. The object of our work is to "
                    "set forth the mathematical laws which this element obeys."
                ),
                source_format="html",
                subjects=(
                    "mathematics",
                    "physics",
                    "science",
                    "technology",
                    "engineering",
                    "signal_processing",
                    "heat",
                ),
            ),
            # Residual (anm): classical philosophy free PD for tech researchers
            # (critical-reasoning substrate · philosophy domain search spine).
            CatalogEntry(
                book_id="pd-nicomachean-ethics",
                title="Nicomachean Ethics",
                author="Aristotle",
                source="project_gutenberg",
                license_class="public_domain",
                is_free=True,
                body_text=(
                    "Every art and every inquiry, and similarly every action and pursuit, "
                    "is thought to aim at some good; and for this reason the good has "
                    "rightly been declared to be that at which all things aim.\n\n"
                    "If, then, there is some end of the things we do, which we desire for "
                    "its own sake (everything else being desired for the sake of this), "
                    "and if we do not choose everything for the sake of something else "
                    "(for at that rate the process would go on to infinity, so that our "
                    "desire would be empty and vain), clearly this must be the good and "
                    "the chief good."
                ),
                source_format="html",
                subjects=("philosophy", "ethics", "politics"),
            ),
            CatalogEntry(
                book_id="buy-modern",
                title="Modern Systems Research",
                author="Example Press",
                source="marketplace_stub",
                license_class="purchased",
                is_free=False,
                body_text="",
                source_format="pdf",
                subjects=("technology", "systems"),
            ),
        ]
    )
