import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import type {
  BookHtmlConversionResultResponse,
  BookHtmlConversionReviewResponse,
  BookHtmlFileHandoffResponse,
  BookHtmlImportPreflightResponse,
  BookHtmlPublishJobResponse,
  BookHtmlPublicationRequestResponse,
  BookHtmlServeGateReviewResponse,
  BookPurchaseRequestResponse,
  BookSummary,
  CorpusStatus,
} from "../../api/books";
import {
  curateBooks,
  handoffBookHtmlFile,
  listBooks,
  preflightBookHtmlImport,
  recordBookHtmlConversionResult,
  requestBookPurchase,
  requestBookHtmlPublication,
  reviewBookHtmlConversion,
  reviewBookHtmlServeGate,
  runBookHtmlPublishJob,
} from "../../api/books";
import { listInvestigations } from "../../lib/api";
import type { InvestigationSummary } from "../../lib/api";
import { useInWindow } from "../../components/windows/windowHostContext";
import GlassSurface from "../../shell/GlassSurface";
import BookCard from "./BookCard";
import CorpusSearch from "./CorpusSearch";
import CuratePrompt from "./CuratePrompt";
import { documentsByTheme } from "./documentsByTheme";
import type { FeedOrdering } from "./documentsByTheme";

/**
 * Library — the home of the Read workflow (Read SPR-02; re-homed as the Read
 * DOOR in Read SPR-06).
 *
 * A shelf/grid over the servable corpus. The legal posture is visible in
 * the IA, not just the backend: the default view is the servable shelf
 * (public-domain + Antiek originals + publisher-licensed), and gated
 * books appear only under "Preview" — flagged, never implying full-text
 * access. This is Spotify-for-books: a licensed shelf, not an aggregator.
 *
 * Opening a book routes to /read/:documentId (SPR-03), which renders only
 * what the serve gate permits.
 *
 * Read SPR-06: this is the Read workflow's defaultRoute (the door). The PDF
 * wrestler is demoted from the door to a "bring your own PDF" affordance
 * here — still reachable for the power case, no longer the home. An empty
 * shelf shows an honest "what's available to read" state, NOT an uploader.
 */

const FILTERS: { key: CorpusStatus; label: string; hint: string }[] = [
  { key: "servable", label: "Shelf", hint: "Readable in full" },
  { key: "gated", label: "Preview", hint: "Metadata + snippet only" },
  { key: "all", label: "All", hint: "Everything, flagged" },
];

