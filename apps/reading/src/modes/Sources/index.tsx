import { useState } from "react";

import {
  ingestSource,
  type IngestSourceResponse,
  type SourceKind,
} from "../../lib/api";
import HeaderBar from "../shared/HeaderBar";

type Status = "idle" | "ingesting" | "done";

interface IngestRow {
  url: string;
  kind: SourceKind | "auto";
  startedAt: number;
  finishedAt?: number;
  result?: IngestSourceResponse;
  error?: string;
}

function detectKindLabel(url: string): SourceKind {
  const u = url.toLowerCase().trim();
  if (u.includes("arxiv.org")) return "arxiv";
  if (u.includes("youtube.com") || u.includes("youtu.be")) return "youtube";
  if (
    u.endsWith(".rss") ||
    u.endsWith(".xml") ||
    u.includes("/rss") ||
    u.includes("/feed")
  ) {
    return "podcast";
  }
  return "url";
}

function StatusBadge({ row }: { row: IngestRow }) {
  if (row.error) {
    return (
      <span className="px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-700">
        error
      </span>
    );
  }
  if (!row.result) {
    return (
      <span className="px-2 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-700">
        ingesting…
      </span>
    );
  }
  const s = row.result.status;
  if (s === "ingested") {
    return (
      <span className="px-2 py-0.5 rounded text-xs font-medium bg-emerald-100 text-emerald-700">
        ingested
      </span>
    );
  }
  if (s === "skipped") {
    return (
      <span className="px-2 py-0.5 rounded text-xs font-medium bg-stone-200 text-stone-700">
        skipped
      </span>
    );
  }
  return (
    <span className="px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-700">
      error
    </span>
  );
}

/**
 * Sources mode — bulk-add URLs into the substrate graph.
 *
 * Operator pastes one or more URLs, optionally overrides the auto-
 * detected kind, picks an investigation_id (defaults to "__operator__"
 * for ambient ingest), and hits Ingest. Each row hits POST
 * /sources/ingest and reports status inline.
 *
 * No backpressure / pacing here — the substrate endpoint is
 * synchronous, so a long podcast feed will block until the adapter
 * returns. That's fine for the operator MVP; bulk pacing is a Sprint 13+
 * concern.
 */
