/**
 * Marketplace host-into-account mode — catalog → host → HTML library.
 * PDF may be purchase/ingest source only; view is always HTML.
 *
 * Residual (dj): client-side catalog filter (title/author/license) so the
 * operator can find a book before host/purchase without a second network hop.
 * Residual (dl): structured account library list + filter (HTML-first docs).
 * Residual (do): rehydrate document HTML via GET /documents/{id}/html so any
 * library row can open a hosted window without last-host session body.
 * Residual (dq): load account library on mount (not only after host).
 * Residual (dz): DecisionTreeDriverBadge — active model driver readout before
 * host/research (reading ≡ research model visibility).
 * Residual (qj): DecisionTreeDriverBadge promptText from hosted book body/title.
 * Residual (gi): Open Write HTML draft handoff from host-result + library
 * rows (marketplace → write flywheel; fl path).
 * Residual (qc / FUTURE-AGENT V5): dual handoff html_draft + twin_seed on host
 * and library Open Write (parity MO pz; seeds note-taker when empty).
 * Residual (gj): offline twin seed after host/purchase so marketplace books
 * enter the recursive note-taker substrate (parity with Write fz).
 * Residual (hl): offline-seed honesty machine attrs on marketplace twin seed
 * status (parity TwinNotes hh).
 * Residual (id): Settings deep-link for driver + twin seed readiness.
 * Residual (il): catalog HTML-first honesty metrics (no payment rails claim).
 * Residual (im): account library HTML-first metrics strip.
 * Residual (in): host-result metrics after host/purchase land.
 * Residual (io): knowledge-dense PD catalog expansion + source surface in UI
 * (project_gutenberg / standard_ebooks / marketplace_stub); filter includes source.
 * Residual (ip): host-land metrics include catalog knowledge source + recursive
 * note-taker substrate note after twin seed.
 * Residual (ir): prefer server catalog honesty (by_source / free_count /
 * payment_rails) when GET /marketplace/catalog provides them (iq).
 * Residual (is): free-PD quick filter + source-aware catalog filter UX for
 * knowledge-dense research books.
 * Residual (iu): host-result one-click floating deep research on hosted book
 * (reading ≡ research flywheel; decision-tree driver chokepoint).
 * Residual (iv): host-result deep research full window mode (parity hosted es).
 * Residual (iw): library row deep research launch parity (float|full).
 * Residual (iy): budget soft-gate on host/library DR launch (parity di/cs).
 * Residual (ja): DR status surfaces research_tier used for launch audit.
 * Residual (jb): reset budget force override when hosted document changes.
 * Residual (jc): prefill host DR depth tier from Settings depth-tier (parity gt/gs).
 * Residual (lw): research-domain subject tags + domain chip filter + by_subject
 * honesty (STEM PD spine: elements/principia/novum).
 * Residual (lx): knowledge-source chip filter (parity subject chips; composes
 * with free-PD + subject + text filter).
 * Residual (ly): open catalog as HTML asset window (project_catalog_html;
 * chip-aware free_only/subject/source filters).
 * Residual (mb): surface host usage_event (Antiek-bench book_qa) on host land.
 * Residual (mh): host-land metrics include catalog subjects for research-domain
 * continuity after host (parity subject chips).
 * Residual (mi): catalog HTML window id encodes active chips so filter-aware
 * projections do not clobber each other in the workspace.
 * Residual (mm): dual-gate L1–L4 checklist deep-link (parity mj/ml).
 * Residual (mo): twin seed body includes catalog subjects for domain-aware
 * recursive note-taker substrate after host.
 * Residual (mp): deep research goal_hint + prompt preview include catalog
 * subjects so DR inherits research-domain context (reading ≡ research).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { seedTwinNotes } from "../../api/engagement";
import {
  fetchAccountLibrary,
  fetchHostedDocumentHtml,
  fetchMarketplaceCatalog,
  hostBookIntoAccount,
  purchaseAndHost,
  type CatalogEntryRow,
  type HostResultResponse,
  type MarketplaceCatalogResponse,
} from "../../api/marketplaceHost";
import { DecisionTreeDriverBadge } from "../../components/engagement/DecisionTreeDriverBadge";
import {
  ResearchLaunchBudgetPanel,
  type ResearchLaunchBudgetProjection,
  type ResearchLaunchTier,
} from "../../components/engagement/ResearchLaunchBudgetPanel";
import { fetchDepthTiers } from "../../api/settings";
import { mapDepthTierToResearchTier } from "../../lib/researchTier";
import { openWindow } from "../../components/windows/openWindow";
import {
  buildMarketplaceWriteHref,
  plainTextFromHtml,
} from "../../workspace/twinWriteSeed";
import { launchFloatingDeepResearch } from "../Reading/launchFloatingDeepResearch";

type LibraryDoc = {
  document_id: string;
  title?: string;
  license_class?: string;
  view_format?: string;
};

export type MarketplaceHostProps = {
  ownerId?: string;
};

/** Offline demo body for purchased-book host (HTML bytes → base64). */
function demoPurchasedContentB64(title: string): string {
  const html = `<!DOCTYPE html><html><body data-view-format="html"><h1>${title}</h1><p>Hosted after manual purchase receipt (no live payment rails).</p></body></html>`;
  // browser + vitest both have btoa
  return typeof btoa === "function"
    ? btoa(html)
    : Buffer.from(html, "utf-8").toString("base64");
}

/** Residual (io): count catalog rows by knowledge source for audit metrics. */
export function groupCatalogBySource(
  rows: CatalogEntryRow[],
): Record<string, number> {
  const out: Record<string, number> = {};
  for (const e of rows) {
    const src = (e.source || "unknown").trim() || "unknown";
    out[src] = (out[src] || 0) + 1;
  }
  return out;
}

/** Residual (lw): multi-label subject counts for research-domain honesty. */
export function groupCatalogBySubject(
  rows: CatalogEntryRow[],
): Record<string, number> {
  const out: Record<string, number> = {};
  for (const e of rows) {
    for (const s of e.subjects || []) {
      const token = (s || "").trim().toLowerCase();
      if (!token) continue;
      out[token] = (out[token] || 0) + 1;
    }
  }
  return out;
}

