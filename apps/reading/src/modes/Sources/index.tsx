import { useState } from "react";

import LemonCard from "../../components/lemon/LemonCard";
import fieldStation from "../../brand/werner/sources/source_intake_field_station_v1.webp";
import {
  ingestSource,
  type IngestSourceResponse,
  type SourceKind,
} from "../../lib/api";
import "./source-intake-field-station.css";

type Status = "idle" | "ingesting" | "done";

interface IngestRow {
  url: string;
  kind: SourceKind | "auto";
  startedAt: number;
  finishedAt?: number;
  result?: IngestSourceResponse;
  failed?: boolean;
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
  if (row.failed) {
    return (
      <span className="px-2 py-0.5 rounded text-xs font-medium bg-emperor/20 text-emperor">
        error
      </span>
    );
  }
  if (!row.result) {
    return (
      <span className="px-2 py-0.5 rounded text-xs font-medium bg-sun/20 text-sun-deep dark:text-sun">
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
      <span className="px-2 py-0.5 rounded text-xs font-medium bg-ice-4 dark:bg-charcoal-1 text-ink dark:text-bright">
        skipped
      </span>
    );
  }
  return (
    <span className="px-2 py-0.5 rounded text-xs font-medium bg-emperor/20 text-emperor">
      error
    </span>
  );
}