export default function Sources() {
  const [urlInput, setUrlInput] = useState("");
  const [kindOverride, setKindOverride] = useState<SourceKind | "auto">("auto");
  const [investigationId, setInvestigationId] = useState("__operator__");
  const [maxEpisodes, setMaxEpisodes] = useState(10);
  const [status, setStatus] = useState<Status>("idle");
  const [rows, setRows] = useState<IngestRow[]>([]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!urlInput.trim()) return;
    const urls = urlInput
      .split(/\r?\n/)
      .map((u) => u.trim())
      .filter((u) => u.length > 0);
    if (urls.length === 0) return;

    setStatus("ingesting");
    const initial: IngestRow[] = urls.map((u) => ({
      url: u,
      kind: kindOverride,
      startedAt: Date.now(),
    }));
    setRows((prev) => [...initial, ...prev]);
    setUrlInput("");

    // Submit in series so the operator sees progress as it goes; the
    // synchronous adapters mean parallelism wouldn't buy much anyway.
    for (let i = 0; i < initial.length; i++) {
      const row = initial[i];
      try {
        const result = await ingestSource({
          url: row.url,
          kind: kindOverride === "auto" ? undefined : kindOverride,
          investigation_id: investigationId.trim() || "__operator__",
          max_episodes: maxEpisodes,
        });
        setRows((prev) =>
          prev.map((r) =>
            r === row || (r.url === row.url && r.startedAt === row.startedAt)
              ? { ...r, result, finishedAt: Date.now() }
              : r,
          ),
        );
      } catch (exc) {
        const msg = exc instanceof Error ? exc.message : String(exc);
        setRows((prev) =>
          prev.map((r) =>
            r === row || (r.url === row.url && r.startedAt === row.startedAt)
              ? { ...r, error: msg, finishedAt: Date.now() }
              : r,
          ),
        );
      }
    }
    setStatus("done");
  }

  return (
    <div className="flex flex-col h-screen bg-stone-50">
      <HeaderBar />
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-6 py-8">
          <h1 className="text-2xl font-semibold tracking-tight text-stone-900">
            Sources
          </h1>
          <p className="mt-1 text-sm text-stone-600">
            Add arXiv papers, YouTube transcripts, podcast feeds, or any
            URL into the substrate graph. Auto-detects source kind from
            the URL.
          </p>

          <form
            onSubmit={handleSubmit}
            className="mt-6 bg-white border border-stone-200 rounded-lg p-5 space-y-4"
          >
            <div>
              <label className="block text-xs font-medium text-stone-700 mb-1.5">
                URLs (one per line)
              </label>
              <textarea
                value={urlInput}
                onChange={(e) => setUrlInput(e.target.value)}
                placeholder={
                  "https://arxiv.org/abs/2402.03300\n" +
                  "https://www.youtube.com/watch?v=...\n" +
                  "https://feeds.example.com/podcast.rss"
                }
                rows={4}
                className="w-full px-3 py-2 border border-stone-300 rounded text-sm font-mono focus:outline-none focus:ring-2 focus:ring-stone-400 focus:border-transparent"
                spellCheck={false}
              />
              {urlInput.trim() && (
                <p className="mt-1.5 text-xs text-stone-500">
                  Detected:{" "}
                  {Array.from(
                    new Set(
                      urlInput
                        .split(/\r?\n/)
                        .map((u) => u.trim())
                        .filter(Boolean)
                        .map(detectKindLabel),
                    ),
                  ).join(", ") || "—"}
                </p>
              )}
            </div>

            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="block text-xs font-medium text-stone-700 mb-1.5">
                  Kind
                </label>
                <select
                  value={kindOverride}
                  onChange={(e) =>
                    setKindOverride(e.target.value as SourceKind | "auto")
                  }
                  className="w-full px-3 py-1.5 border border-stone-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-stone-400"
                >
                  <option value="auto">Auto-detect</option>
                  <option value="arxiv">arXiv</option>
                  <option value="youtube">YouTube</option>
                  <option value="podcast">Podcast (RSS)</option>
                  <option value="url">URL</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-stone-700 mb-1.5">
                  Investigation id
                </label>
                <input
                  type="text"
                  value={investigationId}
                  onChange={(e) => setInvestigationId(e.target.value)}
                  className="w-full px-3 py-1.5 border border-stone-300 rounded text-sm font-mono focus:outline-none focus:ring-2 focus:ring-stone-400"
                  spellCheck={false}
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-stone-700 mb-1.5">
                  Max episodes (podcast)
                </label>
                <input
                  type="number"
                  value={maxEpisodes}
                  onChange={(e) =>
                    setMaxEpisodes(Math.max(1, Number(e.target.value) || 1))
                  }
                  min={1}
                  max={50}
                  className="w-full px-3 py-1.5 border border-stone-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-stone-400"
                />
              </div>
            </div>

            <div className="flex items-center justify-end">
              <button
                type="submit"
                disabled={status === "ingesting" || !urlInput.trim()}
                className="px-4 py-1.5 bg-stone-900 hover:bg-stone-800 disabled:bg-stone-300 disabled:cursor-not-allowed text-white text-sm font-medium rounded transition-colors"
              >
                {status === "ingesting" ? "Ingesting…" : "Ingest"}
              </button>
            </div>
          </form>

          {rows.length > 0 && (
            <section className="mt-8">
              <h2 className="text-sm font-semibold text-stone-700 mb-3">
                Recent ingests
              </h2>
              <ul className="space-y-2">
                {rows.map((row, idx) => (
                  <li
                    key={`${row.url}-${row.startedAt}-${idx}`}
                    className="bg-white border border-stone-200 rounded p-3 flex items-start justify-between gap-3"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <StatusBadge row={row} />
                        {row.result && (
                          <span className="text-xs text-stone-500 font-mono">
                            {row.result.detected_kind}
                          </span>
                        )}
                      </div>
                      <p className="mt-1 text-sm text-stone-900 truncate font-mono">
                        {row.url}
                      </p>
                      {row.result?.title && (
                        <p className="mt-0.5 text-xs text-stone-600 truncate">
                          {row.result.title}
                        </p>
                      )}
                      {row.result?.skipped_reason && (
                        <p className="mt-0.5 text-xs text-amber-700">
                          Skipped: {row.result.skipped_reason}
                        </p>
                      )}
                      {row.error && (
                        <p className="mt-0.5 text-xs text-red-700 break-all">
                          {row.error}
                        </p>
                      )}
                      {row.result?.error_message && (
                        <p className="mt-0.5 text-xs text-red-700 break-all">
                          {row.result.error_message}
                        </p>
                      )}
                    </div>
                    <div className="text-right text-xs text-stone-500 shrink-0 min-w-[80px]">
                      {row.result && (
                        <>
                          <div>{row.result.chunks_written} chunks</div>
                          {row.result.episodes_processed > 0 && (
                            <div>
                              {row.result.episodes_ingested}/
                              {row.result.episodes_processed} eps
                            </div>
                          )}
                        </>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </main>
    </div>
  );
}
