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
 * Residual (aeo): Open Write data-seamless-port · library-landed · seamless-host-write
 * (catalog→account→Write path honesty; parity aea metrics + aen HostedHtml).
 * Residual (gj): offline twin seed after host/purchase so marketplace books
 * enter the recursive note-taker substrate (parity with Write fz).
 * Residual (hl): offline-seed honesty machine attrs on marketplace twin seed
 * status (parity TwinNotes hh).
 * Residual (id): Settings deep-link for driver + twin seed readiness.
 * Residual (il): catalog HTML-first honesty metrics (no payment rails claim).
 * Residual (im): account library HTML-first metrics strip.
 * Residual (in): host-result metrics after host/purchase land.
 * Residual (adh): host metrics L5 payment deferred + html-first stamps (parity catalog uy).
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
 * Residual (uu): optional arxiv/substack/URL pub refs on host-land DR launch
 * (parity HostedHtml er/uj · knowledge-dense grounding from free STEM books).
 * Residual (ta): filtered free-PD honesty — visible free among filtered
 * rows vs full-catalog free_count when free-only/subject/source/text filters on.
 * Residual (tb): library free/PD honesty under text filter (parity catalog ta).
 * Residual (tc): host-land free/PD honesty stamp (public_domain free host path).
 * Residual (ahe): paid purchase+host seamless port honesty (manual receipt ·
 * L5 deferred · HTML host into account · never invent live checkout).
 * Residual (apd): purchase receipt readiness chrome for L5 offline CTA
 * (demo-default honesty · paid-visible count · never invent live charge).
 * Residual (apl): library open/rehydrate windows pass is_free for HostedHtml
 * free/purchased twin seed honesty (parity apk host path).
 * Residual (apg): free-host readiness chrome for free PD / is_free catalog
 * (HTML host path · never PDF · counts visible free under filters).
 * Residual (ahm): host-land DR budget foresight includes pub-ref count (parity ahl).
 * Residual (aif): operator-visible pub-ref foresight chrome (parity aic–aie).
 * Residual (aho): twin seed body includes free/purchased path honesty for
 * recursive note-taker substrate after host/purchase.
 * Residual (alm): host-land domain-search coverage honesty (alj) so free PD
 * catalog subjects map to intelligent twin-search defaults after host.
 * Residual (alx): TwinNotesPanel on host land with catalog domainSubjects
 * (reading ≡ research recursive note-taker without requiring open window).
 * Residual (aly): ResearchContextPanel on host land with domainSubjects
 * (intelligent search + evidence over twin substrate · parity HostedHtml).
 * Residual (alz): remount twins + context after promote (parity HostedHtml ez/ec).
 * Residual (ama): remount twins + context after offline twin seed completes.
 * Residual (amj): host-land ResearchContext inherits hostDrTier depth posture.
 * Residual (ani): CollectiveResearchPanel on host land when open/recent DR spawns
 * exist so multi-select merge/analysis targets the hosted book (reading ≡ research ·
 * parity HostedHtml eu · TalkToBook ang · MetaReading anh).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { seedTwinNotes } from "../../api/engagement";
import { CollectiveResearchPanel } from "../../components/engagement/CollectiveResearchPanel";
import { ResearchContextPanel } from "../../components/engagement/ResearchContextPanel";
import { TwinNotesPanel } from "../../components/engagement/TwinNotesPanel";
import {
  domainDefaultSubjectCatalog,
  domainSearchCoverage,
} from "../../workspace/domainSearchDefaults";
import {
  MARKETPLACE_DEMO_RECEIPT_DEFAULT,
  marketplaceReceiptReadiness,
} from "../../workspace/marketplaceReceiptReadiness";
import { collectDeepResearchSpawnIds } from "../../workspace/collectDeepResearchSpawnIds";
import { listRecentDeepResearchSpawnIds } from "../../workspace/recentDeepResearchSpawns";
import { useWindows } from "../../workspace/windowsStore";
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
import { KNOWLEDGE_DENSE_PUBLICATION_PRESETS } from "../../components/engagement/PublicationAttachPanel";
import {
  ResearchLaunchBudgetPanel,
  type ResearchLaunchBudgetProjection,
  type ResearchLaunchTier,
} from "../../components/engagement/ResearchLaunchBudgetPanel";
import { fetchDepthTiers } from "../../api/settings";
import { mapDepthTierToResearchTier } from "../../lib/researchTier";
import {
  composeDriverPromptText,
  countPublicationRefs,
} from "../../lib/driverPromptText";
import { openWindow } from "../../components/windows/openWindow";
import {
  buildMarketplaceWriteHref,
  plainTextFromHtml,
} from "../../workspace/twinWriteSeed";
import { launchFloatingDeepResearch } from "../Reading/launchFloatingDeepResearch";
import {
  hydratePublicationRefs,
  parsePublicationRefs,
} from "../ResearchWorkstation/publicationRefs";

