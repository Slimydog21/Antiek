import { useEffect, useRef, useState } from "react";

import { fetchToolConnections } from "../../api/toolConnections";
import { searchResearchTool, type ResearchToolCandidate, type SearchToolVendor } from "../../api/researchToolSearch";
import { LemonButton } from "../../components/lemon";

const SEARCHABLE = new Set<SearchToolVendor>(["youtube", "x"]);

export default function ConnectedToolSearch() {
  const [available, setAvailable] = useState<SearchToolVendor[]>([]);
  const [vendor, setVendor] = useState<SearchToolVendor>("youtube");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ResearchToolCandidate[]>([]);
  const [busy, setBusy] = useState(false);
  const [inventoryError, setInventoryError] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<{ operationId: string; vendor: SearchToolVendor; query: string } | null>(null);
  const generation = useRef(0);

  async function loadInventory() {
    const current = ++generation.current;
    setInventoryError(false);
    try {
      const rows = await fetchToolConnections();
      if (current !== generation.current) return;
      const next = rows
        .filter((row) => row.credential_present && row.status === "configured_unverified" && SEARCHABLE.has(row.vendor as SearchToolVendor))
        .map((row) => row.vendor as SearchToolVendor);
      setAvailable(next);
      if (next.length > 0 && !next.includes(vendor)) setVendor(next[0]);
    } catch {
      if (current === generation.current) setInventoryError(true);
    }
  }

  useEffect(() => {
    void loadInventory();
    return () => { generation.current += 1; };
  }, []);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy || !query.trim() || !available.includes(vendor)) return;
    const current = ++generation.current;
    setBusy(true);
    setError(null);
    setResults([]);
    try {
      const identity = pending && pending.vendor === vendor && pending.query === query.trim()
        ? pending
        : { operationId: `tool-search-${crypto.randomUUID()}`, vendor, query: query.trim() };
      setPending(identity);
      const response = await searchResearchTool({ ...identity });
      if (current === generation.current) { setResults(response.candidates); setPending(null); }
    } catch (cause) {
      if (current === generation.current) {
        setError(cause instanceof Error ? cause.message : "Can't search this provider.");
      }
    } finally {
      if (current === generation.current) setBusy(false);
    }
  }

  const noTools = !inventoryError && available.length === 0;
  return (
    <section aria-labelledby="connected-tool-search-title" className="mt-6 border-y border-rule dark:border-charcoal-1 py-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 id="connected-tool-search-title" className="text-sm font-semibold text-ink dark:text-bright">Search connected tools</h2>
          <p className="mt-1 max-w-2xl text-xs text-ink-soft dark:text-starlight">
            Find source candidates with your own provider account. Results stay outside Antiek until you explicitly ingest them.
          </p>
        </div>
        <a href="/settings" className="text-xs font-medium text-ocean hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-ocean">Manage tools</a>
      </div>

      {inventoryError ? (
        <div role="alert" className="mt-4 flex flex-wrap items-center gap-3 text-sm text-emperor">
          Tool inventory is unavailable. <LemonButton size="sm" variant="secondary" onClick={() => void loadInventory()}>Retry</LemonButton>
        </div>
      ) : noTools ? (
        <p className="mt-4 text-sm text-ink-soft dark:text-starlight">Connect YouTube or X in Settings to search with your own account.</p>
      ) : (
        <form onSubmit={submit} className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end">
          <label className="text-xs font-medium text-ink dark:text-bright sm:w-36">
            Provider
            <select value={vendor} onChange={(event) => { setVendor(event.target.value as SearchToolVendor); setResults([]); setError(null); }} disabled={busy}
              className="mt-1 min-h-11 w-full rounded border border-rule bg-ice-0 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ocean dark:border-charcoal-1 dark:bg-charcoal-2">
              {available.map((item) => <option key={item} value={item}>{item === "x" ? "X" : "YouTube"}</option>)}
            </select>
          </label>
          <label className="min-w-0 flex-1 text-xs font-medium text-ink dark:text-bright">
            What sources are you looking for?
            <input value={query} onChange={(event) => setQuery(event.target.value)} disabled={busy} maxLength={500}
              className="mt-1 min-h-11 w-full rounded border border-rule bg-ice-0 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ocean dark:border-charcoal-1 dark:bg-charcoal-2"
              placeholder={vendor === "x" ? "Recent reporting on battery recycling" : "Lectures about solid-state batteries"} />
          </label>
          <LemonButton type="submit" size="md" variant="primary" className="min-h-11" disabled={busy || !query.trim()}>{busy ? "Searching…" : "Search"}</LemonButton>
        </form>
      )}

      {busy && <p role="status" aria-live="polite" className="mt-4 text-sm text-ink-soft dark:text-starlight">Searching {vendor === "x" ? "X" : "YouTube"} with your connected account…</p>}
      {error && <p role="alert" className="mt-4 text-sm text-emperor">{error}</p>}
      {!busy && !error && results.length === 0 && query.trim() && available.length > 0 && (
        <p role="status" className="mt-4 text-sm text-ink-soft dark:text-starlight">No candidates yet. Try a more specific query or another connected provider.</p>
      )}
      {results.length > 0 && (
        <ol aria-label="Source candidates" className="mt-5 divide-y divide-rule border-y border-rule dark:divide-charcoal-1 dark:border-charcoal-1">
          {results.map((result) => (
            <li key={`${vendor}-${result.external_id}`} className="py-4">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-shadow-1 dark:text-moonlight">
                <span className="font-semibold uppercase tracking-wide">{vendor === "x" ? "X" : "YouTube"}</span>
                {result.author && <span className="break-words">{result.author}</span>}
                {result.published_at && <time dateTime={result.published_at}>{new Date(result.published_at).toLocaleDateString()}</time>}
                <span>Candidate · not ingested</span>
              </div>
              <a href={result.url} target="_blank" rel="noreferrer" className="mt-1 block break-words text-sm font-medium leading-6 text-ink hover:text-ocean hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-ocean dark:text-bright">
                {result.title_or_text || result.url}
              </a>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
