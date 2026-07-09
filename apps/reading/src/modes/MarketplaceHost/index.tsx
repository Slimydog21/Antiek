/**
 * Marketplace host-into-account mode — catalog → host → HTML library.
 * PDF may be purchase/ingest source only; view is always HTML.
 */

import { useCallback, useEffect, useState } from "react";
import {
  fetchAccountLibrary,
  fetchMarketplaceCatalog,
  hostBookIntoAccount,
  type CatalogEntryRow,
  type HostResultResponse,
} from "../../api/marketplaceHost";

export type MarketplaceHostProps = {
  ownerId?: string;
};

export default function MarketplaceHost({
  ownerId = "operator",
}: MarketplaceHostProps) {
  const [entries, setEntries] = useState<CatalogEntryRow[]>([]);
  const [hosted, setHosted] = useState<HostResultResponse | null>(null);
  const [libraryHtml, setLibraryHtml] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  return (
    <div className="h-full overflow-y-auto p-6" data-view-format="html">
      <header className="mb-6 space-y-1">
        <h1 className="text-2xl font-semibold">Marketplace · host into account</h1>
        <p className="text-sm opacity-80">
          Host public-domain catalog books into your Antiek library. Purchased
          titles require a receipt (manual order token — no live payment rails
          here). Human view is HTML, never PDF.
        </p>
      </header>

      <button type="button" onClick={() => void loadCatalog()} disabled={busy}>
        Refresh catalog
      </button>

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
              <span className="text-sm opacity-70">requires receipt</span>
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
