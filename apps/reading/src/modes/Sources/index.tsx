import { useEffect, useState } from "react";

import LemonCard from "../../components/lemon/LemonCard";
import {
  API_BASE,
  apiFetch,
  ingestSource,
  type IngestSourceResponse,
  type SourceKind,
} from "../../lib/api";

type Status = "idle" | "ingesting" | "done";

interface IngestRow {
  url: string;
  kind: SourceKind | "auto";
  startedAt: number;
  finishedAt?: number;
  result?: IngestSourceResponse;
  error?: string;
}

interface SourceGateRow {
  source: string;
  blocked: boolean;
  failures: string[];
}

interface SourceGate {
  sourcePath: string;
  state: "missing" | "invalid" | "clean" | "blocked" | "unknown";
  referenceSource: string;
  sourceCount: number;
  blockedCount: number;
  rows: SourceGateRow[];
  error: string | null;
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

function record(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function nonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed || null;
}

function nonNegativeInteger(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value) && value >= 0) {
    return Math.floor(value);
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed) && parsed >= 0) return Math.floor(parsed);
  }
  return 0;
}

function safeSourceGate(value: unknown): SourceGate {
  const body = record(value);
  const state = nonEmptyString(body?.state);
  const rows = Array.isArray(body?.rows)
    ? body.rows.flatMap((item) => {
        const row = record(item);
        const source = nonEmptyString(row?.source);
        if (!source) return [];
        return [{
          source,
          blocked: row?.blocked === true,
          failures: Array.isArray(row?.failures)
            ? row.failures.flatMap((failure) => {
                const text = nonEmptyString(failure);
                return text ? [text] : [];
              })
            : [],
        }];
      })
    : [];
  return {
    sourcePath: nonEmptyString(body?.source_path) ?? "reports/source_census.json",
    state:
      state === "missing" || state === "invalid" || state === "clean" || state === "blocked"
        ? state
        : "unknown",
    referenceSource: nonEmptyString(body?.reference_source) ?? "arxiv",
    sourceCount: nonNegativeInteger(body?.source_count),
    blockedCount: nonNegativeInteger(body?.blocked_count),
    rows,
    error: nonEmptyString(body?.error),
  };
}

async function fetchSourceGate(): Promise<SourceGate> {
  const resp = await apiFetch(`${API_BASE}/coordination/source-gate`);
  if (!resp.ok) {
    throw new Error(`GET /coordination/source-gate failed: HTTP ${resp.status}`);
  }
  return safeSourceGate(await resp.json());
}

function SourceGateStatus({
  sourceGate,
  sourceGateError,
}: {
  sourceGate: SourceGate | null;
  sourceGateError: string | null;
}) {
  if (sourceGateError) {
    return (
      <LemonCard elevation="z1" className="mt-5 p-4 border-emperor/40">
        <p className="text-sm font-medium text-emperor">Source gate unavailable</p>
        <p className="mt-1 text-xs text-ink-soft dark:text-starlight break-all">
          {sourceGateError}
        </p>
      </LemonCard>
    );
  }
  if (!sourceGate) {
    return (
      <LemonCard elevation="z1" className="mt-5 p-4">
        <p className="text-sm font-medium text-ink dark:text-bright">
          Source gate loading
        </p>
      </LemonCard>
    );
  }

  const firstBlocked = sourceGate.rows.find((row) => row.blocked);
  const detail =
    firstBlocked && firstBlocked.failures.length > 0
      ? `${firstBlocked.source}: ${firstBlocked.failures[0]}`
      : sourceGate.error;
  const tone =
    sourceGate.state === "clean"
      ? "text-emerald-700 dark:text-emerald-300"
      : sourceGate.state === "blocked" || sourceGate.state === "invalid"
        ? "text-emperor"
        : "text-sun-deep dark:text-sun";

  return (
    <LemonCard elevation="z1" className="mt-5 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className={`text-sm font-semibold ${tone}`}>
            Source gate {sourceGate.state} · {sourceGate.blockedCount}/
            {sourceGate.sourceCount} blocked
          </p>
          <p className="mt-1 text-xs text-ink-soft dark:text-starlight">
            Reference: {sourceGate.referenceSource}. Source: {sourceGate.sourcePath}.
          </p>
        </div>
        <span className="px-2 py-0.5 rounded bg-ice-4 dark:bg-charcoal-1 text-xs font-mono text-ink dark:text-bright">
          {sourceGate.state}
        </span>
      </div>
      {detail && (
        <p className="mt-2 text-xs text-ink-soft dark:text-starlight break-words">
          {detail}
        </p>
      )}
    </LemonCard>
  );
}

function StatusBadge({ row }: { row: IngestRow }) {
  if (row.error) {
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
  const [sourceGate, setSourceGate] = useState<SourceGate | null>(null);
  const [sourceGateError, setSourceGateError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchSourceGate()
      .then((gate) => {
        if (cancelled) return;
        setSourceGate(gate);
        setSourceGateError(null);
      })
      .catch((exc) => {
        if (cancelled) return;
        setSourceGateError(exc instanceof Error ? exc.message : String(exc));
      });
    return () => {
      cancelled = true;
    };
  }, []);

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
    <div className="flex flex-col h-screen bg-ice-1 dark:bg-charcoal-2">
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-6 py-8">
          <h1 className="text-2xl font-semibold tracking-tight text-ink dark:text-bright">
            Sources
          </h1>
          <p className="mt-1 text-sm text-ink-soft dark:text-starlight">
            Add arXiv papers, YouTube transcripts, podcast feeds, or any
            URL into the substrate graph. Auto-detects source kind from
            the URL.
          </p>
          <SourceGateStatus
            sourceGate={sourceGate}
            sourceGateError={sourceGateError}
          />

          <form
            onSubmit={handleSubmit}
            className="mt-6 bg-ice-0 dark:bg-charcoal-2 border border-rule dark:border-charcoal-1 rounded-lg p-5 space-y-4"
          >
            <div>
              <label
                htmlFor="sources-url-input"
                className="block text-xs font-medium text-ink dark:text-bright mb-1.5"
              >
                URLs (one per line)
              </label>
              <textarea
                id="sources-url-input"
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

            <div className="grid grid-cols-3 gap-3">
              <div>
                <label
                  htmlFor="sources-kind"
                  className="block text-xs font-medium text-ink dark:text-bright mb-1.5"
                >
                  Kind
                </label>
                <select
                  id="sources-kind"
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
                <label
                  htmlFor="sources-investigation-id"
                  className="block text-xs font-medium text-ink dark:text-bright mb-1.5"
                >
                  Investigation id
                </label>
                <input
                  id="sources-investigation-id"
                  type="text"
                  value={investigationId}
                  onChange={(e) => setInvestigationId(e.target.value)}
                  className="w-full px-3 py-1.5 border border-rule dark:border-charcoal-1 rounded text-sm font-mono focus:outline-none focus:ring-2 focus:ring-sun"
                  spellCheck={false}
                />
              </div>
              <div>
                <label
                  htmlFor="sources-max-episodes"
                  className="block text-xs font-medium text-ink dark:text-bright mb-1.5"
                >
                  Max episodes (podcast)
                </label>
                <input
                  id="sources-max-episodes"
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
            <section className="mt-8">
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
                      {row.error && (
                        <p className="mt-0.5 text-xs text-emperor break-all">
                          {row.error}
                        </p>
                      )}
                      {row.result?.error_message && (
                        <p className="mt-0.5 text-xs text-emperor break-all">
                          {row.result.error_message}
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
      </main>
    </div>
  );
}