type LibraryDoc = {
  document_id: string;
  title?: string;
  license_class?: string;
  view_format?: string;
  /** Residual (abu): free inventory for library free honesty (parity free doctrine). */
  is_free?: boolean;
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
  /** Residual (acc): server library free_count when present (parity acb API). */
  const [libraryApiFreeCount, setLibraryApiFreeCount] = useState<number | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [receiptRef, setReceiptRef] = useState(MARKETPLACE_DEMO_RECEIPT_DEFAULT);
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
      // Residual (is/abq): free inventory filter is is_free only (parity free_count
      // abn/abo + free_only HTML abp — never invent free via license_class alone).
      if (freePdOnly) {
        if (!e.is_free) return false;
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

  // Residual (arf): free-PD twin-search default catalog honesty on domain chips.
  const domainDefaultCatalog = useMemo(() => domainDefaultSubjectCatalog(), []);

  /** Residual (lx): sorted knowledge-source chips for catalog filter UI. */
  const sourceChipList = useMemo(() => {
    return Object.keys(catalogBySource).sort((a, b) => a.localeCompare(b));
  }, [catalogBySource]);

  /**
   * Residual (ta): free-PD honesty under active filters.
   * Full-catalog free_count stays server honesty; filtered free is what the
   * operator sees in the list right now (never invent free when paid-only).
   */
  const catalogFreeCount = useMemo(() => {
    if (catalogHonesty?.free_count != null) return catalogHonesty.free_count;
    return entries.filter((e) => e.is_free).length;
  }, [catalogHonesty?.free_count, entries]);

  const filteredFreeCount = useMemo(() => {
    return filteredEntries.filter((e) => e.is_free).length;
  }, [filteredEntries]);

  const filteredPublicDomainCount = useMemo(() => {
    return filteredEntries.filter((e) => e.license_class === "public_domain")
      .length;
  }, [filteredEntries]);

  /**
   * Residual (apd): paid rows in the filtered catalog (require receipt token).
   * Free / public_domain use Host into account — never invent paid path.
   */
  const filteredPaidCount = useMemo(() => {
    return filteredEntries.filter(
      (e) =>
        !e.is_free &&
        e.license_class !== "public_domain",
    ).length;
  }, [filteredEntries]);

  /** Residual (apd/ars): L5 offline receipt readiness via pure helper. */
  const receiptReadiness = useMemo(
    () =>
      marketplaceReceiptReadiness({
        receiptRef,
        demoDefault: MARKETPLACE_DEMO_RECEIPT_DEFAULT,
      }),
    [receiptRef],
  );
  const receiptReady = receiptReadiness.receipt_ready;
  const receiptIsDemoDefault = receiptReadiness.is_demo_default;

  const catalogFiltersActive = useMemo(() => {
    return (
      freePdOnly ||
      Boolean(subjectFilter.trim()) ||
      Boolean(sourceFilter.trim()) ||
      Boolean(filterQuery.trim())
    );
  }, [freePdOnly, subjectFilter, sourceFilter, filterQuery]);

  const filteredLibraryDocs = useMemo(() => {
    const q = libraryFilter.trim().toLowerCase();
    if (!q) return libraryDocs;
    return libraryDocs.filter((d) => {
      const hay =
        `${d.title || ""} ${d.document_id} ${d.license_class || ""}`.toLowerCase();
      return hay.includes(q);
    });
  }, [libraryDocs, libraryFilter]);

  /** Residual (tb/abu): library free honesty — is_free first (parity free doctrine). */
  const libraryDocIsFree = (d: LibraryDoc) =>
    d.is_free === true ||
    (d.is_free == null &&
      (d.license_class === "public_domain" ||
        (d.license_class || "").toLowerCase() === "free"));

  /**
   * Residual (apl): resolve free/purchased for library → HostedHtml float twin seed.
   * true | false | null (unknown — never invent free entitlement).
   */
  const resolveLibraryIsFree = (d: LibraryDoc): boolean | null => {
    if (d.is_free === true) return true;
    if (d.is_free === false) return false;
    if (
      d.license_class === "public_domain" ||
      (d.license_class || "").toLowerCase() === "free"
    ) {
      return true;
    }
    return null;
  };

  const libraryFreeCount = useMemo(() => {
    // Residual (acc): prefer server free_count aggregate when loaded.
    if (libraryApiFreeCount != null && Number.isFinite(libraryApiFreeCount)) {
      return libraryApiFreeCount;
    }
    return libraryDocs.filter(libraryDocIsFree).length;
  }, [libraryDocs, libraryApiFreeCount]);

  const libraryFilteredFreeCount = useMemo(() => {
    return filteredLibraryDocs.filter(libraryDocIsFree).length;
  }, [filteredLibraryDocs]);

  const libraryFiltersActive = useMemo(
    () => Boolean(libraryFilter.trim()),
    [libraryFilter],
  );

  // Residual (alm): domain-search coverage for hosted catalog book subjects.
  const hostedDomainCoverage = useMemo(() => {
    if (!hosted) return null;
    const subjects =
      entries.find((e) => e.book_id === hosted.book_id)?.subjects || [];
    return domainSearchCoverage(subjects);
  }, [hosted, entries]);

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
  /** Residual (alz): remount twins + research context after promote/seed. */
  const [hostTwinsRefreshKey, setHostTwinsRefreshKey] = useState(0);
  // Residual (ani): open + recent DR spawns for collective multi-select on host land.
  const windows = useWindows((s) => s.windows);
  const [hostCollectiveRecentTick, setHostCollectiveRecentTick] = useState(0);
  const hostRecentSpawnIds = useMemo(
    () => listRecentDeepResearchSpawnIds(),
    [windows, hostCollectiveRecentTick],
  );
  const hostOpenSpawnIds = useMemo(
    () =>
      collectDeepResearchSpawnIds({
        currentSpawnId: null,
        windows,
      }),
    [windows],
  );
  const hostAvailableSpawnIds = useMemo(
    () =>
      collectDeepResearchSpawnIds({
        currentSpawnId: null,
        windows,
        recentSpawnIds: hostRecentSpawnIds,
      }),
    [windows, hostRecentSpawnIds],
  );
  /** Residual (iu): floating DR launch status after host. */
  const [hostDrStatus, setHostDrStatus] = useState<string | null>(null);
  const [hostDrBusy, setHostDrBusy] = useState(false);
  /** Residual (iy): soft budget gate before marketplace DR launch. */
  const [hostDrBudgetWarn, setHostDrBudgetWarn] = useState(false);
  const [hostDrForceBudget, setHostDrForceBudget] = useState(false);
  const [hostDrTier, setHostDrTier] = useState<ResearchLaunchTier>("deep");
  const [hostDrPromptPreview, setHostDrPromptPreview] = useState("");
  /** Residual (uu): optional arxiv/substack/URL refs for host-land DR. */
  const [hostDrPubRefs, setHostDrPubRefs] = useState("");
  const [hostDrPubRefStatus, setHostDrPubRefStatus] = useState<string | null>(
    null,
  );
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
      setLibraryApiFreeCount(
        typeof lib.free_count === "number" && Number.isFinite(lib.free_count)
          ? lib.free_count
          : null,
      );
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
    /** Residual (ahr): research-domain subjects for twin intelligent search default. */
    subjects?: string[] | null;
    book_id?: string | null;
    /** Residual (apk): free vs purchased honesty for HostedHtml float twin seed. */
    is_free?: boolean | null;
  }) {
    if ((opts.view_format || "html") !== "html" || !opts.html) return;
    // Residual (ahr): resolve subjects from catalog entry when book_id known.
    const catalogEntry = opts.book_id
      ? entries.find((e) => e.book_id === opts.book_id)
      : undefined;
    const fromCatalog =
      opts.subjects || catalogEntry?.subjects || null;
    // Residual (apk): resolve is_free from opts or catalog (never invent free).
    const resolvedIsFree =
      opts.is_free === true || opts.is_free === false
        ? opts.is_free
        : catalogEntry?.is_free === true || catalogEntry?.is_free === false
          ? catalogEntry.is_free
          : null;
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
        subjects: fromCatalog || undefined,
        is_free: resolvedIsFree,
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
    setHostDrPubRefStatus(null);
    setError(null);
    try {
      // Residual (uu): hydrate optional arxiv/substack/URL refs before launch.
      const refs = parsePublicationRefs(hostDrPubRefs);
      if (refs.length > 0) {
        const hydrated = await hydratePublicationRefs(refs);
        setHostDrPubRefStatus(
          `Hydrated ${hydrated.ok.length} pub asset(s)` +
            (hydrated.failed.length
              ? ` · ${hydrated.failed.length} failed`
              : "") +
            " · HTML-first · offline-default",
        );
      }
      const out = await launchFloatingDeepResearch({
        asset_id: result.document_id,
        selection_text: selection,
        goal_hint: `Wrestle claims and cite evidence in “${title}” (marketplace HTML host · tier=${hostDrTier}${domainClause}).`,
        view_mode: viewMode,
        research_tier: hostDrTier,
        references: refs.length > 0 ? refs : undefined,
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
    setHostDrPubRefStatus(null);
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
          // Residual (apl): free/purchased honesty into float twin seed.
          is_free: resolveLibraryIsFree(doc),
          book_id: hosted.book_id || doc.document_id,
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
      const documentId = body.document_id || doc.document_id;
      const title = body.title || doc.title || doc.document_id;
      const licenseClass = body.license_class || doc.license_class || "unknown";
      // Residual (acg): retain rehydrated body in hosted state so library Open Write
      // twin_seed can use full HTML (parity acf in-session host body path).
      const rehydratedHost: HostResultResponse = {
        document_id: documentId,
        owner_id: ownerId,
        book_id: documentId,
        content_hash: "",
        title,
        license_class: licenseClass,
        already_hosted: true,
        source_format: "html",
        library_document_ids: [documentId],
        view_format: "html",
        html: body.html,
      };
      setHosted(rehydratedHost);
      openHostedWindow({
        document_id: documentId,
        title,
        html: body.html,
        view_format: "html",
        license_class: licenseClass,
        owner_id: ownerId,
        source: "marketplace_library_rehydrate",
        // Residual (apl): free/purchased honesty into float twin seed.
        is_free: resolveLibraryIsFree(doc),
        book_id: documentId,
      });
      // Residual (ach): offline twin seed after library rehydrate so recursive
      // note-taker substrate joins library-opened books (parity host/purchase gj).
      await seedHostedTwins(rehydratedHost);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  /** Residual (gj)/(hl)/(mo)/(aho): offline twin seed for hosted book (non-fatal; honest). */
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
      // Residual (aho): free vs purchased path honesty in twin substrate.
      const isFreeHost =
        Boolean(entry?.is_free) ||
        result.license_class === "public_domain";
      const portHonesty = isFreeHost
        ? "Port path: free public-domain HTML host into account (no payment rails).\n\n"
        : "Port path: purchased HTML host via manual receipt (L5 live payment deferred · never invent entitlement).\n\n";
      const bodyText = (
        subjectPrefix +
        portHonesty +
        (plain || result.title || result.document_id)
      ).slice(0, 2200);
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
      // Residual (ama): remount host-land twins + context after offline seed lands.
      setHostTwinsRefreshKey((k) => k + 1);
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
      setLibraryApiFreeCount(
        typeof lib.free_count === "number" && Number.isFinite(lib.free_count)
          ? lib.free_count
          : null,
      );
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
          book_id: result.book_id,
          // Residual (apk): free host path honesty into float twin seed.
          is_free:
            entries.find((e) => e.book_id === bookId)?.is_free ?? true,
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
      setLibraryApiFreeCount(
        typeof lib.free_count === "number" && Number.isFinite(lib.free_count)
          ? lib.free_count
          : null,
      );
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
          book_id: result.book_id || entry.book_id,
          subjects: entry.subjects || null,
          // Residual (apk): purchased path never claims free.
          is_free: false,
        });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="h-full overflow-y-auto p-6"
      data-view-format="html"
      data-html-first="true"
      data-testid="marketplace-host-mode"
      data-l5-live-payment="deferred"
      data-soft-budget="true"
      data-budget-before-fire="true"
      data-never-auto-route="true"
    >
      <header className="mb-6 space-y-2">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="space-y-1">
            <h1 className="text-2xl font-semibold">Marketplace · host into account</h1>
            <p className="text-sm opacity-80">
              Host public-domain catalog books into your Antiek library. Purchased
              titles use a manual receipt token (no live payment rails). Human view
              is HTML, never PDF. Soft budget foresight on host DR · L5 live
              payment deferred · never auto-route model choice.
            </p>
            {/* Residual (aqp): marketplace honesty nav (parity MO aqn · Settings aqj–aqo). */}
            <p
              className="text-[11px] font-mono flex flex-wrap gap-x-3 gap-y-1 opacity-90"
              data-testid="marketplace-honesty-nav"
              data-view-format="html"
              data-html-first="true"
              data-l5-live-payment="deferred"
              data-soft-budget="true"
              data-never-auto-route="true"
              role="navigation"
              aria-label="Marketplace host honesty navigation"
            >
              <a
                href="/settings#prompt-cost-projection"
                data-testid="marketplace-prompt-cost-honesty-link"
                className="underline opacity-90 hover:opacity-100"
                title="Settings prompt-cost projection (soft budget foresight before host DR)"
              >
                Prompt-cost projection
              </a>
              <a
                href="/settings#decision-tree-panel"
                data-testid="marketplace-decision-tree-honesty-link"
                className="underline opacity-90 hover:opacity-100"
                title="Settings decision-tree driver (manual model choice · never auto-route)"
              >
                Decision-tree driver
              </a>
              <a
                href="/settings#notdiamond-advisory"
                data-testid="marketplace-notdiamond-honesty-link"
                className="underline opacity-90 hover:opacity-100"
                title="NotDiamond advisory only · never dispatch authority"
              >
                ND advisory
              </a>
              <span
                className="opacity-70"
                data-testid="marketplace-soft-budget-hint"
              >
                HTML-first · soft budget · L5 deferred · never auto-route
              </span>
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
              {/* Residual (ye): marketplace dual-gate → L5 payment section (host path). */}
              <a
                href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l5-payment"
                data-testid="marketplace-dual-gate-checklist-link"
                className="underline opacity-80 hover:opacity-100"
                title="Dual-gate L5 payment rails deferred checklist (manual receipt only)"
              >
                Dual-gate L5 payment checklist
              </a>
              {/* Residual (ajl): free STEM / HTML marketplace → competitive DR honesty map. */}
              <a
                href="/settings#settings-competitive-dr-scorecard"
                data-testid="marketplace-competitive-scorecard-link"
                className="underline opacity-80 hover:opacity-100"
                title="Settings competitive deep-research scorecard (HTML-first free STEM shipped · L5 payment deferred)"
              >
                Settings · competitive DR scorecard
              </a>
              <a
                href="/docs/campaigns/2026-07-09-research-reading-spine/FUTURE-AGENT-SPEC-competitive-deep-research-quality.md"
                data-testid="marketplace-competitive-dr-future-agent-link"
                className="underline opacity-80 hover:opacity-100"
                title="FUTURE-AGENT competitive deep-research quality brief"
              >
                FUTURE · competitive DR brief
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
        {/* Residual (is/abz): free inventory quick filter (is_free only · parity free doctrine). */}
        <label className="flex items-center gap-2 text-sm font-mono pb-1">
          <input
            type="checkbox"
            data-testid="catalog-free-pd-only"
            checked={freePdOnly}
            onChange={(e) => setFreePdOnly(e.target.checked)}
            disabled={busy}
          />
          Free inventory only
        </label>
        {/* Residual (lw/arf): research-domain subject chips + twin-search default catalog honesty. */}
        <div
          className="flex flex-wrap gap-1 items-center pb-1"
          data-testid="catalog-subject-chips"
          data-view-format="html"
          data-html-first="true"
          data-domain-default-count={String(domainDefaultCatalog.count)}
          data-domain-defaults-all-ready={String(
            domainDefaultCatalog.all_have_default,
          )}
          data-twin-search-defaults="true"
          role="group"
          aria-label="Filter catalog by research domain"
          title={`Twin-search domain defaults catalog: ${domainDefaultCatalog.count} subjects (all_have_default=${domainDefaultCatalog.all_have_default})`}
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
            data-receipt-ready={String(receiptReady)}
            data-receipt-demo-default={String(receiptIsDemoDefault)}
            aria-label="Purchase receipt ref for L5 offline purchase+host"
          />
          {/* Residual (apd/ars): L5 offline receipt readiness via pure helper. */}
          <span
            className="text-[10px] opacity-80 max-w-[22rem]"
            data-testid="marketplace-receipt-readiness"
            data-receipt-ready={String(receiptReadiness.receipt_ready)}
            data-receipt-demo-default={String(receiptReadiness.is_demo_default)}
            data-live-checkout-deferred={String(
              receiptReadiness.live_checkout_deferred,
            )}
            data-never-invent-charge={String(
              receiptReadiness.never_invent_charge,
            )}
            data-paid-catalog-visible={String(filteredPaidCount)}
            data-l5-payment-rails="deferred"
            data-live-payment="false"
            data-payment-rails="manual_receipt_only"
            data-view-format="html"
            data-html-first="true"
            role="status"
          >
            {receiptReadiness.receipt_ready
              ? receiptReadiness.is_demo_default
                ? `Receipt ready (demo default) · ${filteredPaidCount} paid book(s) can purchase+host · replace token for real orders · L5 live deferred · never invent charge`
                : `Receipt ready · ${filteredPaidCount} paid book(s) can purchase+host · L5 live deferred · never invent charge`
              : `Enter receipt token to enable Purchase + host · ${filteredPaidCount} paid book(s) visible · L5 live checkout deferred`}
          </span>
          {/* Residual (apg): free HTML host path readiness (no receipt · never PDF). */}
          <span
            className="text-[10px] opacity-80 max-w-[22rem]"
            data-testid="marketplace-free-host-readiness"
            data-free-catalog-visible={String(filteredFreeCount)}
            data-free-pd-only={String(freePdOnly)}
            data-html-first="true"
            data-view-format="html"
            data-live-payment="false"
            role="status"
          >
            Free HTML host path · {filteredFreeCount} free book(s) can Host into
            account
            {freePdOnly ? " · free-only filter on" : ""} · never PDF view · no
            receipt required
          </span>
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
        data-free-count={String(catalogFreeCount)}
        data-filtered-free-count={String(filteredFreeCount)}
        data-filtered-public-domain-count={String(filteredPublicDomainCount)}
        data-filters-active={String(catalogFiltersActive)}
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
        // Residual (agl): foundations STEM honesty after Gödel free PD (agh).
        data-foundations-count={String(catalogBySubject["foundations"] ?? 0)}
        data-has-godel-pd={String(
          entries.some((e) => e.book_id === "pd-godel-incompleteness"),
        )}
        // Residual (agt): heat / signal_processing STEM honesty after Fourier free PD (ags).
        data-heat-count={String(catalogBySubject["heat"] ?? 0)}
        data-signal-processing-count={String(
          catalogBySubject["signal_processing"] ?? 0,
        )}
        data-has-fourier-pd={String(
          entries.some((e) => e.book_id === "pd-fourier-heat"),
        )}
        role="status"
      >
        <p>
          Catalog · entries={entries.length} · filtered={filteredEntries.length}{" "}
          · sources={Object.keys(catalogBySource).length} · subjects=
          {Object.keys(catalogBySubject).length} · free=
          {catalogFreeCount}{" "}
          · foundations={catalogBySubject["foundations"] ?? 0}{" "}
          · heat={catalogBySubject["heat"] ?? 0} · signal_processing=
          {catalogBySubject["signal_processing"] ?? 0}{" "}
          · human view=HTML · payment=
          {catalogHonesty?.payment_rails || "manual_receipt_only"} (no live
          rails)
        </p>
        {/* Residual (uy): L5 payment rails honesty — manual receipt only. */}
        {/* Residual (aks): Sprint 1 payment_adapter boundary shipped offline (akr). */}
        <p
          className="text-[11px] font-mono opacity-80 space-x-2"
          data-testid="marketplace-l5-payment-honesty"
          data-payment-rails={
            catalogHonesty?.payment_rails || "manual_receipt_only"
          }
          data-l5-payment-rails="deferred"
          data-live-payment="false"
          data-payment-adapter-sprint="1"
          data-payment-adapter-boundary="shipped_offline"
          data-payment-adapter-env="ANTIEK_MARKETPLACE_LIVE_PAYMENT"
          data-view-format="html"
          role="status"
        >
          <span>
            L5 payment rails:{" "}
            <strong>
              {catalogHonesty?.payment_rails || "manual_receipt_only"}
            </strong>{" "}
            · live checkout deferred · purchase+host requires operator receipt
            token (never invent paid entitlement)
          </span>
          <span
            data-testid="marketplace-l5-payment-adapter-status"
            data-payment-adapter-sprint="1"
            data-payment-adapter-boundary="shipped_offline"
            data-payment-adapter-env="ANTIEK_MARKETPLACE_LIVE_PAYMENT"
            data-live-payment="false"
          >
            · payment adapter Sprint 1 shipped offline (akr ·
            DeferredPaymentAdapter · zero upstream · never invent $0) · Sprint 2
            purchase path still deferred · env=
            ANTIEK_MARKETPLACE_LIVE_PAYMENT
          </span>
          {/* Residual (wj): L5 checklist section deep-link (parity Settings wh). */}
          <a
            href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l5-payment"
            data-testid="marketplace-l5-dual-gate-link"
            className="underline hover:opacity-100"
            title="Dual-gate checklist L5 payment rails deferred (manual receipt only)"
          >
            L5 payment checklist
          </a>
        </p>
        {/* Residual (ta): free-PD honesty under active filters. */}
        {catalogFiltersActive ? (
          <p
            data-testid="marketplace-catalog-filtered-free-honesty"
            data-filtered-free-count={String(filteredFreeCount)}
            data-catalog-free-count={String(catalogFreeCount)}
            data-filtered-public-domain-count={String(
              filteredPublicDomainCount,
            )}
            data-free-pd-only={String(freePdOnly)}
            role="status"
          >
            Filtered free honesty: visible_free={filteredFreeCount} ·
            catalog_free={catalogFreeCount} · visible_pd=
            {filteredPublicDomainCount}
            {freePdOnly ? " · free-only=on" : ""}
            {subjectFilter ? ` · subject=${subjectFilter}` : ""}
            {sourceFilter ? ` · source=${sourceFilter}` : ""}
            {" · HTML host path only (no live payment rails)"}
          </p>
        ) : null}
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
                data-testid={`free-host-${e.book_id}`}
                data-book-id={e.book_id}
                data-html-first="true"
                data-view-format="html"
                data-free-host="true"
                data-is-free={String(Boolean(e.is_free))}
                data-license-class={e.license_class || ""}
                data-live-payment="false"
                data-seamless-port="true"
                disabled={busy}
                onClick={() => void onHost(e.book_id)}
                title="Host free HTML book into account (never PDF · no receipt · seamless port)"
              >
                Host into account
              </button>
            ) : (
              <div
                className="flex flex-col items-end gap-1"
                data-testid={`purchase-actions-${e.book_id}`}
                data-l5-payment-rails="deferred"
                data-live-payment="false"
              >
                <button
                  type="button"
                  data-testid={`purchase-host-${e.book_id}`}
                  data-book-id={e.book_id}
                  data-seamless-purchase-port="true"
                  data-l5-payment-rails="deferred"
                  data-live-payment="false"
                  data-view-format="html"
                  data-payment-rails="manual_receipt_only"
                  data-receipt-required="true"
                  data-receipt-ready={String(receiptReady)}
                  data-receipt-demo-default={String(receiptIsDemoDefault)}
                  disabled={busy || !receiptReady}
                  onClick={() => void onPurchaseAndHost(e)}
                  title={
                    receiptReady
                      ? receiptIsDemoDefault
                        ? "Purchase + host with demo receipt token (replace for real orders · L5 live deferred · HTML account port)"
                        : "Purchase + host with manual receipt token (L5 live rails deferred · HTML account port)"
                      : "Enter receipt token to enable Purchase + host (L5 live checkout deferred)"
                  }
                >
                  Purchase + host
                </button>
                {/* Residual (ala / L5 Sprint 3 offline): live checkout CTA stays
                    disabled until dual-gate live rails — never invent charge. */}
                <button
                  type="button"
                  data-testid={`live-checkout-deferred-${e.book_id}`}
                  data-book-id={e.book_id}
                  data-l5-payment-rails="deferred"
                  data-live-payment="false"
                  data-payment-rails="manual_receipt_only"
                  data-payment-adapter-sprint="1"
                  data-payment-adapter-boundary="shipped_offline"
                  data-checkout-cta="deferred"
                  data-live-checkout-available="false"
                  disabled
                  title="Live checkout deferred (L5 dual-gate ANTIEK_MARKETPLACE_LIVE_PAYMENT · Sprint 1–2 offline · never invent charge)"
                  aria-disabled="true"
                >
                  Live checkout (L5 deferred)
                </button>
                <span
                  className="text-[10px] font-mono opacity-70 max-w-[14rem] text-right"
                  data-testid={`live-checkout-deferred-note-${e.book_id}`}
                  data-l5-payment-rails="deferred"
                  data-live-payment="false"
                  data-checkout-cta="deferred"
                >
                  Use manual receipt token · live rails dual-gate only · zero
                  upstream until operator enables payment
                </span>
              </div>
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
          {freePdOnly ? " (free inventory only)" : ""}.
        </p>
      ) : null}

      {hosted ? (
        <section className="mt-8 space-y-2" data-testid="host-result">
          <h2 className="text-lg font-medium">Hosted {hosted.document_id}</h2>
          {/* Residual (in/ip/tc): host land metrics + free/PD honesty. */}
          <div
            data-testid="marketplace-host-metrics"
            data-document-id={hosted.document_id}
            data-already-hosted={String(Boolean(hosted.already_hosted))}
            data-license-class={hosted.license_class ?? ""}
            data-is-public-domain={String(
              (hosted.license_class || "") === "public_domain",
            )}
            data-is-free-host={String(
              // Residual (abs): free_host is catalog is_free only (parity abn–abq).
              Boolean(
                entries.find((e) => e.book_id === hosted.book_id)?.is_free,
              ),
            )}
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
            // Residual (alm): intelligent twin-search domain coverage after host.
            data-domain-search-has-default={String(
              Boolean(hostedDomainCoverage?.has_default),
            )}
            data-domain-search-covered={
              hostedDomainCoverage?.covered.join(",") || ""
            }
            data-domain-search-uncovered={
              hostedDomainCoverage?.uncovered.join(",") || ""
            }
            data-domain-search-covered-count={String(
              hostedDomainCoverage?.covered.length ?? 0,
            )}
            data-domain-search-uncovered-count={String(
              hostedDomainCoverage?.uncovered.length ?? 0,
            )}
            data-twin-seeded={
              twinSeedStatus
                ? twinSeedHonesty?.seeded === false
                  ? "skipped"
                  : "true"
                : "pending"
            }
            data-payment-rails="manual_receipt_only"
            // Residual (adh): L5 payment deferred honesty + HTML-first host land.
            data-l5-payment-rails="deferred"
            data-html-first="true"
            // Residual (ahe): purchased (non-free) path honesty after manual receipt host.
            data-purchased-path={String(
              Boolean(
                hosted.license_class &&
                  hosted.license_class !== "public_domain" &&
                  !entries.find((e) => e.book_id === hosted.book_id)?.is_free,
              ),
            )}
            data-seamless-purchase-port={String(
              Boolean(
                hosted.license_class &&
                  hosted.license_class !== "public_domain" &&
                  (hosted.view_format || "html") === "html" &&
                  Boolean(hosted.document_id),
              ),
            )}
            data-live-payment="false"
            // Residual (aea): seamless port audit — catalog → account library → HTML host → twins.
            data-seamless-port={String(
              (hosted.view_format || "html") === "html" &&
                Boolean(hosted.document_id) &&
                (libraryDocs || []).some(
                  (d) => d.document_id === hosted.document_id,
                ),
            )}
            data-library-landed={String(
              (libraryDocs || []).some(
                (d) => d.document_id === hosted.document_id,
              ),
            )}
            data-account-owner={hosted.owner_id || ownerId || ""}
            role="status"
            className="font-mono text-[11px] opacity-80 space-y-0.5"
          >
            <p>
              Host land · document={hosted.document_id} · already=
              {String(Boolean(hosted.already_hosted))} · view=
              {hosted.view_format} · catalog_source=
              {entries.find((e) => e.book_id === hosted.book_id)?.source ||
                "unknown"}
              · subjects=
              {(
                entries.find((e) => e.book_id === hosted.book_id)?.subjects || []
              ).join(",") || "none"}
            </p>
            {/* Residual (alm): domain-search coverage honesty after host land. */}
            {hostedDomainCoverage ? (
              <p
                data-testid="marketplace-host-domain-search-coverage"
                data-has-default={String(hostedDomainCoverage.has_default)}
                data-covered-count={String(
                  hostedDomainCoverage.covered.length,
                )}
                data-uncovered-count={String(
                  hostedDomainCoverage.uncovered.length,
                )}
                data-covered={hostedDomainCoverage.covered.join(",") || ""}
                data-uncovered={
                  hostedDomainCoverage.uncovered.join(",") || ""
                }
                role="status"
              >
                Domain-search coverage:{" "}
                {hostedDomainCoverage.has_default
                  ? `default active · covered=${hostedDomainCoverage.covered.join(",") || "none"}`
                  : "no domain default (honest empty · never invent query)"}
                {hostedDomainCoverage.uncovered.length > 0
                  ? ` · co-tags=${hostedDomainCoverage.uncovered.join(",")}`
                  : ""}
              </p>
            ) : null}
            {/* Residual (aea): seamless port honesty for account host path. */}
            <p
              data-testid="marketplace-seamless-port"
              data-seamless-port={String(
                (hosted.view_format || "html") === "html" &&
                  Boolean(hosted.document_id) &&
                  (libraryDocs || []).some(
                    (d) => d.document_id === hosted.document_id,
                  ),
              )}
              data-library-landed={String(
                (libraryDocs || []).some(
                  (d) => d.document_id === hosted.document_id,
                ),
              )}
              data-view-format={hosted.view_format ?? "html"}
              data-twin-seeded={
                twinSeedStatus
                  ? twinSeedHonesty?.seeded === false
                    ? "skipped"
                    : "true"
                  : "pending"
              }
              data-html-first="true"
              role="status"
            >
              Seamless port: catalog → account library=
              {(libraryDocs || []).some(
                (d) => d.document_id === hosted.document_id,
              )
                ? "landed"
                : "pending"}{" "}
              · HTML host · twin seed=
              {twinSeedStatus
                ? twinSeedHonesty?.seeded === false
                  ? "skipped"
                  : "seeded"
                : "pending"}{" "}
              · owner={hosted.owner_id || ownerId || "—"}
            </p>
            {/* Residual (tc/abs): free/PD host path honesty — free_host is is_free. */}
            <p
              data-testid="marketplace-host-free-pd-honesty"
              data-license-class={hosted.license_class ?? ""}
              data-is-public-domain={String(
                (hosted.license_class || "") === "public_domain",
              )}
              data-is-free-host={String(
                Boolean(
                  entries.find((e) => e.book_id === hosted.book_id)?.is_free,
                ),
              )}
              data-l5-payment-rails="deferred"
              data-html-first="true"
              role="status"
            >
              Free/PD host honesty: license=
              {hosted.license_class || "unknown"} · free_host=
              {Boolean(
                entries.find((e) => e.book_id === hosted.book_id)?.is_free,
              )
                ? "true"
                : "false"}{" "}
              · HTML host only · payment=manual_receipt_only · L5 rails deferred
              (no live rails)
            </p>
            {/* Residual (akb): host land → FUTURE L5 digital book port + dual-gate L5. */}
            {/* Residual (aks): host land stamps Sprint 1 payment_adapter shipped offline (akr). */}
            <p
              className="space-x-3"
              data-testid="marketplace-host-l5-nav"
              data-l5-payment-rails="deferred"
              data-payment-rails="manual_receipt_only"
              data-payment-adapter-sprint="1"
              data-payment-adapter-boundary="shipped_offline"
              data-payment-adapter-env="ANTIEK_MARKETPLACE_LIVE_PAYMENT"
              data-live-payment="false"
              data-html-first="true"
              data-view-format="html"
              role="navigation"
              aria-label="Marketplace host L5 payment honesty navigation"
            >
              <a
                href="/docs/campaigns/2026-07-09-research-reading-spine/FUTURE-AGENT-SPEC-l5-digital-book-seamless-port.md"
                data-testid="marketplace-host-l5-future-agent-link"
                className="underline opacity-90 hover:opacity-100"
                title="Future-agent L5 digital book seamless port brief (Sprint 1 payment adapter shipped offline akr · Sprint 2 purchase path deferred · manual receipt)"
              >
                FUTURE · L5 digital book seamless port
              </a>
              <a
                href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l5-payment"
                data-testid="marketplace-host-l5-dual-gate-link"
                className="underline opacity-90 hover:opacity-100"
                title="Dual-gate L5 payment rails checklist (prep only · manual receipt only)"
              >
                Dual-gate L5 payment checklist
              </a>
              <a
                href="/settings#settings-competitive-dr-scorecard"
                data-testid="marketplace-host-competitive-scorecard-link"
                className="underline opacity-90 hover:opacity-100"
                title="Settings competitive DR scorecard (HTML-first free STEM · L5 payment deferred)"
              >
                Settings · competitive DR scorecard
              </a>
            </p>
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
          {/* Residual (alx): TwinNotes on host land with catalog domain subjects. */}
          {hosted.document_id?.trim() ? (
            <section
              className="mt-2 space-y-1 border rounded p-3"
              data-testid="marketplace-host-twins-mount"
              data-view-format="html"
              data-document-id={hosted.document_id.trim()}
              data-book-id={hosted.book_id || ""}
              data-domain-subjects={
                catalogSubjectsForBook(hosted.book_id).join(",") || "none"
              }
              data-domain-search-has-default={String(
                Boolean(hostedDomainCoverage?.has_default),
              )}
              data-seamless-marketplace-twins="true"
              data-research-tier={hostDrTier}
            >
              <div
                data-testid="marketplace-host-twins-refresh"
                data-refresh-key={String(hostTwinsRefreshKey)}
                data-seed-phase={
                  twinSeedStatus
                    ? twinSeedHonesty?.seeded === false
                      ? "skipped"
                      : "seeded"
                    : "pending"
                }
              >
                <TwinNotesPanel
                  key={`mkt-twins-${hosted.document_id.trim()}-${hostTwinsRefreshKey}`}
                  assetId={hosted.document_id.trim()}
                  autoLoad
                  autoSeedIfEmpty
                  autoPromoteAfterLoad
                  onPromoted={() => setHostTwinsRefreshKey((k) => k + 1)}
                  seedTitle={
                    hosted.title?.trim() ||
                    hosted.book_id ||
                    hosted.document_id.trim()
                  }
                  seedBodyText={
                    (hosted.body_preview || hosted.html || "").slice(0, 2000) ||
                    hosted.title ||
                    ""
                  }
                  researchTier={hostDrTier}
                  domainSubjects={catalogSubjectsForBook(hosted.book_id)}
                />
              </div>
              {/* Residual (aly): research context + intelligent search over twins. */}
              {/* Residual (alz): remount context with twins refresh key after promote. */}
              <div
                className="mt-2"
                data-testid="marketplace-host-context-mount"
                data-view-format="html"
                data-document-id={hosted.document_id.trim()}
                data-domain-subjects={
                  catalogSubjectsForBook(hosted.book_id).join(",") || "none"
                }
                data-domain-search-has-default={String(
                  Boolean(hostedDomainCoverage?.has_default),
                )}
                data-seamless-marketplace-context="true"
                data-refresh-key={String(hostTwinsRefreshKey)}
              >
                <ResearchContextPanel
                  key={`mkt-ctx-${hosted.document_id.trim()}-${hostTwinsRefreshKey}`}
                  assetId={hosted.document_id.trim()}
                  autoLoad
                  domainSubjects={catalogSubjectsForBook(hosted.book_id)}
                  researchTier={hostDrTier}
                />
              </div>
              {/* Residual (ani): multi-select open + recent DR spawns → hosted book. */}
              {hostAvailableSpawnIds.length > 0 ? (
                <div
                  className="mt-2"
                  data-testid="marketplace-host-collective-mount"
                  data-view-format="html"
                  data-document-id={hosted.document_id.trim()}
                  data-book-id={hosted.book_id || ""}
                  data-seamless-marketplace-collective="true"
                  data-available-spawn-count={String(hostAvailableSpawnIds.length)}
                  data-recent-count={String(hostRecentSpawnIds.length)}
                  data-open-spawn-count={String(hostOpenSpawnIds.length)}
                  data-research-tier={hostDrTier}
                >
                  <CollectiveResearchPanel
                    availableSpawnIds={hostAvailableSpawnIds}
                    parentAssetId={hosted.document_id.trim()}
                    recentSpawnIds={hostRecentSpawnIds}
                    openSpawnIds={hostOpenSpawnIds}
                    onRecentSpawnsCleared={() =>
                      setHostCollectiveRecentTick((n) => n + 1)
                    }
                    onDocMerged={() => setHostTwinsRefreshKey((k) => k + 1)}
                  />
                </div>
              ) : null}
            </section>
          ) : null}
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
          {/* Residual (iy/jc/ahm): budget projection soft-gate · pub-ref foresight. */}
          <div
            className="space-y-2 border rounded p-3"
            data-testid="marketplace-host-dr-budget-mount"
            data-view-format="html"
            data-research-tier={hostDrTier}
            data-depth-prefill={hostDrDepthPrefill}
            data-domains={
              catalogSubjectsForBook(hosted.book_id).join(",") || "none"
            }
            data-pub-ref-count={String(countPublicationRefs(hostDrPubRefs))}
            data-has-pub-refs={String(countPublicationRefs(hostDrPubRefs) > 0)}
            data-prompt-chars={String(
              composeDriverPromptText(
                hostDrPromptPreview || hosted.title || "hosted book",
                hostDrPubRefs,
              ).length,
            )}
          >
            {/* Residual (aif): operator-visible pub-ref foresight chrome (parity aic–aie). */}
            {countPublicationRefs(hostDrPubRefs) > 0 ? (
              <p
                className="text-[10px] font-mono opacity-80 mb-1"
                data-testid="marketplace-host-pub-ref-foresight-chrome"
                data-pub-ref-count={String(countPublicationRefs(hostDrPubRefs))}
                role="status"
              >
                Knowledge-dense pubs in projection:{" "}
                <strong>{countPublicationRefs(hostDrPubRefs)}</strong> ref
                {countPublicationRefs(hostDrPubRefs) === 1 ? "" : "s"} · chars=
                {composeDriverPromptText(
                  hostDrPromptPreview || hosted.title || "hosted book",
                  hostDrPubRefs,
                ).length}{" "}
                · soft budget below
              </p>
            ) : null}
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
              promptText={composeDriverPromptText(
                hostDrPromptPreview || hosted.title || "hosted book",
                hostDrPubRefs,
              )}
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
            {/* Residual (uu/ahb): ground marketplace DR with arxiv/substack/URL refs. */}
            <div
              className="space-y-1"
              data-testid="marketplace-host-pub-refs"
              data-view-format="html"
              data-offline-default="true"
              data-l1-l2-hydrate-prep="true"
              data-seamless-pub-quick-call="true"
              data-knowledge-dense-presets={String(
                KNOWLEDGE_DENSE_PUBLICATION_PRESETS.length,
              )}
            >
              <label
                className="text-[10px] font-mono uppercase tracking-wider opacity-80"
                htmlFor="marketplace-host-refs-input"
              >
                Ground with pubs (optional · arxiv / substack / URL)
              </label>
              {/* Residual (ahb): marketplace host DR quick-call (parity hosted aha). */}
              <div
                className="flex flex-wrap gap-1 items-center"
                data-testid="marketplace-host-publication-quick-call"
                data-preset-count={String(
                  KNOWLEDGE_DENSE_PUBLICATION_PRESETS.length,
                )}
                data-seamless-pub-quick-call="true"
                data-auto-hydrate="false"
                role="group"
                aria-label="Knowledge-dense publication quick-call presets"
              >
                <span className="text-[10px] font-mono opacity-70 mr-1">
                  Quick-call:
                </span>
                {KNOWLEDGE_DENSE_PUBLICATION_PRESETS.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    data-testid={`marketplace-host-preset-${p.id}`}
                    data-preset-id={p.id}
                    data-kind={p.kind}
                    data-reference={p.reference}
                    data-auto-hydrate="false"
                    disabled={hostDrBusy || busy}
                    onClick={() => {
                      const ref = p.reference.trim();
                      if (!ref) return;
                      setHostDrPubRefs((prev) => {
                        const existing = new Set(
                          prev
                            .split(/\r?\n/)
                            .map((l) => l.trim())
                            .filter(Boolean),
                        );
                        if (existing.has(ref)) return prev;
                        const base = prev.trim();
                        return base ? `${base}\n${ref}` : ref;
                      });
                    }}
                    className="text-[10px] font-mono border rounded px-1.5 py-0.5 opacity-80 hover:opacity-100 disabled:opacity-50 border-ink/20 dark:border-bright/20"
                    title={`Insert ${p.reference} (hydrates offline-honest on DR launch · never auto-live)`}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
              <textarea
                id="marketplace-host-refs-input"
                data-testid="marketplace-host-refs-input"
                value={hostDrPubRefs}
                onChange={(e) => setHostDrPubRefs(e.target.value)}
                disabled={hostDrBusy || busy}
                rows={2}
                placeholder={"arxiv:1706.03762\nhttps://…"}
                className="w-full rounded border border-ink/20 bg-transparent px-2 py-1 text-[11px] font-mono dark:border-bright/20"
              />
              <p className="text-[10px] font-mono space-x-2 opacity-80">
                <a
                  href="/settings#hydrate-live-status"
                  data-testid="marketplace-host-hydrate-settings-link"
                  className="underline hover:opacity-100"
                  title="Settings publication hydrate readiness (arxiv/substack · offline default)"
                >
                  Settings · hydrate readiness
                </a>
                {/* Residual (xd): L1 arxiv checklist section deep-link (parity pubs xc). */}
                <a
                  href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l1-arxiv"
                  data-testid="marketplace-host-hydrate-dual-gate-link"
                  className="underline hover:opacity-100"
                  title="Dual-gate L1 arxiv hydrate checklist (prep only · offline default)"
                >
                  Dual-gate L1 arxiv checklist
                </a>
                {/* Residual (aal): L2 substack section — label claimed L1–L2 but only
                    linked L1; knowledge-dense Substack prep needs its own anchor. */}
                <a
                  href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l2-substack"
                  data-testid="marketplace-host-hydrate-dual-gate-l2-link"
                  className="underline hover:opacity-100"
                  title="Dual-gate L2 Substack hydrate checklist (prep only · factory + ToS)"
                >
                  Dual-gate L2 Substack checklist
                </a>
              </p>
              {hostDrPubRefStatus ? (
                <p
                  className="text-[10px] font-mono text-aurora"
                  data-testid="marketplace-host-refs-status"
                  role="status"
                >
                  {hostDrPubRefStatus}
                </p>
              ) : null}
            </div>
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
                  book_id: hosted.book_id,
                  // Residual (apk): resolve free/purchased for float twin seed.
                  is_free:
                    entries.find((e) => e.book_id === hosted.book_id)
                      ?.is_free ?? null,
                });
              }}
              className="px-3 py-1.5 rounded border border-ink dark:border-bright text-sm font-mono hover:bg-ink/5 dark:hover:bg-bright/10 disabled:opacity-50"
            >
              Open hosted book in window
            </button>
            {/* Residual (gi/aeo): handoff hosted HTML into Write + seamless-port path. */}
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
                // Residual (aeo): body + seamless port honesty on host Open Write.
                data-write-seed-has-body={String(
                  Boolean(
                    hosted.view_format === "html" &&
                      Boolean(hosted.html?.trim()),
                  ),
                )}
                data-seamless-port={String(
                  (hosted.view_format || "html") === "html" &&
                    Boolean(hosted.document_id) &&
                    (libraryDocs || []).some(
                      (d) => d.document_id === hosted.document_id,
                    ),
                )}
                data-library-landed={String(
                  (libraryDocs || []).some(
                    (d) => d.document_id === hosted.document_id,
                  ),
                )}
                data-seamless-host-write="true"
                className="px-3 py-1.5 rounded border border-ink dark:border-bright text-sm font-mono underline hover:bg-ink/5 dark:hover:bg-bright/10"
                title="Open Write with hosted book as HTML draft + twin_seed (seamless port · seeds note-taker when empty)"
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
          {/* Residual (im/tb): HTML-first account library metrics + free honesty. */}
          <div
            className="text-[11px] font-mono opacity-80 space-y-0.5"
            data-testid="marketplace-library-metrics"
            data-doc-count={String(libraryDocs.length)}
            data-filtered-count={String(filteredLibraryDocs.length)}
            data-free-count={String(libraryFreeCount)}
            data-filtered-free-count={String(libraryFilteredFreeCount)}
            data-filters-active={String(libraryFiltersActive)}
            // Residual (ace): free_count provenance — api when server free_count loaded.
            data-free-count-source={
              libraryApiFreeCount != null && Number.isFinite(libraryApiFreeCount)
                ? "api"
                : "client"
            }
            data-library-api-free-count={
              libraryApiFreeCount != null && Number.isFinite(libraryApiFreeCount)
                ? String(libraryApiFreeCount)
                : ""
            }
            data-view-format="html"
            role="status"
          >
            <p>
              Library · docs={libraryDocs.length} · filtered=
              {filteredLibraryDocs.length} · free_inventory=
              {libraryFreeCount} · human view=HTML
              {libraryApiFreeCount != null && Number.isFinite(libraryApiFreeCount)
                ? " · free_count_source=api"
                : " · free_count_source=client"}
            </p>
            {libraryFiltersActive ? (
              <p
                data-testid="marketplace-library-filtered-free-honesty"
                data-filtered-free-count={String(libraryFilteredFreeCount)}
                data-library-free-count={String(libraryFreeCount)}
                role="status"
              >
                Filtered free honesty: visible_free_pd=
                {libraryFilteredFreeCount} · library_free_pd=
                {libraryFreeCount} · HTML host path only (not PDF)
              </p>
            ) : null}
          </div>
          <ul className="space-y-2" data-testid="library-doc-list">
            {filteredLibraryDocs.map((d) => (
              <li
                key={d.document_id}
                className="border rounded p-2 flex flex-wrap justify-between gap-2 items-center"
                data-testid={`library-doc-${d.document_id}`}
                data-view-format="html"
                // Residual (ace): free inventory machine attrs (parity catalog rows).
                data-license-class={d.license_class ?? ""}
                data-is-free={String(libraryDocIsFree(d))}
              >
                <div className="text-sm">
                  <strong>{d.title || d.document_id}</strong>
                  <div className="font-mono text-[11px] opacity-70">
                    {d.document_id}
                    {d.license_class ? ` · ${d.license_class}` : ""}
                    {libraryDocIsFree(d) ? " · free" : " · paid"}
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
                    {/* Residual (gi/acf): library → Write dual handoff; when
                        in-session host body matches this doc, seed twin with body
                        (recursive note-taker substrate richer than title-only). */}
                    <a
                      href={buildMarketplaceWriteHref({
                        documentId: d.document_id,
                        title: d.title,
                        html:
                          hosted?.document_id === d.document_id &&
                          hosted.view_format === "html" &&
                          hosted.html
                            ? hosted.html
                            : null,
                      })}
                      data-testid={`library-open-write-${d.document_id}`}
                      data-view-format="html"
                      data-document-id={d.document_id}
                      data-has-twin-seed="1"
                      data-write-seed-has-body={String(
                        Boolean(
                          hosted?.document_id === d.document_id &&
                            hosted.view_format === "html" &&
                            hosted.html?.trim(),
                        ),
                      )}
                      // Residual (aeo): library row is always account-landed;
                      // seamless-port true when in-session host body is present.
                      data-library-landed="true"
                      data-seamless-port={String(
                        (d.view_format || "html") === "html" &&
                          hosted?.document_id === d.document_id &&
                          hosted.view_format === "html" &&
                          Boolean(hosted.html?.trim()),
                      )}
                      data-seamless-host-write={String(
                        (d.view_format || "html") === "html",
                      )}
                      data-is-free={String(libraryDocIsFree(d))}
                      className="text-xs font-mono border rounded px-2 py-1 underline"
                      title={
                        hosted?.document_id === d.document_id &&
                        hosted.html?.trim()
                          ? "Open Write with library HTML body + twin_seed (seamless port · in-session host body)"
                          : "Open Write with library document as HTML draft + twin_seed (title seed until rehydrate · library-landed)"
                      }
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