export default function Library() {
  const navigate = useNavigate();
  // SPR-09 window-adaptation contract: in a WorkspaceWindow, fill the
  // container (h-full) and drop the opaque full-bleed bg so the glass shows
  // through. Gated on this flag → the full-page route is unchanged.
  const inWindow = useInWindow();
  const [status, setStatus] = useState<CorpusStatus>("servable");
  const [books, setBooks] = useState<BookSummary[]>([]);
  // Active research, the signal documentsByTheme ranks the shelf to (M1).
  // Best-effort: a failed/empty fetch falls the feed back to recency, honestly.
  const [investigations, setInvestigations] = useState<InvestigationSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Prompt-to-curate (SPR-04): an ordered list of servable document_ids,
  // or null when no prompt is active. Curated books are a re-ranked subset
  // of the servable shelf.
  const [curatedOrder, setCuratedOrder] = useState<string[] | null>(null);
  const [curatePrompt, setCuratePrompt] = useState<string>("");
  const [curateBusy, setCurateBusy] = useState(false);
  const [purchaseTitle, setPurchaseTitle] = useState("");
  const [purchaseAuthor, setPurchaseAuthor] = useState("");
  const [purchaseUrl, setPurchaseUrl] = useState("");
  const [purchaseMaxUsd, setPurchaseMaxUsd] = useState("25");
  const [purchaseAck, setPurchaseAck] = useState(false);
  const [purchaseBusy, setPurchaseBusy] = useState(false);
  const [purchaseReceipt, setPurchaseReceipt] = useState<BookPurchaseRequestResponse | null>(null);
  const [importFileName, setImportFileName] = useState("");
  const [importFileFormat, setImportFileFormat] = useState<"epub" | "html" | "pdf" | "kindle" | "unknown">("epub");
  const [importHasLegalAccess, setImportHasLegalAccess] = useState(false);
  const [importAck, setImportAck] = useState(false);
  const [importBusy, setImportBusy] = useState(false);
  const [importReceipt, setImportReceipt] = useState<BookHtmlImportPreflightResponse | null>(null);
  const [handoffStorageRef, setHandoffStorageRef] = useState("");
  const [handoffChecksum, setHandoffChecksum] = useState("");
  const [handoffManualAck, setHandoffManualAck] = useState(false);
  const [handoffNoReadAck, setHandoffNoReadAck] = useState(false);
  const [handoffBusy, setHandoffBusy] = useState(false);
  const [handoffReceipt, setHandoffReceipt] = useState<BookHtmlFileHandoffResponse | null>(null);
  const [conversionConverter, setConversionConverter] = useState<
    "pandoc" | "calibre" | "native_html" | "manual_review" | "unknown"
  >("pandoc");
  const [conversionSandbox, setConversionSandbox] = useState<
    "locked_down" | "network_disabled" | "manual_only"
  >("locked_down");
  const [conversionSandboxAck, setConversionSandboxAck] = useState(false);
  const [conversionNoRunAck, setConversionNoRunAck] = useState(false);
  const [conversionBusy, setConversionBusy] = useState(false);
  const [conversionReceipt, setConversionReceipt] = useState<BookHtmlConversionReviewResponse | null>(null);
  const [outputRef, setOutputRef] = useState("");
  const [outputChecksum, setOutputChecksum] = useState("");
  const [outputPageCount, setOutputPageCount] = useState("");
  const [outputMetadataAck, setOutputMetadataAck] = useState(false);
  const [outputNoPublishAck, setOutputNoPublishAck] = useState(false);
  const [outputBusy, setOutputBusy] = useState(false);
  const [outputReceipt, setOutputReceipt] = useState<BookHtmlConversionResultResponse | null>(null);
  const [serveRightsBasis, setServeRightsBasis] = useState<
    "public_domain" | "publisher_opt_in" | "platform_authored" | "personal_license" | "unknown"
  >("personal_license");
  const [serveDecision, setServeDecision] = useState<"servable_full_text" | "gated_metadata_only" | "blocked">(
    "servable_full_text",
  );
  const [serveRightsAck, setServeRightsAck] = useState(false);
  const [serveNoPublishAck, setServeNoPublishAck] = useState(false);
  const [serveBusy, setServeBusy] = useState(false);
  const [serveReceipt, setServeReceipt] = useState<BookHtmlServeGateReviewResponse | null>(null);
  const [publicationDocHint, setPublicationDocHint] = useState("");
  const [publicationVisibility, setPublicationVisibility] = useState<"private_library" | "workspace_only">(
    "private_library",
  );
  const [publicationIntentAck, setPublicationIntentAck] = useState(false);
  const [publicationNoIngestAck, setPublicationNoIngestAck] = useState(false);
  const [publicationBusy, setPublicationBusy] = useState(false);
  const [publicationReceipt, setPublicationReceipt] =
    useState<BookHtmlPublicationRequestResponse | null>(null);
  const [publishDocumentId, setPublishDocumentId] = useState("");
  const [publishHtmlBody, setPublishHtmlBody] = useState("");
  const [publishLicenseBasis, setPublishLicenseBasis] = useState("");
  const [publishWriteAck, setPublishWriteAck] = useState(false);
  const [publishServableAck, setPublishServableAck] = useState(false);
  const [publishBusy, setPublishBusy] = useState(false);
  const [publishReceipt, setPublishReceipt] = useState<BookHtmlPublishJobResponse | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listBooks(status);
      setBooks(data.books);
      // Pull active research themes only for the default servable shelf — the
      // theme-ranked feed is the Read DOOR's first view. Best-effort: if the
      // research list is unavailable, the feed falls back to recency (the empty
      // investigations set → documentsByTheme returns ordering "recency").
      if (status === "servable") {
        try {
          const inv = await listInvestigations({ status: "in_progress" });
          setInvestigations(inv.investigations);
        } catch {
          setInvestigations([]); // thin signal → recency fallback, honestly
        }
      } else {
        setInvestigations([]);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => {
    void reload();
    // Switching shelves clears any active curation.
    setCuratedOrder(null);
    setCuratePrompt("");
  }, [reload]);

  const onCurate = useCallback(async (prompt: string) => {
    setCurateBusy(true);
    setError(null);
    try {
      const res = await curateBooks(prompt);
      setCuratedOrder(res.books.map((b) => b.document_id));
      setCuratePrompt(prompt);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setCurateBusy(false);
    }
  }, []);

  const onClearCurate = useCallback(() => {
    setCuratedOrder(null);
    setCuratePrompt("");
  }, []);

  const onPurchaseRequest = useCallback(async () => {
    const cents = Math.max(0, Math.round(Number(purchaseMaxUsd || "0") * 100));
    setPurchaseBusy(true);
    setError(null);
    setPurchaseReceipt(null);
    try {
      const res = await requestBookPurchase({
        title: purchaseTitle,
        author: purchaseAuthor.trim() || null,
        source_url: purchaseUrl.trim() || null,
        store: "other",
        max_price_usd_cents: cents,
        desired_format: "unknown",
        import_target: "antiek_html",
        acknowledge_manual_purchase_only: purchaseAck,
      });
      setPurchaseReceipt(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPurchaseBusy(false);
    }
  }, [purchaseAck, purchaseAuthor, purchaseMaxUsd, purchaseTitle, purchaseUrl]);

  const onImportPreflight = useCallback(async () => {
    const title = purchaseReceipt?.title ?? purchaseTitle;
    const author = purchaseReceipt?.author ?? (purchaseAuthor.trim() || null);
    setImportBusy(true);
    setError(null);
    setImportReceipt(null);
    try {
      const res = await preflightBookHtmlImport({
        title,
        author,
        source_request_id: purchaseReceipt?.request_id ?? null,
        file_name: importFileName.trim() || null,
        file_format: importFileFormat,
        has_legal_access: importHasLegalAccess,
        acknowledge_no_upload_or_ingest: importAck,
      });
      setImportReceipt(res);
      setHandoffReceipt(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setImportBusy(false);
    }
  }, [
    importAck,
    importFileFormat,
    importFileName,
    importHasLegalAccess,
    purchaseAuthor,
    purchaseReceipt,
    purchaseTitle,
  ]);

  const onFileHandoff = useCallback(async () => {
    if (!importReceipt) return;
    setHandoffBusy(true);
    setError(null);
    setHandoffReceipt(null);
    try {
      const res = await handoffBookHtmlFile({
        import_preflight_id: importReceipt.import_preflight_id,
        file_name: importReceipt.file_name ?? importFileName.trim(),
        file_format: importReceipt.file_format as "epub" | "html" | "pdf" | "kindle" | "unknown",
        storage_ref: handoffStorageRef,
        checksum_sha256: handoffChecksum.trim() || null,
        acknowledge_manual_storage_only: handoffManualAck,
        acknowledge_no_file_read_or_conversion: handoffNoReadAck,
      });
      setHandoffReceipt(res);
      setConversionReceipt(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setHandoffBusy(false);
    }
  }, [
    handoffChecksum,
    handoffManualAck,
    handoffNoReadAck,
    handoffStorageRef,
    importFileName,
    importReceipt,
  ]);

  const onConversionReview = useCallback(async () => {
    if (!handoffReceipt || !importReceipt) return;
    setConversionBusy(true);
    setError(null);
    setConversionReceipt(null);
    try {
      const res = await reviewBookHtmlConversion({
        handoff_id: handoffReceipt.handoff_id,
        import_preflight_id: importReceipt.import_preflight_id,
        converter: conversionConverter,
        sandbox_profile: conversionSandbox,
        output_format: "antiek_html",
        acknowledge_sandbox_required: conversionSandboxAck,
        acknowledge_no_conversion_run: conversionNoRunAck,
      });
      setConversionReceipt(res);
      setOutputReceipt(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setConversionBusy(false);
    }
  }, [
    conversionConverter,
    conversionNoRunAck,
    conversionSandbox,
    conversionSandboxAck,
    handoffReceipt,
    importReceipt,
  ]);

  const onConversionResult = useCallback(async () => {
    if (!conversionReceipt || !handoffReceipt) return;
    const pageCount = outputPageCount.trim().length > 0 ? Number(outputPageCount) : null;
    setOutputBusy(true);
    setError(null);
    setOutputReceipt(null);
    try {
      const res = await recordBookHtmlConversionResult({
        conversion_review_id: conversionReceipt.conversion_review_id,
        handoff_id: handoffReceipt.handoff_id,
        html_output_ref: outputRef,
        html_checksum_sha256: outputChecksum.trim() || null,
        page_count_estimate: pageCount === null || Number.isNaN(pageCount) ? null : pageCount,
        acknowledge_output_metadata_only: outputMetadataAck,
        acknowledge_no_publish_or_serve: outputNoPublishAck,
      });
      setOutputReceipt(res);
      setServeReceipt(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setOutputBusy(false);
    }
  }, [
    conversionReceipt,
    handoffReceipt,
    outputChecksum,
    outputMetadataAck,
    outputNoPublishAck,
    outputPageCount,
    outputRef,
  ]);

  const onServeGateReview = useCallback(async () => {
    if (!outputReceipt) return;
    setServeBusy(true);
    setError(null);
    setServeReceipt(null);
    try {
      const res = await reviewBookHtmlServeGate({
        conversion_result_id: outputReceipt.conversion_result_id,
        title: importReceipt?.title ?? purchaseTitle,
        author: importReceipt?.author ?? (purchaseAuthor.trim() || null),
        rights_basis: serveRightsBasis,
        servability_decision: serveDecision,
        acknowledge_rights_reviewed: serveRightsAck,
        acknowledge_no_publication: serveNoPublishAck,
      });
      setServeReceipt(res);
      setPublicationReceipt(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setServeBusy(false);
    }
  }, [
    importReceipt,
    outputReceipt,
    purchaseAuthor,
    purchaseTitle,
    serveDecision,
    serveNoPublishAck,
    serveRightsAck,
    serveRightsBasis,
  ]);

  const onPublicationRequest = useCallback(async () => {
    if (!serveReceipt || !outputReceipt) return;
    setPublicationBusy(true);
    setError(null);
    setPublicationReceipt(null);
    try {
      const res = await requestBookHtmlPublication({
        serve_gate_review_id: serveReceipt.serve_gate_review_id,
        conversion_result_id: outputReceipt.conversion_result_id,
        document_id_hint: publicationDocHint.trim() || null,
        shelf_visibility: publicationVisibility,
        acknowledge_publication_intent: publicationIntentAck,
        acknowledge_no_ingest_or_serve: publicationNoIngestAck,
      });
      setPublicationReceipt(res);
      setPublishReceipt(null);
      if (publicationDocHint.trim()) {
        setPublishDocumentId(publicationDocHint.trim());
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPublicationBusy(false);
    }
  }, [
    outputReceipt,
    publicationDocHint,
    publicationIntentAck,
    publicationNoIngestAck,
    publicationVisibility,
    serveReceipt,
  ]);

  const onPublishJob = useCallback(async () => {
    if (!publicationReceipt || !serveReceipt || !importReceipt) return;
    const pageCount =
      outputReceipt?.page_count_estimate !== null && outputReceipt?.page_count_estimate !== undefined
        ? outputReceipt.page_count_estimate
        : 0;
    const rightsBasis =
      serveRightsBasis === "unknown" ? "personal_license" : serveRightsBasis;
    setPublishBusy(true);
    setError(null);
    setPublishReceipt(null);
    try {
      const res = await runBookHtmlPublishJob({
        publication_request_id: publicationReceipt.publication_request_id,
        serve_gate_review_id: serveReceipt.serve_gate_review_id,
        document_id: publishDocumentId,
        title: importReceipt.title,
        author: importReceipt.author,
        html_body: publishHtmlBody,
        rights_basis: rightsBasis,
        page_count: pageCount,
        license_basis: publishLicenseBasis,
        acknowledge_write_to_library: publishWriteAck,
        acknowledge_full_text_servable: publishServableAck,
      });
      setPublishReceipt(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPublishBusy(false);
    }
  }, [
    importReceipt,
    outputReceipt,
    publicationReceipt,
    publishDocumentId,
    publishHtmlBody,
    publishLicenseBasis,
    publishServableAck,
    publishWriteAck,
    serveReceipt,
    serveRightsBasis,
  ]);

  // The display order, in three layers of precedence:
  //   1. an ACTIVE CURATE prompt (explicit user query) re-ranks to that order;
  //   2. otherwise, on the default servable shelf, documentsByTheme ranks to
  //      the user's active research themes (M1) — or falls back to recency with
  //      a STATED label when the theme signal is thin (the honesty seam);
  //   3. on the Preview / All shelves there is no ambient theme ranking — they
  //      are flagged catalogues, shown in their given (recency) order.
  // `ordering`/`themeTerms` drive the honest label the surface renders.
  const { displayed, ordering, themeTerms } = useMemo<{
    displayed: BookSummary[];
    ordering: FeedOrdering | null;
    themeTerms: string[];
  }>(() => {
    if (curatedOrder) {
      // Curated: re-rank the loaded shelf to the curated order; books not in
      // the shelf (shouldn't happen — curate is servable-only) are dropped
      // rather than rendered without their metadata.
      const byId = new Map(books.map((b) => [b.document_id, b]));
      const curated = curatedOrder
        .map((id) => byId.get(id))
        .filter((b): b is BookSummary => Boolean(b));
      return { displayed: curated, ordering: null, themeTerms: [] };
    }
    if (status === "servable") {
      const feed = documentsByTheme(books, investigations);
      return { displayed: feed.books, ordering: feed.ordering, themeTerms: feed.themeTerms };
    }
    return { displayed: books, ordering: null, themeTerms: [] };
  }, [curatedOrder, books, status, investigations]);

  const open = useCallback(
    (documentId: string) => navigate(`/read/${encodeURIComponent(documentId)}`),
    [navigate],
  );

  // Open a book at a specific page (M1 search-result jump). The reader reads its
  // page from the SAME sessionStorage locator usePosition owns (no new
  // mechanism); seeding it here lands the reader on the cited page. A null /
  // unresolved page opens at the saved position (honest — no fake page jump).
  const openAtPage = useCallback(
    (documentId: string, pageIndex?: number | null) => {
      if (pageIndex !== null && pageIndex !== undefined && pageIndex >= 0) {
        try {
          window.sessionStorage.setItem(`antiek.read.pos.${documentId}`, String(pageIndex));
        } catch {
          /* private mode — the reader still opens, just at the saved page */
        }
      }
      navigate(`/read/${encodeURIComponent(documentId)}`);
    },
    [navigate],
  );

  const subtitle = useMemo(() => {
    if (loading) return "Loading the shelf…";
    if (status === "servable") return `${books.length} books readable in full`;
    if (status === "gated") return `${books.length} preview-only titles`;
    return `${books.length} titles`;
  }, [loading, status, books.length]);

  // The Library shelf body. Two surfaces:
  //  - inWindow (SPR-09 contract): a WorkspaceWindow already owns the glass, so
  //    the body stays bg-transparent and is NOT re-glassed — preserved verbatim.
  //  - the full-page landing (the Read door): a LANDING surface (SPR-03 M2) —
  //    its body renders through GlassSurface so the <Scene/> (z-0) shows through
  //    instead of the old opaque bg-ice-0 dark:bg-charcoal-2 wall; the scrim
  //    keeps the shelf header + body text legible (WCAG-AA owned by the glass).
  const shelfBody = (
    <div className="max-w-5xl mx-auto px-8 py-10 space-y-6">
          <header className="space-y-2">
            <div className="flex items-start justify-between gap-4">
              <h1 className="text-2xl font-serif text-ink dark:text-bright">Library</h1>
              <div className="shrink-0 mt-1 flex items-center gap-4">
                {/* SPR-09 M2: the paginated browse view over the catalog endpoint
                    — for scanning the whole shelf a page at a time. Additive to
                    the theme-ranked door. */}
                <button
                  type="button"
                  onClick={() => navigate("/library/browse")}
                  className="text-xs font-mono text-shadow-1 dark:text-moonlight underline decoration-dotted underline-offset-2 hover:text-ink dark:hover:text-bright"
                  title="Browse the whole catalog, a page at a time"
                >
                  browse all →
                </button>
                {/* Read SPR-06: the PDF wrestler, demoted from the Read door to a
                    bring-your-own affordance. Reachable for the power case (read a
                    PDF you brought), no longer the home — the shelf is. */}
                <button
                  type="button"
                  onClick={() => navigate("/wrestle")}
                  className="text-xs font-mono text-shadow-1 dark:text-moonlight underline decoration-dotted underline-offset-2 hover:text-ink dark:hover:text-bright"
                  title="Read a PDF you bring yourself"
                >
                  bring your own PDF →
                </button>
              </div>
            </div>
            <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
              A licensed shelf of what can be aggregated — public-domain works,
              Antiek originals, and publisher-opted-in titles you can read in
              full. Acquisition requests are prepared without checkout here;
              everything else is preview-only. {subtitle}.
            </p>
          </header>

          <div
            role="tablist"
            aria-label="Corpus filter"
            className="flex items-center gap-2"
          >
            {FILTERS.map((f) => (
              <button
                key={f.key}
                role="tab"
                aria-selected={status === f.key}
                type="button"
                title={f.hint}
                onClick={() => setStatus(f.key)}
                className={`px-3 py-1 rounded-md text-xs font-mono transition-colors ${
                  status === f.key
                    ? "bg-ink text-white"
                    : "bg-ice-3 dark:bg-charcoal-1 text-ink dark:text-bright hover:bg-ice-4"
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>

          {/* M1: search the OWNED corpus — typed query OR file-drop bias.
              Theme-context (the active research themes) is folded into the
              query when present, degrading gracefully when absent. */}
          <CorpusSearch onOpen={openAtPage} themeContext={themeTerms} />

          {/* M4: meta-reading entry — deep-research the owned corpus into a
              re-openable, length-boxed Read asset. PROPOSED boundary (sign-off
              pending) — the surface itself carries the banner. */}
          <div className="flex items-center justify-between gap-3 rounded-md border border-sun/40 bg-sun/10 px-3 py-2">
            <p className="text-[13px] font-serif text-ink dark:text-bright">
              Make a reading asset from your corpus
              <span className="ml-2 text-[11px] font-mono uppercase tracking-wider text-sun-deep dark:text-sun">
                proposed
              </span>
            </p>
            <button
              type="button"
              onClick={() => navigate("/read/meta-reading")}
              className="shrink-0 text-xs font-mono text-ink dark:text-bright underline decoration-dotted underline-offset-2 hover:opacity-80"
            >
              Meta-read →
            </button>
          </div>

          <form
            className="rounded-md border border-ice-4 dark:border-charcoal-1 bg-white/70 dark:bg-charcoal-2/70 p-3 space-y-3"
            onSubmit={(event) => {
              event.preventDefault();
              void onPurchaseRequest();
            }}
          >
            <div className="flex flex-col gap-3 md:flex-row md:items-end">
              <label className="flex-1 min-w-0 text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                Title
                <input
                  value={purchaseTitle}
                  onChange={(event) => setPurchaseTitle(event.target.value)}
                  required
                  className="mt-1 w-full rounded-md border border-ice-4 dark:border-charcoal-1 bg-white dark:bg-charcoal-3 px-2 py-1.5 text-sm normal-case tracking-normal text-ink dark:text-bright"
                  placeholder="Book to acquire"
                />
              </label>
              <label className="flex-1 min-w-0 text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                Author
                <input
                  value={purchaseAuthor}
                  onChange={(event) => setPurchaseAuthor(event.target.value)}
                  className="mt-1 w-full rounded-md border border-ice-4 dark:border-charcoal-1 bg-white dark:bg-charcoal-3 px-2 py-1.5 text-sm normal-case tracking-normal text-ink dark:text-bright"
                  placeholder="Optional"
                />
              </label>
              <label className="w-full md:w-28 text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                Max USD
                <input
                  value={purchaseMaxUsd}
                  onChange={(event) => setPurchaseMaxUsd(event.target.value)}
                  min="0"
                  step="0.01"
                  type="number"
                  className="mt-1 w-full rounded-md border border-ice-4 dark:border-charcoal-1 bg-white dark:bg-charcoal-3 px-2 py-1.5 text-sm normal-case tracking-normal text-ink dark:text-bright"
                />
              </label>
            </div>
            <label className="block text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
              Source URL
              <input
                value={purchaseUrl}
                onChange={(event) => setPurchaseUrl(event.target.value)}
                className="mt-1 w-full rounded-md border border-ice-4 dark:border-charcoal-1 bg-white dark:bg-charcoal-3 px-2 py-1.5 text-sm normal-case tracking-normal text-ink dark:text-bright"
                placeholder="Optional store or publisher page"
              />
            </label>
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <label className="flex items-start gap-2 text-[12px] font-serif text-ink-soft dark:text-starlight">
                <input
                  type="checkbox"
                  checked={purchaseAck}
                  onChange={(event) => setPurchaseAck(event.target.checked)}
                  className="mt-0.5"
                />
                <span>No purchase, fetch, budget reservation, or import runs from this request.</span>
              </label>
              <button
                type="submit"
                disabled={purchaseBusy || purchaseTitle.trim().length === 0}
                className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
              >
                {purchaseBusy ? "Preparing…" : "Prepare request"}
              </button>
            </div>
            {purchaseReceipt && (
              <p className="text-[13px] font-serif text-ink dark:text-bright" role="status">
                Request {purchaseReceipt.request_id} is ready for manual purchase; Antiek reserved $
                {(purchaseReceipt.spend_reserved_usd_cents / 100).toFixed(2)} and performed no external call.
              </p>
            )}
          </form>

          <form
            className="rounded-md border border-ice-4 dark:border-charcoal-1 bg-white/70 dark:bg-charcoal-2/70 p-3 space-y-3"
            onSubmit={(event) => {
              event.preventDefault();
              void onImportPreflight();
            }}
          >
            <div>
              <p className="text-[13px] font-serif text-ink dark:text-bright">
                HTML import preflight
              </p>
              <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight">
                Checks legal-access and HTML-hosting posture only; no upload,
                file read, conversion, ingest, or graph write runs here.
              </p>
            </div>
            <div className="flex flex-col gap-3 md:flex-row md:items-end">
              <label className="flex-1 min-w-0 text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                File name
                <input
                  value={importFileName}
                  onChange={(event) => setImportFileName(event.target.value)}
                  className="mt-1 w-full rounded-md border border-ice-4 dark:border-charcoal-1 bg-white dark:bg-charcoal-3 px-2 py-1.5 text-sm normal-case tracking-normal text-ink dark:text-bright"
                  placeholder="Optional filename"
                />
              </label>
              <label className="w-full md:w-36 text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                Format
                <select
                  value={importFileFormat}
                  onChange={(event) => setImportFileFormat(event.target.value as typeof importFileFormat)}
                  className="mt-1 w-full rounded-md border border-ice-4 dark:border-charcoal-1 bg-white dark:bg-charcoal-3 px-2 py-1.5 text-sm normal-case tracking-normal text-ink dark:text-bright"
                >
                  <option value="epub">EPUB</option>
                  <option value="html">HTML</option>
                  <option value="pdf">PDF</option>
                  <option value="kindle">Kindle</option>
                  <option value="unknown">Unknown</option>
                </select>
              </label>
            </div>
            <div className="flex flex-col gap-2">
              <label className="flex items-start gap-2 text-[12px] font-serif text-ink-soft dark:text-starlight">
                <input
                  type="checkbox"
                  checked={importHasLegalAccess}
                  onChange={(event) => setImportHasLegalAccess(event.target.checked)}
                  className="mt-0.5"
                />
                <span>I have legal access to this file or receipt-backed copy.</span>
              </label>
              <label className="flex items-start gap-2 text-[12px] font-serif text-ink-soft dark:text-starlight">
                <input
                  type="checkbox"
                  checked={importAck}
                  onChange={(event) => setImportAck(event.target.checked)}
                  className="mt-0.5"
                />
                <span>No upload, file read, conversion, ingest, or graph write runs from this preflight.</span>
              </label>
            </div>
            <button
              type="submit"
              disabled={importBusy || (purchaseReceipt?.title ?? purchaseTitle).trim().length === 0}
              className="rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
            >
              {importBusy ? "Checking…" : "Check import"}
            </button>
            {importReceipt && (
              <p className="text-[13px] font-serif text-ink dark:text-bright" role="status">
                Import {importReceipt.import_preflight_id} is ready for operator file handoff; uploaded{" "}
                {importReceipt.file_uploaded ? "yes" : "no"}, ingested{" "}
                {importReceipt.ingest_attempted ? "yes" : "no"}, HTML hosting required{" "}
                {importReceipt.html_hosting_required ? "yes" : "no"}.
              </p>
            )}
          </form>

          {importReceipt && (
            <form
              className="rounded-md border border-ice-4 dark:border-charcoal-1 bg-white/70 dark:bg-charcoal-2/70 p-3 space-y-3"
              onSubmit={(event) => {
                event.preventDefault();
                void onFileHandoff();
              }}
            >
              <div>
                <p className="text-[13px] font-serif text-ink dark:text-bright">
                  File handoff metadata
                </p>
                <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight">
                  Records the operator storage reference only; Antiek does not upload,
                  open, read, convert, ingest, or serve the file here.
                </p>
              </div>
              <label className="block text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                Storage reference
                <input
                  value={handoffStorageRef}
                  onChange={(event) => setHandoffStorageRef(event.target.value)}
                  required
                  className="mt-1 w-full rounded-md border border-ice-4 dark:border-charcoal-1 bg-white dark:bg-charcoal-3 px-2 py-1.5 text-sm normal-case tracking-normal text-ink dark:text-bright"
                  placeholder="operator-vault://books/title.epub"
                />
              </label>
              <label className="block text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                SHA-256
                <input
                  value={handoffChecksum}
                  onChange={(event) => setHandoffChecksum(event.target.value)}
                  className="mt-1 w-full rounded-md border border-ice-4 dark:border-charcoal-1 bg-white dark:bg-charcoal-3 px-2 py-1.5 text-sm normal-case tracking-normal text-ink dark:text-bright"
                  placeholder="Optional 64-character checksum"
                />
              </label>
              <div className="flex flex-col gap-2">
                <label className="flex items-start gap-2 text-[12px] font-serif text-ink-soft dark:text-starlight">
                  <input
                    type="checkbox"
                    checked={handoffManualAck}
                    onChange={(event) => setHandoffManualAck(event.target.checked)}
                    className="mt-0.5"
                  />
                  <span>This is a manual storage reference, not a file upload.</span>
                </label>
                <label className="flex items-start gap-2 text-[12px] font-serif text-ink-soft dark:text-starlight">
                  <input
                    type="checkbox"
                    checked={handoffNoReadAck}
                    onChange={(event) => setHandoffNoReadAck(event.target.checked)}
                    className="mt-0.5"
                  />
                  <span>No file open, read, conversion, ingest, graph write, or serve runs from this handoff.</span>
                </label>
              </div>
              <button
                type="submit"
                disabled={
                  handoffBusy ||
                  handoffStorageRef.trim().length === 0 ||
                  (importReceipt.file_name ?? importFileName.trim()).trim().length === 0
                }
                className="rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
              >
                {handoffBusy ? "Recording…" : "Record handoff"}
              </button>
              {handoffReceipt && (
                <p className="text-[13px] font-serif text-ink dark:text-bright" role="status">
                  Handoff {handoffReceipt.handoff_id} is ready for conversion review; file read{" "}
                  {handoffReceipt.file_read_attempted ? "yes" : "no"}, converted{" "}
                  {handoffReceipt.conversion_attempted ? "yes" : "no"}, uploaded{" "}
                  {handoffReceipt.upload_accepted ? "yes" : "no"}.
                </p>
              )}
            </form>
          )}

          {handoffReceipt && (
            <form
              className="rounded-md border border-ice-4 dark:border-charcoal-1 bg-white/70 dark:bg-charcoal-2/70 p-3 space-y-3"
              onSubmit={(event) => {
                event.preventDefault();
                void onConversionReview();
              }}
            >
              <div>
                <p className="text-[13px] font-serif text-ink dark:text-bright">
                  Conversion review
                </p>
                <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight">
                  Approves the converter plan only; no storage reference is read,
                  no converter runs, and no HTML output is written here.
                </p>
              </div>
              <div className="flex flex-col gap-3 md:flex-row md:items-end">
                <label className="flex-1 min-w-0 text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Converter
                  <select
                    value={conversionConverter}
                    onChange={(event) =>
                      setConversionConverter(
                        event.target.value as "pandoc" | "calibre" | "native_html" | "manual_review" | "unknown",
                      )
                    }
                    className="mt-1 w-full rounded-md border border-ice-4 dark:border-charcoal-1 bg-white dark:bg-charcoal-3 px-2 py-1.5 text-sm normal-case tracking-normal text-ink dark:text-bright"
                  >
                    <option value="pandoc">Pandoc</option>
                    <option value="calibre">Calibre</option>
                    <option value="native_html">Native HTML</option>
                    <option value="manual_review">Manual review</option>
                    <option value="unknown">Unknown</option>
                  </select>
                </label>
                <label className="flex-1 min-w-0 text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Sandbox
                  <select
                    value={conversionSandbox}
                    onChange={(event) =>
                      setConversionSandbox(event.target.value as "locked_down" | "network_disabled" | "manual_only")
                    }
                    className="mt-1 w-full rounded-md border border-ice-4 dark:border-charcoal-1 bg-white dark:bg-charcoal-3 px-2 py-1.5 text-sm normal-case tracking-normal text-ink dark:text-bright"
                  >
                    <option value="locked_down">Locked down</option>
                    <option value="network_disabled">Network disabled</option>
                    <option value="manual_only">Manual only</option>
                  </select>
                </label>
              </div>
              <div className="flex flex-col gap-2">
                <label className="flex items-start gap-2 text-[12px] font-serif text-ink-soft dark:text-starlight">
                  <input
                    type="checkbox"
                    checked={conversionSandboxAck}
                    onChange={(event) => setConversionSandboxAck(event.target.checked)}
                    className="mt-0.5"
                  />
                  <span>The converter must run later inside the approved sandbox.</span>
                </label>
                <label className="flex items-start gap-2 text-[12px] font-serif text-ink-soft dark:text-starlight">
                  <input
                    type="checkbox"
                    checked={conversionNoRunAck}
                    onChange={(event) => setConversionNoRunAck(event.target.checked)}
                    className="mt-0.5"
                  />
                  <span>No conversion, file read, output write, ingest, graph write, or serve runs from this review.</span>
                </label>
              </div>
              <button
                type="submit"
                disabled={conversionBusy}
                className="rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
              >
                {conversionBusy ? "Reviewing…" : "Review conversion"}
              </button>
              {conversionReceipt && (
                <p className="text-[13px] font-serif text-ink dark:text-bright" role="status">
                  Conversion {conversionReceipt.conversion_review_id} is ready for an explicit job; read{" "}
                  {conversionReceipt.file_read_attempted ? "yes" : "no"}, converted{" "}
                  {conversionReceipt.conversion_attempted ? "yes" : "no"}, output written{" "}
                  {conversionReceipt.output_written ? "yes" : "no"}.
                </p>
              )}
            </form>
          )}

          {conversionReceipt && (
            <form
              className="rounded-md border border-ice-4 dark:border-charcoal-1 bg-white/70 dark:bg-charcoal-2/70 p-3 space-y-3"
              onSubmit={(event) => {
                event.preventDefault();
                void onConversionResult();
              }}
            >
              <div>
                <p className="text-[13px] font-serif text-ink dark:text-bright">
                  Converted HTML metadata
                </p>
                <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight">
                  Records the converted HTML output reference only; no output is
                  fetched, ingested, published, or served here.
                </p>
              </div>
              <label className="block text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                HTML output reference
                <input
                  value={outputRef}
                  onChange={(event) => setOutputRef(event.target.value)}
                  required
                  className="mt-1 w-full rounded-md border border-ice-4 dark:border-charcoal-1 bg-white dark:bg-charcoal-3 px-2 py-1.5 text-sm normal-case tracking-normal text-ink dark:text-bright"
                  placeholder="operator-vault://books/title/index.html"
                />
              </label>
              <div className="flex flex-col gap-3 md:flex-row md:items-end">
                <label className="flex-1 min-w-0 text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  HTML SHA-256
                  <input
                    value={outputChecksum}
                    onChange={(event) => setOutputChecksum(event.target.value)}
                    className="mt-1 w-full rounded-md border border-ice-4 dark:border-charcoal-1 bg-white dark:bg-charcoal-3 px-2 py-1.5 text-sm normal-case tracking-normal text-ink dark:text-bright"
                    placeholder="Optional 64-character checksum"
                  />
                </label>
                <label className="w-full md:w-32 text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Pages
                  <input
                    value={outputPageCount}
                    onChange={(event) => setOutputPageCount(event.target.value)}
                    min="0"
                    type="number"
                    className="mt-1 w-full rounded-md border border-ice-4 dark:border-charcoal-1 bg-white dark:bg-charcoal-3 px-2 py-1.5 text-sm normal-case tracking-normal text-ink dark:text-bright"
                  />
                </label>
              </div>
              <div className="flex flex-col gap-2">
                <label className="flex items-start gap-2 text-[12px] font-serif text-ink-soft dark:text-starlight">
                  <input
                    type="checkbox"
                    checked={outputMetadataAck}
                    onChange={(event) => setOutputMetadataAck(event.target.checked)}
                    className="mt-0.5"
                  />
                  <span>This records converted-output metadata only.</span>
                </label>
                <label className="flex items-start gap-2 text-[12px] font-serif text-ink-soft dark:text-starlight">
                  <input
                    type="checkbox"
                    checked={outputNoPublishAck}
                    onChange={(event) => setOutputNoPublishAck(event.target.checked)}
                    className="mt-0.5"
                  />
                  <span>No output fetch, ingest, graph write, shelf publication, or full-text serve runs from this receipt.</span>
                </label>
              </div>
              <button
                type="submit"
                disabled={outputBusy || outputRef.trim().length === 0}
                className="rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
              >
                {outputBusy ? "Recording…" : "Record output"}
              </button>
              {outputReceipt && (
                <p className="text-[13px] font-serif text-ink dark:text-bright" role="status">
                  Output {outputReceipt.conversion_result_id} is ready for serve-gate review; fetched{" "}
                  {outputReceipt.output_ref_fetched ? "yes" : "no"}, ingested{" "}
                  {outputReceipt.ingest_attempted ? "yes" : "no"}, served{" "}
                  {outputReceipt.full_text_served ? "yes" : "no"}.
                </p>
              )}
            </form>
          )}

          {outputReceipt && (
            <form
              className="rounded-md border border-ice-4 dark:border-charcoal-1 bg-white/70 dark:bg-charcoal-2/70 p-3 space-y-3"
              onSubmit={(event) => {
                event.preventDefault();
                void onServeGateReview();
              }}
            >
              <div>
                <p className="text-[13px] font-serif text-ink dark:text-bright">
                  Serve-gate review
                </p>
                <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight">
                  Records rights and servability metadata only; no HTML is read,
                  no graph state changes, and nothing is published here.
                </p>
              </div>
              <div className="flex flex-col gap-3 md:flex-row md:items-end">
                <label className="flex-1 min-w-0 text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Rights basis
                  <select
                    value={serveRightsBasis}
                    onChange={(event) =>
                      setServeRightsBasis(
                        event.target.value as
                          | "public_domain"
                          | "publisher_opt_in"
                          | "platform_authored"
                          | "personal_license"
                          | "unknown",
                      )
                    }
                    className="mt-1 w-full rounded-md border border-ice-4 dark:border-charcoal-1 bg-white dark:bg-charcoal-3 px-2 py-1.5 text-sm normal-case tracking-normal text-ink dark:text-bright"
                  >
                    <option value="personal_license">Personal license</option>
                    <option value="public_domain">Public domain</option>
                    <option value="publisher_opt_in">Publisher opt-in</option>
                    <option value="platform_authored">Platform authored</option>
                    <option value="unknown">Unknown</option>
                  </select>
                </label>
                <label className="flex-1 min-w-0 text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Servability
                  <select
                    value={serveDecision}
                    onChange={(event) =>
                      setServeDecision(event.target.value as "servable_full_text" | "gated_metadata_only" | "blocked")
                    }
                    className="mt-1 w-full rounded-md border border-ice-4 dark:border-charcoal-1 bg-white dark:bg-charcoal-3 px-2 py-1.5 text-sm normal-case tracking-normal text-ink dark:text-bright"
                  >
                    <option value="servable_full_text">Servable full text</option>
                    <option value="gated_metadata_only">Gated metadata only</option>
                    <option value="blocked">Blocked</option>
                  </select>
                </label>
              </div>
              <div className="flex flex-col gap-2">
                <label className="flex items-start gap-2 text-[12px] font-serif text-ink-soft dark:text-starlight">
                  <input
                    type="checkbox"
                    checked={serveRightsAck}
                    onChange={(event) => setServeRightsAck(event.target.checked)}
                    className="mt-0.5"
                  />
                  <span>I reviewed rights and servability evidence for this converted HTML.</span>
                </label>
                <label className="flex items-start gap-2 text-[12px] font-serif text-ink-soft dark:text-starlight">
                  <input
                    type="checkbox"
                    checked={serveNoPublishAck}
                    onChange={(event) => setServeNoPublishAck(event.target.checked)}
                    className="mt-0.5"
                  />
                  <span>No ingest, graph write, shelf publication, or full-text serve runs from this review.</span>
                </label>
              </div>
              <button
                type="submit"
                disabled={serveBusy}
                className="rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
              >
                {serveBusy ? "Reviewing…" : "Review serve gate"}
              </button>
              {serveReceipt && (
                <p className="text-[13px] font-serif text-ink dark:text-bright" role="status">
                  Serve gate {serveReceipt.serve_gate_review_id} is{" "}
                  {serveReceipt.publication_allowed_next ? "ready for publication request" : "blocked"}; published{" "}
                  {serveReceipt.shelf_publication_attempted ? "yes" : "no"}, served{" "}
                  {serveReceipt.full_text_served ? "yes" : "no"}.
                </p>
              )}
            </form>
          )}

          {serveReceipt && (
            <form
              className="rounded-md border border-ice-4 dark:border-charcoal-1 bg-white/70 dark:bg-charcoal-2/70 p-3 space-y-3"
              onSubmit={(event) => {
                event.preventDefault();
                void onPublicationRequest();
              }}
            >
              <div>
                <p className="text-[13px] font-serif text-ink dark:text-bright">
                  Publication request
                </p>
                <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight">
                  Records intent to publish the approved HTML later; no ingest,
                  graph write, shelf update, reader route, or full-text serve runs here.
                </p>
              </div>
              <div className="flex flex-col gap-3 md:flex-row md:items-end">
                <label className="flex-1 min-w-0 text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Document id hint
                  <input
                    value={publicationDocHint}
                    onChange={(event) => setPublicationDocHint(event.target.value)}
                    className="mt-1 w-full rounded-md border border-ice-4 dark:border-charcoal-1 bg-white dark:bg-charcoal-3 px-2 py-1.5 text-sm normal-case tracking-normal text-ink dark:text-bright"
                    placeholder="Optional slug for later publish job"
                  />
                </label>
                <label className="w-full md:w-44 text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Visibility
                  <select
                    value={publicationVisibility}
                    onChange={(event) =>
                      setPublicationVisibility(event.target.value as "private_library" | "workspace_only")
                    }
                    className="mt-1 w-full rounded-md border border-ice-4 dark:border-charcoal-1 bg-white dark:bg-charcoal-3 px-2 py-1.5 text-sm normal-case tracking-normal text-ink dark:text-bright"
                  >
                    <option value="private_library">Private library</option>
                    <option value="workspace_only">Workspace only</option>
                  </select>
                </label>
              </div>
              <div className="flex flex-col gap-2">
                <label className="flex items-start gap-2 text-[12px] font-serif text-ink-soft dark:text-starlight">
                  <input
                    type="checkbox"
                    checked={publicationIntentAck}
                    onChange={(event) => setPublicationIntentAck(event.target.checked)}
                    className="mt-0.5"
                  />
                  <span>I intend to publish this reviewed Antiek HTML in a later explicit job.</span>
                </label>
                <label className="flex items-start gap-2 text-[12px] font-serif text-ink-soft dark:text-starlight">
                  <input
                    type="checkbox"
                    checked={publicationNoIngestAck}
                    onChange={(event) => setPublicationNoIngestAck(event.target.checked)}
                    className="mt-0.5"
                  />
                  <span>No ingest, graph write, shelf publication, reader route, or full-text serve runs from this request.</span>
                </label>
              </div>
              <button
                type="submit"
                disabled={publicationBusy || !serveReceipt.publication_allowed_next}
                className="rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
              >
                {publicationBusy ? "Preparing…" : "Prepare publication"}
              </button>
              {publicationReceipt && (
                <p className="text-[13px] font-serif text-ink dark:text-bright" role="status">
                  Publication {publicationReceipt.publication_request_id} is ready for an explicit publish job; ingested{" "}
                  {publicationReceipt.ingest_attempted ? "yes" : "no"}, published{" "}
                  {publicationReceipt.shelf_publication_attempted ? "yes" : "no"}, served{" "}
                  {publicationReceipt.full_text_served ? "yes" : "no"}.
                </p>
              )}
            </form>
          )}

          {publicationReceipt && (
            <form
              className="rounded-md border border-ice-4 dark:border-charcoal-1 bg-white/70 dark:bg-charcoal-2/70 p-3 space-y-3"
              onSubmit={(event) => {
                event.preventDefault();
                void onPublishJob();
              }}
            >
              <div>
                <p className="text-[13px] font-serif text-ink dark:text-bright">
                  Publish inline HTML
                </p>
                <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight">
                  Writes the provided Antiek HTML body into the local library;
                  no external file, storage reference, provider, checkout, or spend is touched.
                </p>
              </div>
              <label className="block text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                Document id
                <input
                  value={publishDocumentId}
                  onChange={(event) => setPublishDocumentId(event.target.value)}
                  required
                  className="mt-1 w-full rounded-md border border-ice-4 dark:border-charcoal-1 bg-white dark:bg-charcoal-3 px-2 py-1.5 text-sm normal-case tracking-normal text-ink dark:text-bright"
                  placeholder="book-dream-machine"
                />
              </label>
              <label className="block text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                Antiek HTML body
                <textarea
                  value={publishHtmlBody}
                  onChange={(event) => setPublishHtmlBody(event.target.value)}
                  required
                  rows={4}
                  className="mt-1 w-full rounded-md border border-ice-4 dark:border-charcoal-1 bg-white dark:bg-charcoal-3 px-2 py-1.5 text-sm normal-case tracking-normal text-ink dark:text-bright"
                  placeholder="<article><h1>Title</h1><p>Body…</p></article>"
                />
              </label>
              <label className="block text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                License basis
                <input
                  value={publishLicenseBasis}
                  onChange={(event) => setPublishLicenseBasis(event.target.value)}
                  required
                  className="mt-1 w-full rounded-md border border-ice-4 dark:border-charcoal-1 bg-white dark:bg-charcoal-3 px-2 py-1.5 text-sm normal-case tracking-normal text-ink dark:text-bright"
                  placeholder="Operator-owned copy for private Antiek library"
                />
              </label>
              <div className="flex flex-col gap-2">
                <label className="flex items-start gap-2 text-[12px] font-serif text-ink-soft dark:text-starlight">
                  <input
                    type="checkbox"
                    checked={publishWriteAck}
                    onChange={(event) => setPublishWriteAck(event.target.checked)}
                    className="mt-0.5"
                  />
                  <span>Write this inline HTML into my local Antiek library.</span>
                </label>
                <label className="flex items-start gap-2 text-[12px] font-serif text-ink-soft dark:text-starlight">
                  <input
                    type="checkbox"
                    checked={publishServableAck}
                    onChange={(event) => setPublishServableAck(event.target.checked)}
                    className="mt-0.5"
                  />
                  <span>The rights basis allows full-text reading through the existing serve gate.</span>
                </label>
              </div>
              <button
                type="submit"
                disabled={
                  publishBusy ||
                  publishDocumentId.trim().length === 0 ||
                  publishHtmlBody.trim().length === 0 ||
                  publishLicenseBasis.trim().length === 0
                }
                className="rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
              >
                {publishBusy ? "Publishing…" : "Publish HTML"}
              </button>
              {publishReceipt && (
                <p className="text-[13px] font-serif text-ink dark:text-bright" role="status">
                  Published {publishReceipt.document_id} through {publishReceipt.publish_job_id}; servable{" "}
                  {publishReceipt.servable_full_text ? "yes" : "no"}, route {publishReceipt.open_route}.
                </p>
              )}
            </form>
          )}

          {status === "servable" && (
            <CuratePrompt
              onCurate={onCurate}
              onClear={onClearCurate}
              active={curatedOrder !== null}
              busy={curateBusy}
            />
          )}

          {curatedOrder !== null && (
            <p className="text-[13px] font-serif text-ink dark:text-bright">
              Curated for “<span className="italic">{curatePrompt}</span>” —{" "}
              {displayed.length} {displayed.length === 1 ? "book" : "books"}, best match first.
            </p>
          )}

          {/* M1 honesty seam: SAY which ordering is active. A theme-ranked feed
              names the research it ranked to; a thin-signal fallback admits it
              is showing recency, never dressing it up as relevance. Only on the
              default servable shelf, and never while a curate prompt overrides. */}
          {curatedOrder === null && !loading && displayed.length > 0 && ordering === "theme" && (
            <p className="text-[13px] font-serif text-ink dark:text-bright" data-feed-ordering="theme">
              Ranked to your active research
              {themeTerms.length > 0 && (
                <>
                  {" — "}
                  <span className="italic">{themeTerms.slice(0, 4).join(", ")}</span>
                </>
              )}
              .
            </p>
          )}
          {curatedOrder === null && !loading && displayed.length > 0 && ordering === "recency" && (
            <p className="text-[13px] font-serif text-shadow-1 dark:text-moonlight" data-feed-ordering="recency">
              No active research to rank to yet — showing the most recently added first.
            </p>
          )}

          {error && (
            <p className="text-sm text-emperor border border-red-200 bg-red-50 px-3 py-2 rounded">
              {error}
            </p>
          )}

          {loading && (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">Loading…</p>
          )}

          {!loading && !error && displayed.length === 0 && (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">
              {curatedOrder !== null
                ? "No servable books matched that prompt. Try different words, or clear to see the whole shelf."
                : status === "servable"
                  ? "Nothing is readable in full on the shelf yet — the library only shows what can be legally aggregated. Check the Preview tab for titles you can sample, or bring your own PDF to read it here."
                  : "Nothing here."}
            </p>
          )}

          {displayed.length > 0 && (
            <section
              aria-label="Books"
              className="grid gap-5"
              style={{ gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))" }}
            >
              {displayed.map((b) => (
                <BookCard key={b.document_id} book={b} onOpen={open} />
              ))}
            </section>
          )}
    </div>
  );

  return (
    <div className={`flex flex-col ${inWindow ? "h-full" : "h-screen"}`}>
      {inWindow ? (
        // SPR-09 contract preserved: the host WorkspaceWindow owns the glass;
        // the body stays bg-transparent and is NOT re-glassed.
        <main className="flex-1 overflow-y-auto bg-transparent">{shelfBody}</main>
      ) : (
        // Full-page Read door landing → glass over the living scene.
        <GlassSurface as="main" className="flex-1 overflow-y-auto">
          {shelfBody}
        </GlassSurface>
      )}
    </div>
  );
}
