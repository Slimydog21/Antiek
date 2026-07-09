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
 * Residual (gi): Open Write HTML draft handoff from host-result + library
 * rows (marketplace → write flywheel; fl path).
 * Residual (gj): offline twin seed after host/purchase so marketplace books
 * enter the recursive note-taker substrate (parity with Write fz).
 * Residual (hl): offline-seed honesty machine attrs on marketplace twin seed
 * status (parity TwinNotes hh).
 * Residual (id): Settings deep-link for driver + twin seed readiness.
 * Residual (il): catalog HTML-first honesty metrics (no payment rails claim).
 * Residual (im): account library HTML-first metrics strip.
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
} from "../../api/marketplaceHost";
import { DecisionTreeDriverBadge } from "../../components/engagement/DecisionTreeDriverBadge";
import { openWindow } from "../../components/windows/openWindow";

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

export default function MarketplaceHost({
  ownerId = "operator",
}: MarketplaceHostProps) {
  const [entries, setEntries] = useState<CatalogEntryRow[]>([]);
  const [hosted, setHosted] = useState<HostResultResponse | null>(null);
  const [libraryHtml, setLibraryHtml] = useState<string | null>(null);
  const [libraryDocs, setLibraryDocs] = useState<LibraryDoc[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [receiptRef, setReceiptRef] = useState("manual-order-token-demo");
  /** Residual (dj): substring filter over catalog title/author/license. */
  const [filterQuery, setFilterQuery] = useState("");
  /** Residual (dl): filter over account library document titles/ids. */
  const [libraryFilter, setLibraryFilter] = useState("");
  /** Residual (dk): auto-open hosted HTML window after successful host. */
  const [autoOpenWindow, setAutoOpenWindow] = useState(true);

  const filteredEntries = useMemo(() => {
    const q = filterQuery.trim().toLowerCase();
    if (!q) return entries;
    return entries.filter((e) => {
      const hay =
        `${e.title} ${e.author} ${e.license_class} ${e.book_id}`.toLowerCase();
      return hay.includes(q);
    });
  }, [entries, filterQuery]);

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
      const cat = await fetchMarketplaceCatalog();
      setEntries(cat.entries);
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

  /** Residual (gj)/(hl): offline twin seed for hosted book (non-fatal; honest). */
  async function seedHostedTwins(result: HostResultResponse) {
    setTwinSeedStatus(null);
    setTwinSeedHonesty(null);
    try {
      const plain = (result.html || "")
        .replace(/<[^>]+>/g, " ")
        .replace(/\s+/g, " ")
        .trim()
        .slice(0, 2000);
      const seeded = await seedTwinNotes({
        asset_id: result.document_id,
        title: result.title || result.document_id,
        body_text: plain || result.title || result.document_id,
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
            <DecisionTreeDriverBadge />
            {/* Residual (id): Settings deep-link (driver + twin seed readiness). */}
            <p className="mt-1 text-[11px] font-mono">
              <a
                href="/settings"
                data-testid="marketplace-settings-link"
                className="underline opacity-80 hover:opacity-100"
                title="Open Settings for decision-tree driver and twin seed readiness"
              >
                Settings · driver & twin seed
              </a>
            </p>
          </div>
        </div>
      </header>

      <div className="flex flex-wrap gap-3 items-end mb-4">
        <button type="button" onClick={() => void loadCatalog()} disabled={busy}>
          Refresh catalog
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
            placeholder="Title, author, license…"
            className="border rounded px-2 py-1 min-w-[16rem]"
            disabled={busy}
            aria-label="Filter catalog"
          />
        </label>
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
      {/* Residual (il): HTML-first catalog honesty (no live payment rails). */}
      <div
        className="text-[11px] font-mono opacity-80 mb-2"
        data-testid="marketplace-catalog-metrics"
        data-entry-count={String(entries.length)}
        data-filtered-count={String(filteredEntries.length)}
        data-view-format="html"
        data-payment-rails="manual_receipt_only"
        role="status"
      >
        Catalog · entries={entries.length} · filtered={filteredEntries.length} ·
        human view=HTML · payment=manual receipt only (no live rails)
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
          >
            <div>
              <strong>{e.title}</strong>
              <div className="text-sm opacity-80">
                {e.author} · {e.license_class}
                {e.is_free ? " · free" : ""}
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
          No catalog matches for “{filterQuery.trim()}”.
        </p>
      ) : null}

      {hosted ? (
        <section className="mt-8 space-y-2" data-testid="host-result">
          <h2 className="text-lg font-medium">Hosted {hosted.document_id}</h2>
          <p>
            {hosted.already_hosted ? "Already hosted" : "Newly hosted"} ·{" "}
            {hosted.license_class} · view_format={hosted.view_format}
          </p>
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
                href={`/write?html_draft=${encodeURIComponent(hosted.document_id)}`}
                data-testid="marketplace-open-write"
                data-view-format="html"
                data-document-id={hosted.document_id}
                className="px-3 py-1.5 rounded border border-ink dark:border-bright text-sm font-mono underline hover:bg-ink/5 dark:hover:bg-bright/10"
                title="Open Write with hosted book as HTML draft handoff"
              >
                Open Write (HTML draft)
              </a>
            ) : null}
          </div>
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
                      href={`/write?html_draft=${encodeURIComponent(d.document_id)}`}
                      data-testid={`library-open-write-${d.document_id}`}
                      data-view-format="html"
                      data-document-id={d.document_id}
                      className="text-xs font-mono border rounded px-2 py-1 underline"
                      title="Open Write with library document as HTML draft handoff"
                    >
                      Open Write
                    </a>
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
