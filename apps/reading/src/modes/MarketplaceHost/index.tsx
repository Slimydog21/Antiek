/**
 * Marketplace host-into-account mode — catalog → host → HTML library.
 * PDF may be purchase/ingest source only; view is always HTML.
 */

import { useCallback, useEffect, useState } from "react";
import {
  fetchAccountLibrary,
  fetchMarketplaceCatalog,
  hostBookIntoAccount,
  purchaseAndHost,
  type CatalogEntryRow,
  type HostResultResponse,
} from "../../api/marketplaceHost";
import { openWindow } from "../../components/windows/openWindow";

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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [receiptRef, setReceiptRef] = useState("manual-order-token-demo");

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

  useEffect(() => {
    void loadCatalog();
  }, [loadCatalog]);

  async function onHost(bookId: string) {
    setBusy(true);
    setError(null);
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
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onPurchaseAndHost(entry: CatalogEntryRow) {
    setBusy(true);
    setError(null);
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
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="h-full overflow-y-auto p-6" data-view-format="html" data-testid="marketplace-host-mode">
      <header className="mb-6 space-y-1">
        <h1 className="text-2xl font-semibold">Marketplace · host into account</h1>
        <p className="text-sm opacity-80">
          Host public-domain catalog books into your Antiek library. Purchased
          titles use a manual receipt token (no live payment rails). Human view
          is HTML, never PDF.
        </p>
      </header>

      <div className="flex flex-wrap gap-3 items-end mb-4">
        <button type="button" onClick={() => void loadCatalog()} disabled={busy}>
          Refresh catalog
        </button>
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
      </div>

      {error ? (
        <p className="mt-4 text-red-600" role="alert">
          {error}
        </p>
      ) : null}

      <ul className="mt-4 space-y-2" data-testid="catalog-list">
        {entries.map((e) => (
          <li key={e.book_id} className="border rounded p-3 flex justify-between gap-4">
            <div>
              <strong>{e.title}</strong>
              <div className="text-sm opacity-80">
                {e.author} · {e.license_class}
                {e.is_free ? " · free" : ""}
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

      {hosted ? (
        <section className="mt-8 space-y-2" data-testid="host-result">
          <h2 className="text-lg font-medium">Hosted {hosted.document_id}</h2>
          <p>
            {hosted.already_hosted ? "Already hosted" : "Newly hosted"} ·{" "}
            {hosted.license_class} · view_format={hosted.view_format}
          </p>
          {/* Residual (bt): open hosted HTML book in a floating window. */}
          <button
            type="button"
            data-testid="open-hosted-in-window"
            disabled={hosted.view_format !== "html" || !hosted.html}
            onClick={() => {
              if (hosted.view_format !== "html") {
                setError("view_format must be html — PDF is not a reading surface");
                return;
              }
              openWindow(
                "hosted_html_document",
                {
                  document_id: hosted.document_id,
                  title: hosted.title,
                  html: hosted.html,
                  view_format: hosted.view_format,
                  license_class: hosted.license_class,
                  owner_id: hosted.owner_id,
                  source: "marketplace_host",
                },
                {
                  id: `win:hosted:${hosted.document_id}`,
                  title: hosted.title || "Hosted book",
                },
              );
            }}
            className="px-3 py-1.5 rounded border border-ink dark:border-bright text-sm font-mono hover:bg-ink/5 dark:hover:bg-bright/10 disabled:opacity-50"
          >
            Open hosted book in window
          </button>
          <div
            className="prose border rounded p-3 text-sm"
            data-testid="hosted-html"
            dangerouslySetInnerHTML={{ __html: hosted.html }}
          />
        </section>
      ) : null}

      {libraryHtml ? (
        <section className="mt-6">
          <h2 className="text-lg font-medium">Library</h2>
          <div
            className="prose border rounded p-3 text-sm"
            data-testid="library-html"
            dangerouslySetInnerHTML={{ __html: libraryHtml }}
          />
        </section>
      ) : null}
    </div>
  );
}
