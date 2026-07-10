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
    opaque_reference: str,
    content: bytes,
    note: str = "",
) -> tuple[PurchaseReceipt, MarketplaceHostProductResult]:
    """Product entry for purchased books: record manual receipt, then host.

    No Stripe — opaque order/receipt token only.
    """
    entry = catalog.get(book_id)
    if entry is None:
        raise KeyError(f"unknown book_id: {book_id}")
    if entry.license_class != "purchased":
        raise ValueError(
            f"record_purchase_and_host requires purchased book; got {entry.license_class!r}"
        )
    adapter = ManualPurchaseReceipt(store=store)
    receipt = adapter.record_receipt(
        book_id=book_id,
        owner_id=owner_id,
        opaque_reference=opaque_reference,
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
    for doc_id in lib.document_ids:
        doc = store.get_document(doc_id) or {}
        title = str(doc.get("title") or doc_id)
        lic = str(doc.get("license_class") or "?")
        blocks.append(
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": f"[{lic}] {title} ({doc_id})",
                    }
                ],
            }
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
        if free_only and not (
            e.license_class == "public_domain" and e.is_free
        ):
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