export default function MarketplaceHost({
  ownerId = "operator",
}: MarketplaceHostProps) {
  const [entries, setEntries] = useState<CatalogEntryRow[]>([]);
  /** Residual (ir/lw): server honesty fields from catalog route (iq/lw). */
  const [catalogHonesty, setCatalogHonesty] = useState<{
    by_source?: Record<string, number>;
    by_subject?: Record<string, number>;
    public_domain_count?: number;
    purchased_count?: number;
    free_count?: number;
    payment_rails?: string;
  } | null>(null);
  const [hosted, setHosted] = useState<HostResultResponse | null>(null);
  const [libraryHtml, setLibraryHtml] = useState<string | null>(null);
  /** Residual (ly): last catalog HTML projection (full catalog on load). */
  const [catalogHtml, setCatalogHtml] = useState<string | null>(null);
  const [libraryDocs, setLibraryDocs] = useState<LibraryDoc[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [receiptRef, setReceiptRef] = useState("manual-order-token-demo");
  /** Residual (dj/is): substring filter over catalog title/author/license/source. */
  const [filterQuery, setFilterQuery] = useState("");
  /**
   * Residual (is): when true, show only free public_domain rows (research PD spine).
   * Composes with filterQuery; does not invent payment rails.
   */
  const [freePdOnly, setFreePdOnly] = useState(false);
  /**
   * Residual (lw): research-domain subject chip (empty = all domains).
   * Exact token match against entry.subjects; composes with freePdOnly + filterQuery.
   */
  const [subjectFilter, setSubjectFilter] = useState("");
  /**
   * Residual (lx): knowledge-source chip (empty = all sources).
   * Exact match against entry.source; composes with freePdOnly + subject + filterQuery.
   */
  const [sourceFilter, setSourceFilter] = useState("");
  /** Residual (dl): filter over account library document titles/ids. */
  const [libraryFilter, setLibraryFilter] = useState("");
  /** Residual (dk): auto-open hosted HTML window after successful host. */
  const [autoOpenWindow, setAutoOpenWindow] = useState(true);

  const filteredEntries = useMemo(() => {
    const q = filterQuery.trim().toLowerCase();
    const subject = subjectFilter.trim().toLowerCase();
    const source = sourceFilter.trim().toLowerCase();
    return entries.filter((e) => {
      // Residual (is): free public_domain research spine filter.
      if (freePdOnly) {
        if (!(e.license_class === "public_domain" && e.is_free)) return false;
      }
      // Residual (lw): exact research-domain subject chip.
      if (subject) {
        const subjects = (e.subjects || []).map((s) => s.toLowerCase());
        if (!subjects.includes(subject)) return false;
      }
      // Residual (lx): exact knowledge-source chip.
      if (source) {
        const entrySource = (e.source || "").trim().toLowerCase();
        if (entrySource !== source) return false;
      }
      if (!q) return true;
      // Residual (io/lw): include knowledge source + subjects in filter haystack.
      const subjHay = (e.subjects || []).join(" ");
      const hay =
        `${e.title} ${e.author} ${e.license_class} ${e.book_id} ${e.source} ${subjHay}`.toLowerCase();
      return hay.includes(q);
    });
  }, [entries, filterQuery, freePdOnly, subjectFilter, sourceFilter]);

  /**
   * Residual (io/ir): by_source breakdown — prefer server honesty when present.
   */
  const catalogBySource = useMemo(() => {
    if (
      catalogHonesty?.by_source &&
      Object.keys(catalogHonesty.by_source).length > 0
    ) {
      return catalogHonesty.by_source;
    }
    return groupCatalogBySource(entries);
  }, [catalogHonesty, entries]);

  /**
   * Residual (lw): by_subject breakdown — prefer server honesty when present.
   */
  const catalogBySubject = useMemo(() => {
    if (
      catalogHonesty?.by_subject &&
      Object.keys(catalogHonesty.by_subject).length > 0
    ) {
      return catalogHonesty.by_subject;
    }
    return groupCatalogBySubject(entries);
  }, [catalogHonesty, entries]);

  /** Residual (lw): sorted domain chips for research filter UI. */
  const subjectChipList = useMemo(() => {
    return Object.keys(catalogBySubject).sort((a, b) => a.localeCompare(b));
  }, [catalogBySubject]);

  /** Residual (lx): sorted knowledge-source chips for catalog filter UI. */
  const sourceChipList = useMemo(() => {
    return Object.keys(catalogBySource).sort((a, b) => a.localeCompare(b));
  }, [catalogBySource]);

  const filteredLibraryDocs = useMemo(() => {
    const q = libraryFilter.trim().toLowerCase();
    if (!q) return libraryDocs;
    return libraryDocs.filter((d) => {
      const hay =
        `${d.title || ""} ${d.document_id} ${d.license_class || ""}`.toLowerCase();
      return hay.includes(q);
    });
  }, [libraryDocs, libraryFilter]);

  const loadCatalog = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const cat: MarketplaceCatalogResponse = await fetchMarketplaceCatalog();
      setEntries(cat.entries);
      // Residual (ir/lw): retain server honesty fields when provided.
      setCatalogHonesty({
        by_source: cat.by_source,
        by_subject: cat.by_subject,
        public_domain_count: cat.public_domain_count,
        purchased_count: cat.purchased_count,
        free_count: cat.free_count,
        payment_rails: cat.payment_rails,
      });
      // Residual (ly): keep full-catalog HTML projection when provided.
      if (cat.html && cat.view_format === "html") {
        setCatalogHtml(cat.html);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  /** Residual (dq/dw): hydrate library list on enter so open-rehydrate works. */
  const [libraryLoadNote, setLibraryLoadNote] = useState<string | null>(null);
  // Residual (gj): twin seed status after host/purchase.
  const [twinSeedStatus, setTwinSeedStatus] = useState<string | null>(null);
  /** Residual (hl): machine-readable offline-seed honesty (parity TwinNotes hh). */
  const [twinSeedHonesty, setTwinSeedHonesty] = useState<{
    liveSeed: boolean;
    offlineHonest: boolean;
    seeded: boolean;
    seedSource: string;
    seedSkipped: string | null;
    assetId: string;
  } | null>(null);
  /** Residual (iu): floating DR launch status after host. */
  const [hostDrStatus, setHostDrStatus] = useState<string | null>(null);
  const [hostDrBusy, setHostDrBusy] = useState(false);
  /** Residual (iy): soft budget gate before marketplace DR launch. */
  const [hostDrBudgetWarn, setHostDrBudgetWarn] = useState(false);
  const [hostDrForceBudget, setHostDrForceBudget] = useState(false);
  const [hostDrTier, setHostDrTier] = useState<ResearchLaunchTier>("deep");
  const [hostDrPromptPreview, setHostDrPromptPreview] = useState("");
  /**
   * Residual (jc): Settings depth-tier prefill for host DR (pending|installed|none|error).
   */
  const [hostDrDepthPrefill, setHostDrDepthPrefill] = useState<
    "pending" | "installed" | "none" | "error"
  >("pending");
  const loadLibrary = useCallback(async () => {
    try {
      const lib = await fetchAccountLibrary(ownerId);
      if (lib.view_format !== "html") {
        throw new Error("library view_format must be html");
      }
      setLibraryHtml(lib.html);
      setLibraryDocs(lib.documents || []);
      setLibraryLoadNote(null);
    } catch (e) {
      // Residual (dw): non-fatal — catalog remains usable; quiet note not hard error.
      setLibraryLoadNote(
        e instanceof Error ? e.message : String(e),
      );
    }
  }, [ownerId]);

  useEffect(() => {
    void loadCatalog();
    void loadLibrary();
  }, [loadCatalog, loadLibrary]);

  // Residual (jc): prefill host DR tier from Settings depth-tier (parity Midnight Oil gt).
  useEffect(() => {
    let cancelled = false;
    void fetchDepthTiers()
      .then((resp) => {
        if (cancelled) return;
        const mapped = mapDepthTierToResearchTier(resp.active_depth_tier);
        if (mapped) {
          setHostDrTier(mapped);
          setHostDrDepthPrefill("installed");
        } else {
          setHostDrDepthPrefill("none");
        }
      })
      .catch(() => {
        if (!cancelled) setHostDrDepthPrefill("error");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function openHostedWindow(opts: {
    document_id: string;
    title?: string;
    html: string;
    view_format?: string;
    license_class?: string;
    owner_id?: string;
    source?: string;
  }) {
    if ((opts.view_format || "html") !== "html" || !opts.html) return;
    openWindow(
      "hosted_html_document",
      {
        document_id: opts.document_id,
        title: opts.title,
        html: opts.html,
        view_format: "html",
        license_class: opts.license_class,
        owner_id: opts.owner_id,
        source: opts.source || "marketplace_host",
      },
      {
        id: `win:hosted:${opts.document_id}`,
        title: opts.title || "Hosted book",
      },
    );
  }

  /**
   * Residual (ly): open catalog as HTML asset — re-fetch with active chips so
   * the projected document matches free-PD / subject / source filters.
   */
  async function openCatalogAsHtml() {
    setBusy(true);
    setError(null);
    try {
      const cat = await fetchMarketplaceCatalog({
        freeOnly: freePdOnly,
        subject: subjectFilter || undefined,
        source: sourceFilter || undefined,
        includeHtml: true,
      });
      if (cat.view_format !== "html" || !cat.html?.trim()) {
        throw new Error("catalog HTML projection missing or non-html");
      }
      if (cat.html.trimStart().toLowerCase().startsWith("%pdf")) {
        throw new Error("catalog view must not be PDF");
      }
      setCatalogHtml(cat.html);
      // Residual (mi): chip-aware document id so filtered HTML opens uniquely.
      const filterKey = [
        freePdOnly ? "freepd" : "all",
        subjectFilter || "any-subject",
        sourceFilter || "any-source",
      ].join("_");
      const catalogDocId = `marketplace-catalog-${filterKey}`;
      openHostedWindow({
        document_id: catalogDocId,
        title: `Marketplace catalog (HTML) · ${filterKey}`,
        html: cat.html,
        view_format: "html",
        license_class: "public_domain",
        owner_id: ownerId,
        source: "marketplace_catalog",
      });
    } catch (e) {
      // Fallback: last full-catalog projection if chip-aware fetch fails.
      if (catalogHtml?.trim()) {
        openHostedWindow({
          document_id: "marketplace-catalog-fallback",
          title: "Marketplace catalog (HTML)",
          html: catalogHtml,
          view_format: "html",
          license_class: "public_domain",
          owner_id: ownerId,
          source: "marketplace_catalog",
        });
        setError(
          e instanceof Error
            ? `catalog filter HTML failed (${e.message}); opened last full catalog`
            : String(e),
        );
      } else {
        setError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setBusy(false);
    }
  }

  function hostDrSelectionFromHtml(
    html: string,
    title: string,
    domains?: string[],
  ): string {
    const plain = (html || "")
      .replace(/<[^>]+>/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 800);
    // Residual (mp): domain prefix for budget projection + selection context.
    const domainPrefix =
      domains && domains.length > 0
        ? `Research domains: ${domains.join(", ")}. `
        : "";
    if (plain.length >= 3) return (domainPrefix + plain).slice(0, 900);
    return (
      domainPrefix +
      `Key claims and open questions in “${title}” for deep research.`
    );
  }

  /** Residual (mp): catalog subjects for a hosted book_id (empty if unknown). */
  function catalogSubjectsForBook(bookId: string | undefined): string[] {
    if (!bookId) return [];
    const entry = entries.find((e) => e.book_id === bookId);
    return (entry?.subjects || []).filter(Boolean);
  }

  /**
   * Residual (iu/iv/iy/mp): one-click deep research on hosted HTML book.
   * Uses decision-tree driver chokepoint; selection from title/body preview.
   * Soft budget gate when projection would exceed (force override available).
   * Domain subjects from catalog join goal_hint for domain-aware research.
   */
  async function onDeepResearchHostedBook(
    result: HostResultResponse,
    viewMode: "floating" | "full" = "floating",
  ) {
    if (result.view_format !== "html") {
      setError("view_format must be html — PDF is not a research surface");
      return;
    }
    if (hostDrBudgetWarn && !hostDrForceBudget) {
      setHostDrStatus(
        "Projected cost may exceed remaining daily budget — enable force override or reduce depth tier.",
      );
      return;
    }
    const title = (result.title || result.document_id || "hosted book").trim();
    const domains = catalogSubjectsForBook(result.book_id);
    const selection = hostDrSelectionFromHtml(
      result.html || "",
      title,
      domains,
    );
    const domainClause =
      domains.length > 0 ? ` · domains=${domains.join(",")}` : "";
    setHostDrBusy(true);
    setHostDrStatus(null);
    setError(null);
    try {
      const out = await launchFloatingDeepResearch({
        asset_id: result.document_id,
        selection_text: selection,
        goal_hint: `Wrestle claims and cite evidence in “${title}” (marketplace HTML host · tier=${hostDrTier}${domainClause}).`,
        view_mode: viewMode,
        research_tier: hostDrTier,
      });
      if (out.view_format !== "html") {
        throw new Error("deep research view_format must be html");
      }
      setHostDrStatus(
        `Deep research launched (${viewMode}) · tier=${hostDrTier}${domainClause} · session=${out.session_id} · spawn=${out.spawn_id} · window=${out.window_id}`,
      );
    } catch (e) {
      setHostDrStatus(
        e instanceof Error ? e.message : "Deep research launch failed",
      );
    } finally {
      setHostDrBusy(false);
    }
  }

  /** Residual (iy/jb/mp): keep budget panel prompt in sync; reset force on host change. */
  useEffect(() => {
    // Residual (jb): new host must not inherit prior force-over-budget override.
    setHostDrForceBudget(false);
    setHostDrBudgetWarn(false);
    setHostDrStatus(null);
    if (!hosted?.html) {
      setHostDrPromptPreview("");
      return;
    }
    const title = (hosted.title || hosted.document_id || "hosted book").trim();
    const domains = catalogSubjectsForBook(hosted.book_id);
    setHostDrPromptPreview(
      hostDrSelectionFromHtml(hosted.html, title, domains),
    );
  }, [hosted?.document_id, hosted?.html, hosted?.title, hosted?.book_id, entries]);

  /**
   * Residual (iw): deep research from library row — rehydrate HTML then launch.
   */
  async function onDeepResearchLibraryDoc(
    doc: LibraryDoc,
    viewMode: "floating" | "full" = "floating",
  ) {
    if ((doc.view_format || "html") !== "html") {
      setError("view_format must be html — PDF is not a research surface");
      return;
    }
    setHostDrBusy(true);
    setHostDrStatus(null);
    setError(null);
    try {
      let html = "";
      let title = doc.title || doc.document_id;
      if (
        hosted &&
        hosted.document_id === doc.document_id &&
        hosted.html &&
        hosted.view_format === "html"
      ) {
        html = hosted.html;
        title = hosted.title || title;
      } else {
        const body = await fetchHostedDocumentHtml(doc.document_id);
        if (body.view_format !== "html") {
          throw new Error("document view_format must be html");
        }
        html = body.html || "";
        title = body.title || title;
      }
      await onDeepResearchHostedBook(
        {
          document_id: doc.document_id,
          owner_id: ownerId,
          book_id: doc.document_id,
          content_hash: "",
          title: title || doc.document_id,
          license_class: doc.license_class || "unknown",
          already_hosted: true,
          source_format: "html",
          library_document_ids: [doc.document_id],
          view_format: "html",
          html,
        },
        viewMode,
      );
    } catch (e) {
      setHostDrStatus(
        e instanceof Error ? e.message : "Library deep research failed",
      );
      setHostDrBusy(false);
    }
  }

  /** Residual (do): fetch HTML body then open reading window for any library doc. */
  async function onOpenLibraryDoc(doc: LibraryDoc) {
    if ((doc.view_format || "html") !== "html") {
      setError("view_format must be html — PDF is not a reading surface");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      // Prefer in-session host body when it matches (avoids extra round-trip).
      if (
        hosted &&
        hosted.document_id === doc.document_id &&
        hosted.html &&
        hosted.view_format === "html"
      ) {
        openHostedWindow({
          document_id: hosted.document_id,
          title: hosted.title || doc.title,
          html: hosted.html,
          view_format: "html",
          license_class: hosted.license_class || doc.license_class,
          owner_id: hosted.owner_id || ownerId,
          source: "marketplace_library",
        });
        return;
      }
      const body = await fetchHostedDocumentHtml(doc.document_id);
      if (body.view_format !== "html") {
        throw new Error("hosted document view_format must be html");
      }
      if (!body.html?.trim()) {
        throw new Error("hosted document HTML body empty");
      }
      openHostedWindow({
        document_id: body.document_id || doc.document_id,
        title: body.title || doc.title || doc.document_id,
        html: body.html,
        view_format: "html",
        license_class: body.license_class || doc.license_class,
        owner_id: ownerId,
        source: "marketplace_library_rehydrate",
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  /** Residual (gj)/(hl)/(mo): offline twin seed for hosted book (non-fatal; honest). */
  async function seedHostedTwins(result: HostResultResponse) {
    setTwinSeedStatus(null);
    setTwinSeedHonesty(null);
    try {
      const plain = (result.html || "")
        .replace(/<[^>]+>/g, " ")
        .replace(/\s+/g, " ")
        .trim()
        .slice(0, 2000);
      // Residual (mo): domain subjects from catalog for recursive note-taker context.
      const entry = entries.find((e) => e.book_id === result.book_id);
      const subjects = (entry?.subjects || []).filter(Boolean);
      const subjectPrefix =
        subjects.length > 0
          ? `Research domains: ${subjects.join(", ")}.\n\n`
          : "";
      const bodyText =
        (subjectPrefix + (plain || result.title || result.document_id)).slice(
          0,
          2200,
        );
      const seeded = await seedTwinNotes({
        asset_id: result.document_id,
        title: result.title || result.document_id,
        body_text: bodyText,
        include_html: false,
        force_offline: true,
      });
      const liveSeed = Boolean(seeded.live_seed);
      const offlineHonest = !liveSeed;
      const seedSource =
        (seeded.seed_source && String(seeded.seed_source)) ||
        (liveSeed
          ? "engagement_spine.twin.seed_twins_for_asset.live"
          : "engagement_spine.twin.seed_twins_for_asset");
      setTwinSeedHonesty({
        liveSeed,
        offlineHonest,
        seeded: seeded.seeded !== false,
        seedSource,
        seedSkipped: seeded.seed_skipped ?? null,
        assetId: result.document_id,
      });
      if (seeded.seeded === false) {
        setTwinSeedStatus(
          `Twin seed skipped${seeded.seed_skipped ? `: ${seeded.seed_skipped}` : ""}`,
        );
      } else {
        setTwinSeedStatus(
          offlineHonest
            ? `Seed mode: offline-honest identity stubs for ${result.document_id} — recursive note-taker (not live note_taker)`
            : `Seed mode: live note_taker injector landed for ${result.document_id}`,
        );
      }
    } catch (e) {
      setTwinSeedHonesty(null);
      setTwinSeedStatus(
        e instanceof Error ? e.message : "Twin seed failed (non-fatal)",
      );
    }
  }

  async function onHost(bookId: string) {
    setBusy(true);
    setError(null);
    setTwinSeedStatus(null);
    setTwinSeedHonesty(null);
    try {
      const result = await hostBookIntoAccount({
        owner_id: ownerId,
        book_id: bookId,
      });
      if (result.view_format !== "html") {
        throw new Error("hosted view_format must be html");
      }
      setHosted(result);
      const lib = await fetchAccountLibrary(ownerId);
      setLibraryHtml(lib.html);
      setLibraryDocs(lib.documents || []);
      // Residual (gj): recursive note-taker substrate for the book asset.
      await seedHostedTwins(result);
      // Residual (dk): seamless port into reading surface.
      if (autoOpenWindow) {
        openHostedWindow({
          document_id: result.document_id,
          title: result.title,
          html: result.html,
          view_format: result.view_format,
          license_class: result.license_class,
          owner_id: result.owner_id,
          source: "marketplace_host",
        });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onPurchaseAndHost(entry: CatalogEntryRow) {
    setBusy(true);
    setError(null);
    setTwinSeedStatus(null);
    setTwinSeedHonesty(null);
    try {
      const result = await purchaseAndHost({
        owner_id: ownerId,
        book_id: entry.book_id,
        opaque_reference: receiptRef.trim() || "manual-order-token-demo",
        content_b64: demoPurchasedContentB64(entry.title),
        note: "Manual purchase receipt (residual bg UI)",
      });
      if (result.view_format !== "html") {
        throw new Error("hosted view_format must be html");
      }
      setHosted(result);
      const lib = await fetchAccountLibrary(ownerId);
      setLibraryHtml(lib.html);
      setLibraryDocs(lib.documents || []);
      await seedHostedTwins(result);
      if (autoOpenWindow) {
        openHostedWindow({
          document_id: result.document_id,
          title: result.title,
          html: result.html,
          view_format: result.view_format,
          license_class: result.license_class,
          owner_id: result.owner_id,
          source: "marketplace_host",
        });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="h-full overflow-y-auto p-6" data-view-format="html" data-testid="marketplace-host-mode">
      <header className="mb-6 space-y-2">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="space-y-1">
            <h1 className="text-2xl font-semibold">Marketplace · host into account</h1>
            <p className="text-sm opacity-80">
              Host public-domain catalog books into your Antiek library. Purchased
              titles use a manual receipt token (no live payment rails). Human view
              is HTML, never PDF.
            </p>
          </div>
          {/* Residual (dz): Settings decision-tree driver (advisory readout). */}
          <div data-testid="marketplace-driver-badge-mount" data-view-format="html">
            <DecisionTreeDriverBadge
              researchTier={hostDrTier}
              promptText={
                hosted?.html
                  ? plainTextFromHtml(hosted.html).slice(0, 4000)
                  : hosted?.title
                    ? `marketplace DR · ${hosted.title}`
                    : undefined
              }
            />
            {/* Residual (id): Settings deep-link (driver + twin seed readiness). */}
            <p className="mt-1 text-[11px] font-mono space-x-3">
              <a
                href="/settings#decision-tree-panel"
                data-testid="marketplace-settings-link"
                className="underline opacity-80 hover:opacity-100"
                title="Open Settings decision-tree: driver, budget bar; twin seed readiness is on same page"
              >
                Settings · driver & twin seed
              </a>
              {/* Residual (mm): dual-gate checklist prep (never enables L1–L4). */}
              <a
                href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md"
                data-testid="marketplace-dual-gate-checklist-link"
                className="underline opacity-80 hover:opacity-100"
                title="Dual-gate L1–L4 operator checklist (prep only)"
              >
                Dual-gate L1–L4 checklist
              </a>
            </p>
          </div>
        </div>
      </header>

      <div className="flex flex-wrap gap-3 items-end mb-4">
        <button type="button" onClick={() => void loadCatalog()} disabled={busy}>
          Refresh catalog
        </button>
        {/* Residual (ly): browse catalog as HTML-first asset window. */}
        <button
          type="button"
          data-testid="catalog-open-html"
          onClick={() => void openCatalogAsHtml()}
          disabled={busy}
          title="Open catalog as HTML (respects free-PD / domain / source chips)"
        >
          Open catalog as HTML
        </button>
        <label className="flex flex-col gap-1 text-sm font-mono">
          <span className="text-[11px] uppercase opacity-70">
            Filter catalog
          </span>
          <input
            type="search"
            data-testid="catalog-filter"
            value={filterQuery}
            onChange={(e) => setFilterQuery(e.target.value)}
            placeholder="Title, author, license, source, subject…"
            className="border rounded px-2 py-1 min-w-[16rem]"
            disabled={busy}
            aria-label="Filter catalog"
          />
        </label>
        {/* Residual (is): free public_domain quick filter for research spine. */}
        <label className="flex items-center gap-2 text-sm font-mono pb-1">
          <input
            type="checkbox"
            data-testid="catalog-free-pd-only"
            checked={freePdOnly}
            onChange={(e) => setFreePdOnly(e.target.checked)}
            disabled={busy}
          />
          Free public-domain only
        </label>
        {/* Residual (lw): research-domain subject chips (STEM / philosophy / …). */}
        <div
          className="flex flex-wrap gap-1 items-center pb-1"
          data-testid="catalog-subject-chips"
          role="group"
          aria-label="Filter catalog by research domain"
        >
          <button
            type="button"
            data-testid="catalog-subject-all"
            data-active={String(subjectFilter === "")}
            className={`text-[11px] font-mono border rounded px-2 py-0.5 ${
              subjectFilter === "" ? "opacity-100 font-semibold" : "opacity-70"
            }`}
            onClick={() => setSubjectFilter("")}
            disabled={busy}
          >
            all domains
          </button>
          {subjectChipList.map((subj) => (
            <button
              key={subj}
              type="button"
              data-testid={`catalog-subject-${subj}`}
              data-active={String(subjectFilter === subj)}
              className={`text-[11px] font-mono border rounded px-2 py-0.5 ${
                subjectFilter === subj
                  ? "opacity-100 font-semibold"
                  : "opacity-70"
              }`}
              onClick={() =>
                setSubjectFilter((prev) => (prev === subj ? "" : subj))
              }
              disabled={busy}
            >
              {subj}
              {catalogBySubject[subj] != null
                ? ` (${catalogBySubject[subj]})`
                : ""}
            </button>
          ))}
        </div>
        {/* Residual (lx): knowledge-source chips (project_gutenberg / standard_ebooks / …). */}
        <div
          className="flex flex-wrap gap-1 items-center pb-1"
          data-testid="catalog-source-chips"
          role="group"
          aria-label="Filter catalog by knowledge source"
        >
          <button
            type="button"
            data-testid="catalog-source-all"
            data-active={String(sourceFilter === "")}
            className={`text-[11px] font-mono border rounded px-2 py-0.5 ${
              sourceFilter === "" ? "opacity-100 font-semibold" : "opacity-70"
            }`}
            onClick={() => setSourceFilter("")}
            disabled={busy}
          >
            all sources
          </button>
          {sourceChipList.map((src) => (
            <button
              key={src}
              type="button"
              data-testid={`catalog-source-${src}`}
              data-active={String(sourceFilter === src)}
              className={`text-[11px] font-mono border rounded px-2 py-0.5 ${
                sourceFilter === src
                  ? "opacity-100 font-semibold"
                  : "opacity-70"
              }`}
              onClick={() =>
                setSourceFilter((prev) => (prev === src ? "" : src))
              }
              disabled={busy}
            >
              {src}
              {catalogBySource[src] != null ? ` (${catalogBySource[src]})` : ""}
            </button>
          ))}
        </div>
        <label className="flex flex-col gap-1 text-sm font-mono">
          <span className="text-[11px] uppercase opacity-70">
            Purchase receipt ref
          </span>
          <input
            type="text"
            data-testid="purchase-receipt-ref"
            value={receiptRef}
            onChange={(e) => setReceiptRef(e.target.value)}
            className="border rounded px-2 py-1 min-w-[16rem]"
            disabled={busy}
          />
        </label>
        <label
          className="flex items-center gap-2 text-sm font-mono"
          data-testid="auto-open-hosted-window"
        >
          <input
            type="checkbox"
            checked={autoOpenWindow}
            onChange={(e) => setAutoOpenWindow(e.target.checked)}
            disabled={busy}
          />
          Auto-open hosted book window
        </label>
      </div>

      {error ? (
        <p className="mt-4 text-red-600" role="alert">
          {error}
        </p>
      ) : null}
      {libraryLoadNote ? (
        <p
          className="mt-2 text-sm opacity-70 font-mono"
          data-testid="library-load-note"
          role="status"
        >
          Library load note: {libraryLoadNote}
        </p>
      ) : null}

      <p
        className="text-[11px] font-mono opacity-70"
        data-testid="catalog-filter-count"
      >
        Showing {filteredEntries.length} of {entries.length}
      </p>
      {/* Residual (il/io): HTML-first catalog honesty + by_source audit. */}
      <div
        className="text-[11px] font-mono opacity-80 mb-2 space-y-0.5"
        data-testid="marketplace-catalog-metrics"
        data-entry-count={String(entries.length)}
        data-filtered-count={String(filteredEntries.length)}
        data-source-count={String(Object.keys(catalogBySource).length)}
        data-public-domain-count={String(
          catalogHonesty?.public_domain_count ??
            entries.filter((e) => e.license_class === "public_domain").length,
        )}
        data-free-count={String(
          catalogHonesty?.free_count ??
            entries.filter((e) => e.is_free).length,
        )}
        data-honesty-source={
          catalogHonesty?.by_source ? "server" : "client"
        }
        data-free-pd-only={String(freePdOnly)}
        data-subject-filter={subjectFilter || "all"}
        data-subject-count={String(Object.keys(catalogBySubject).length)}
        data-source-filter={sourceFilter || "all"}
        data-view-format="html"
        data-payment-rails={
          catalogHonesty?.payment_rails || "manual_receipt_only"
        }
        role="status"
      >
        <p>
          Catalog · entries={entries.length} · filtered={filteredEntries.length}{" "}
          · sources={Object.keys(catalogBySource).length} · subjects=
          {Object.keys(catalogBySubject).length} · free=
          {catalogHonesty?.free_count ??
            entries.filter((e) => e.is_free).length}{" "}
          · human view=HTML · payment=
          {catalogHonesty?.payment_rails || "manual_receipt_only"} (no live
          rails)
        </p>
        {Object.keys(catalogBySource).length > 0 ? (
          <p data-testid="marketplace-catalog-by-source">
            By source:{" "}
            {Object.entries(catalogBySource)
              .map(([src, n]) => `${src}=${n}`)
              .join(" · ")}
          </p>
        ) : null}
        {Object.keys(catalogBySubject).length > 0 ? (
          <p data-testid="marketplace-catalog-by-subject">
            By subject:{" "}
            {Object.entries(catalogBySubject)
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([subj, n]) => `${subj}=${n}`)
              .join(" · ")}
          </p>
        ) : null}
      </div>

      <ul className="mt-4 space-y-2" data-testid="catalog-list">
        {filteredEntries.map((e) => (
          <li
            key={e.book_id}
            className="border rounded p-3 flex justify-between gap-4"
            data-testid={`catalog-entry-${e.book_id}`}
            data-view-format="html"
            data-license-class={e.license_class}
            data-is-free={String(Boolean(e.is_free))}
            data-source={e.source || "unknown"}
            data-source-format="html"
            data-subjects={(e.subjects || []).join(",") || "none"}
          >
            <div>
              <strong>{e.title}</strong>
              <div className="text-sm opacity-80">
                {e.author} · {e.license_class}
                {e.is_free ? " · free" : ""}
                {" · source="}
                {e.source || "unknown"}
                {(e.subjects || []).length > 0
                  ? ` · subjects=${(e.subjects || []).join(",")}`
                  : ""}
                {" · HTML host"}
              </div>
            </div>
            {e.license_class === "public_domain" || e.is_free ? (
              <button
                type="button"
                disabled={busy}
                onClick={() => void onHost(e.book_id)}
              >
                Host into account
              </button>
            ) : (
              <button
                type="button"
                data-testid={`purchase-host-${e.book_id}`}
                disabled={busy || !receiptRef.trim()}
                onClick={() => void onPurchaseAndHost(e)}
              >
                Purchase + host
              </button>
            )}
          </li>
        ))}
      </ul>
      {entries.length > 0 && filteredEntries.length === 0 ? (
        <p className="text-sm opacity-70" data-testid="catalog-filter-empty">
          No catalog matches
          {filterQuery.trim() ? ` for “${filterQuery.trim()}”` : ""}
          {subjectFilter ? ` in domain “${subjectFilter}”` : ""}
          {sourceFilter ? ` from source “${sourceFilter}”` : ""}
          {freePdOnly ? " (free public-domain only)" : ""}.
        </p>
      ) : null}

      {hosted ? (
        <section className="mt-8 space-y-2" data-testid="host-result">
          <h2 className="text-lg font-medium">Hosted {hosted.document_id}</h2>
          {/* Residual (in/ip): host land metrics + catalog knowledge source. */}
          <div
            data-testid="marketplace-host-metrics"
            data-document-id={hosted.document_id}
            data-already-hosted={String(Boolean(hosted.already_hosted))}
            data-license-class={hosted.license_class ?? ""}
            data-view-format={hosted.view_format ?? "html"}
            data-book-id={hosted.book_id ?? ""}
            data-catalog-source={
              entries.find((e) => e.book_id === hosted.book_id)?.source ||
              "unknown"
            }
            data-usage-task-class={hosted.usage_event?.task_class || ""}
            data-usage-source={hosted.usage_event?.source || ""}
            data-subjects={
              (
                entries.find((e) => e.book_id === hosted.book_id)?.subjects ||
                []
              ).join(",") || "none"
            }
            data-twin-seeded={
              twinSeedStatus
                ? twinSeedHonesty?.seeded === false
                  ? "skipped"
                  : "true"
                : "pending"
            }
            role="status"
            className="font-mono text-[11px] opacity-80"
          >
            Host land · document={hosted.document_id} · already=
            {String(Boolean(hosted.already_hosted))} · view=
            {hosted.view_format} · catalog_source=
            {entries.find((e) => e.book_id === hosted.book_id)?.source ||
              "unknown"}
            · subjects=
            {(
              entries.find((e) => e.book_id === hosted.book_id)?.subjects || []
            ).join(",") || "none"}
          </div>
          {/* Residual (ip): recursive note-taker substrate after host. */}
          <p
            className="text-[11px] font-mono opacity-80"
            data-testid="marketplace-host-research-substrate"
            data-view-format="html"
            role="status"
          >
            Research substrate: HTML host + offline twin seed path (recursive
            note-taker) — ready for floating deep research on this book
          </p>
          {/* Residual (mb): Antiek-bench usage feed honesty after host. */}
          {hosted.usage_event ? (
            <p
              className="text-[11px] font-mono opacity-80"
              data-testid="marketplace-host-usage-event"
              data-task-class={hosted.usage_event.task_class || ""}
              data-outcome={hosted.usage_event.outcome || ""}
              data-source={hosted.usage_event.source || ""}
              data-propose-not-promote="true"
              data-view-format="html"
              role="status"
            >
              Antiek-bench usage: task_class=
              {hosted.usage_event.task_class || "?"} · outcome=
              {hosted.usage_event.outcome || "?"} · source=
              {hosted.usage_event.source || "?"} · propose≠promote (Settings
              suite proposal)
            </p>
          ) : null}
          <p>
            {hosted.already_hosted ? "Already hosted" : "Newly hosted"} ·{" "}
            {hosted.license_class} · view_format={hosted.view_format}
          </p>
          {/* Residual (iy/jc): budget projection soft-gate + Settings depth prefill. */}
          <div
            className="space-y-2 border rounded p-3"
            data-testid="marketplace-host-dr-budget-mount"
            data-view-format="html"
            data-research-tier={hostDrTier}
            data-depth-prefill={hostDrDepthPrefill}
            data-domains={
              catalogSubjectsForBook(hosted.book_id).join(",") || "none"
            }
          >
            <p
              className="text-[11px] font-mono opacity-80"
              data-testid="marketplace-host-dr-depth-prefill"
              role="status"
            >
              Depth prefill: {hostDrDepthPrefill}
              {hostDrDepthPrefill === "installed"
                ? ` → ${hostDrTier}`
                : hostDrDepthPrefill === "none"
                  ? " (default deep)"
                  : ""}
            </p>
            <ResearchLaunchBudgetPanel
              promptText={hostDrPromptPreview || hosted.title || "hosted book"}
              researchTier={hostDrTier}
              allowTierPick
              onResearchTierChange={setHostDrTier}
              onProjectionChange={(p: ResearchLaunchBudgetProjection) => {
                setHostDrBudgetWarn(p.wouldExceedBudget === true);
              }}
            />
            {hostDrBudgetWarn ? (
              <label className="flex items-center gap-2 text-[11px] font-mono">
                <input
                  type="checkbox"
                  data-testid="marketplace-host-dr-force-budget"
                  checked={hostDrForceBudget}
                  onChange={(e) => setHostDrForceBudget(e.target.checked)}
                />
                Force deep research despite budget projection
              </label>
            ) : null}
          </div>
          {/* Residual (bt/dk): open hosted HTML book in a floating window. */}
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              data-testid="open-hosted-in-window"
              disabled={hosted.view_format !== "html" || !hosted.html}
              onClick={() => {
                if (hosted.view_format !== "html") {
                  setError("view_format must be html — PDF is not a reading surface");
                  return;
                }
                openHostedWindow({
                  document_id: hosted.document_id,
                  title: hosted.title,
                  html: hosted.html,
                  view_format: hosted.view_format,
                  license_class: hosted.license_class,
                  owner_id: hosted.owner_id,
                  source: "marketplace_host",
                });
              }}
              className="px-3 py-1.5 rounded border border-ink dark:border-bright text-sm font-mono hover:bg-ink/5 dark:hover:bg-bright/10 disabled:opacity-50"
            >
              Open hosted book in window
            </button>
            {/* Residual (gi): handoff hosted HTML into Write mode (fl path). */}
            {hosted.view_format === "html" && hosted.document_id ? (
              <a
                href={buildMarketplaceWriteHref({
                  documentId: hosted.document_id,
                  title: hosted.title,
                  html: hosted.html,
                })}
                data-testid="marketplace-open-write"
                data-view-format="html"
                data-document-id={hosted.document_id}
                data-has-twin-seed="1"
                className="px-3 py-1.5 rounded border border-ink dark:border-bright text-sm font-mono underline hover:bg-ink/5 dark:hover:bg-bright/10"
                title="Open Write with hosted book as HTML draft + twin_seed (seeds note-taker when empty)"
              >
                Open Write (HTML draft)
              </a>
            ) : null}
            {/* Residual (iu/iv): deep research floating | full on hosted book. */}
            <button
              type="button"
              data-testid="marketplace-host-deep-research"
              data-view-format="html"
              data-document-id={hosted.document_id}
              data-view-mode="floating"
              disabled={
                hostDrBusy ||
                busy ||
                hosted.view_format !== "html" ||
                !hosted.document_id ||
                (hostDrBudgetWarn && !hostDrForceBudget)
              }
              onClick={() => void onDeepResearchHostedBook(hosted, "floating")}
              className="px-3 py-1.5 rounded border border-ink dark:border-bright text-sm font-mono hover:bg-ink/5 dark:hover:bg-bright/10 disabled:opacity-50"
              title="Launch floating deep research on this hosted HTML book"
            >
              {hostDrBusy ? "Launching…" : "Deep research (float)"}
            </button>
            <button
              type="button"
              data-testid="marketplace-host-deep-research-full"
              data-view-format="html"
              data-document-id={hosted.document_id}
              data-view-mode="full"
              disabled={
                hostDrBusy ||
                busy ||
                hosted.view_format !== "html" ||
                !hosted.document_id ||
                (hostDrBudgetWarn && !hostDrForceBudget)
              }
              onClick={() => void onDeepResearchHostedBook(hosted, "full")}
              className="px-3 py-1.5 rounded border border-ink dark:border-bright text-sm font-mono hover:bg-ink/5 dark:hover:bg-bright/10 disabled:opacity-50"
              title="Launch full working-region deep research on this hosted HTML book"
            >
              {hostDrBusy ? "Launching…" : "Deep research (full)"}
            </button>
          </div>
          {hostDrStatus ? (
            <p
              className="text-[11px] font-mono opacity-80"
              data-testid="marketplace-host-dr-status"
              data-research-tier={hostDrTier}
              data-view-format="html"
              role="status"
            >
              {hostDrStatus}
            </p>
          ) : null}
          {/* Residual (gj)/(hl): twin seed status + offline-honesty attrs. */}
          {twinSeedStatus ? (
            <p
              className="text-[11px] font-mono opacity-80"
              data-testid="marketplace-twin-seed-status"
              data-offline-honest={
                twinSeedHonesty
                  ? String(twinSeedHonesty.offlineHonest)
                  : undefined
              }
              data-live-seed={
                twinSeedHonesty ? String(twinSeedHonesty.liveSeed) : undefined
              }
              data-seeded={
                twinSeedHonesty ? String(twinSeedHonesty.seeded) : undefined
              }
              data-seed-source={twinSeedHonesty?.seedSource}
              data-seed-skipped={twinSeedHonesty?.seedSkipped ?? undefined}
              data-force-offline="true"
              data-asset-id={twinSeedHonesty?.assetId}
              role="status"
            >
              {twinSeedStatus}
            </p>
          ) : null}
          <div
            className="prose border rounded p-3 text-sm"
            data-testid="hosted-html"
            dangerouslySetInnerHTML={{ __html: hosted.html }}
          />
        </section>
      ) : null}

      {libraryDocs.length > 0 || libraryHtml ? (
        <section className="mt-6 space-y-3" data-testid="account-library">
          <h2 className="text-lg font-medium">Library</h2>
          {/* Residual (dl): structured list + filter for hosted HTML docs. */}
          <label className="flex flex-col gap-1 text-sm font-mono max-w-md">
            <span className="text-[11px] uppercase opacity-70">
              Filter library
            </span>
            <input
              type="search"
              data-testid="library-filter"
              value={libraryFilter}
              onChange={(e) => setLibraryFilter(e.target.value)}
              placeholder="Title or document id…"
              className="border rounded px-2 py-1"
              aria-label="Filter library"
            />
          </label>
          <p
            className="text-[11px] font-mono opacity-70"
            data-testid="library-filter-count"
          >
            Showing {filteredLibraryDocs.length} of {libraryDocs.length}
          </p>
          {/* Residual (im): HTML-first account library metrics. */}
          <div
            className="text-[11px] font-mono opacity-80"
            data-testid="marketplace-library-metrics"
            data-doc-count={String(libraryDocs.length)}
            data-filtered-count={String(filteredLibraryDocs.length)}
            data-view-format="html"
            role="status"
          >
            Library · docs={libraryDocs.length} · filtered=
            {filteredLibraryDocs.length} · human view=HTML
          </div>
          <ul className="space-y-2" data-testid="library-doc-list">
            {filteredLibraryDocs.map((d) => (
              <li
                key={d.document_id}
                className="border rounded p-2 flex flex-wrap justify-between gap-2 items-center"
                data-testid={`library-doc-${d.document_id}`}
                data-view-format="html"
              >
                <div className="text-sm">
                  <strong>{d.title || d.document_id}</strong>
                  <div className="font-mono text-[11px] opacity-70">
                    {d.document_id}
                    {d.license_class ? ` · ${d.license_class}` : ""}
                    {" · "}
                    {(d.view_format || "html") === "html" ? "HTML" : d.view_format}
                    {" · not PDF"}
                  </div>
                </div>
                {(d.view_format || "html") === "html" ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      data-testid={`library-open-${d.document_id}`}
                      className="text-xs font-mono border rounded px-2 py-1"
                      disabled={busy}
                      onClick={() => void onOpenLibraryDoc(d)}
                    >
                      Open window
                    </button>
                    {/* Residual (gi): library → Write HTML draft handoff. */}
                    <a
                      href={buildMarketplaceWriteHref({
                        documentId: d.document_id,
                        title: d.title,
                        html: null,
                      })}
                      data-testid={`library-open-write-${d.document_id}`}
                      data-view-format="html"
                      data-document-id={d.document_id}
                      data-has-twin-seed="1"
                      className="text-xs font-mono border rounded px-2 py-1 underline"
                      title="Open Write with library document as HTML draft + twin_seed"
                    >
                      Open Write
                    </a>
                    {/* Residual (iw): library → floating|full deep research. */}
                    <button
                      type="button"
                      data-testid={`library-deep-research-${d.document_id}`}
                      data-view-mode="floating"
                      className="text-xs font-mono border rounded px-2 py-1"
                      disabled={hostDrBusy || busy}
                      onClick={() => void onDeepResearchLibraryDoc(d, "floating")}
                      title="Floating deep research on library HTML document"
                    >
                      DR float
                    </button>
                    <button
                      type="button"
                      data-testid={`library-deep-research-full-${d.document_id}`}
                      data-view-mode="full"
                      className="text-xs font-mono border rounded px-2 py-1"
                      disabled={hostDrBusy || busy}
                      onClick={() => void onDeepResearchLibraryDoc(d, "full")}
                      title="Full deep research on library HTML document"
                    >
                      DR full
                    </button>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
          {libraryDocs.length > 0 && filteredLibraryDocs.length === 0 ? (
            <p className="text-sm opacity-70" data-testid="library-filter-empty">
              No library matches for “{libraryFilter.trim()}”.
            </p>
          ) : null}
          {libraryHtml ? (
            <div
              className="prose border rounded p-3 text-sm"
              data-testid="library-html"
              dangerouslySetInnerHTML={{ __html: libraryHtml }}
            />
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