export function SourceIntakeFieldStationFrame({
  phase,
  visualFixture = false,
  children,
}: {
  phase: "Ready" | "Receiving" | "Filed" | "Needs attention";
  visualFixture?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className={`source-intake-station ${visualFixture ? "source-intake-station--fixture" : ""}`}>
      <img src={fieldStation} alt="" aria-hidden="true" draggable={false} decoding="sync" data-testid="source-intake-station-art" />
      <div className="source-intake-station__veil" aria-hidden="true" />
      <header className="source-intake-station__masthead">
        <div>
          <p className="source-intake-station__eyebrow">Antiek · source intake field station</p>
          <h1>Bring the evidence into range</h1>
          <p>File papers, talks, feeds, and web sources into the substrate before you interrogate them.</p>
        </div>
        <div className="source-intake-station__phase"><span aria-hidden="true" /><strong>{phase}</strong></div>
      </header>
      <div className="source-intake-station__console">{children}</div>
    </div>
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
      } catch {
        setRows((prev) =>
          prev.map((r) =>
            r === row || (r.url === row.url && r.startedAt === row.startedAt)
              ? { ...r, failed: true, finishedAt: Date.now() }
              : r,
          ),
        );
      }
    }
    setStatus("done");
  }

  return (
    <SourceIntakeFieldStationFrame phase={status === "ingesting" ? "Receiving" : rows.some((row) => row.failed || row.result?.status === "error") ? "Needs attention" : rows.length > 0 ? "Filed" : "Ready"}>
        <div className="source-intake-station__workspace">

          <form
            onSubmit={handleSubmit}
            className="source-intake-station__form bg-ice-0 dark:bg-charcoal-2 border border-rule dark:border-charcoal-1 rounded-lg p-5 space-y-4"
          >
            <div>
              <label className="block text-xs font-medium text-ink dark:text-bright mb-1.5">
                URLs (one per line)
              </label>
              <textarea
                aria-label="Source URLs"
                value={urlInput}
                onChange={(e) => setUrlInput(e.target.value)}
                placeholder={
                  "https://arxiv.org/abs/2402.03300\n" +
                  "https://www.youtube.com/watch?v=...\n" +
                  "https://feeds.example.com/podcast.rss"
                }
                rows={4}
                className="w-full px-3 py-2 border border-rule dark:border-charcoal-1 rounded text-sm font-mono focus:outline-none focus:ring-2 focus:ring-sun focus:border-transparent"
                spellCheck={false}
              />
              {urlInput.trim() && (
                <p className="mt-1.5 text-xs text-shadow-1 dark:text-moonlight">
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

            <div className="source-intake-station__settings grid grid-cols-3 gap-3">
              <div>
                <label className="block text-xs font-medium text-ink dark:text-bright mb-1.5">
                  Kind
                </label>
                <select
                  aria-label="Source kind"
                  value={kindOverride}
                  onChange={(e) =>
                    setKindOverride(e.target.value as SourceKind | "auto")
                  }
                  className="w-full px-3 py-1.5 border border-rule dark:border-charcoal-1 rounded text-sm focus:outline-none focus:ring-2 focus:ring-sun"
                >
                  <option value="auto">Auto-detect</option>
                  <option value="arxiv">arXiv</option>
                  <option value="youtube">YouTube</option>
                  <option value="podcast">Podcast (RSS)</option>
                  <option value="url">URL</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-ink dark:text-bright mb-1.5">
                  Investigation id
                </label>
                <input
                  aria-label="Investigation id"
                  type="text"
                  value={investigationId}
                  onChange={(e) => setInvestigationId(e.target.value)}
                  className="w-full px-3 py-1.5 border border-rule dark:border-charcoal-1 rounded text-sm font-mono focus:outline-none focus:ring-2 focus:ring-sun"
                  spellCheck={false}
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-ink dark:text-bright mb-1.5">
                  Max episodes (podcast)
                </label>
                <input
                  aria-label="Maximum podcast episodes"
                  type="number"
                  value={maxEpisodes}
                  onChange={(e) =>
                    setMaxEpisodes(Math.max(1, Number(e.target.value) || 1))
                  }
                  min={1}
                  max={50}
                  className="w-full px-3 py-1.5 border border-rule dark:border-charcoal-1 rounded text-sm focus:outline-none focus:ring-2 focus:ring-sun"
                />
              </div>
            </div>

            <div className="flex items-center justify-end">
              <button
                type="submit"
                disabled={status === "ingesting" || !urlInput.trim()}
                className="px-4 py-1.5 bg-ink hover:bg-shadow-2 disabled:bg-glacial-1 dark:bg-slate-1 disabled:cursor-not-allowed text-white text-sm font-medium rounded transition-colors"
              >
                {status === "ingesting" ? "Ingesting…" : "Ingest"}
              </button>
            </div>
          </form>

          {rows.length > 0 && (
            <section className="source-intake-station__manifest">
              <h2 className="text-sm font-semibold text-ink dark:text-bright mb-3">
                Recent ingests
              </h2>
              {/* S10 acceptance: each adapter card → LemonCard. */}
              <div className="space-y-2">
                {rows.map((row, idx) => (
                  <LemonCard
                    key={`${row.url}-${row.startedAt}-${idx}`}
                    elevation="z1"
                    className="p-3 flex items-start justify-between gap-3"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <StatusBadge row={row} />
                        {row.result && (
                          <span className="text-xs text-shadow-1 dark:text-moonlight font-mono">
                            {row.result.detected_kind}
                          </span>
                        )}
                      </div>
                      <p className="mt-1 text-sm text-ink dark:text-bright truncate font-mono">
                        {row.url}
                      </p>
                      {row.result?.title && (
                        <p className="mt-0.5 text-xs text-ink-soft dark:text-starlight truncate">
                          {row.result.title}
                        </p>
                      )}
                      {row.result?.skipped_reason && (
                        <p className="mt-0.5 text-xs text-sun-deep dark:text-sun">
                          Skipped: {row.result.skipped_reason}
                        </p>
                      )}
                      {row.failed && (
                        <p className="mt-0.5 text-xs text-emperor break-all">
                          This source could not be received. Check the address and try again.
                        </p>
                      )}
                      {row.result?.error_message && (
                        <p className="mt-0.5 text-xs text-emperor break-all">
                          This source could not be received. Check the address and try again.
                        </p>
                      )}
                    </div>
                    <div className="text-right text-xs text-shadow-1 dark:text-moonlight shrink-0 min-w-[80px]">
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
                  </LemonCard>
                ))}
              </div>
            </section>
          )}
        </div>
    </SourceIntakeFieldStationFrame>
  );
}
