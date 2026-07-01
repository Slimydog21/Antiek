import { useCallback, useEffect, useMemo, useState } from "react";

import LemonTable from "../../components/lemon/LemonTable";
import LemonTag from "../../components/lemon/LemonTag";
import { useInWindow } from "../../components/windows/windowHostContext";
import { apiFetch } from "../../lib/api";
import { useOpenDocument } from "../../lib/openDocument";

/**
 * Documents listing UI (master-spec §4.1).
 *
 * Operator-facing list of substrate-attached documents with
 * source-tier + investigation filters. Each row opens the document in the ONE
 * Reader via `openDocument` (SPR-05 — was a `/wrestle/:id` mis-route, the pdf.js
 * page-1 surface that can't fetch by id; now the one door → the gated Reader).
 */

interface DocumentRow {
  document_id: string;
  title: string | null;
  source_uri: string | null;
  document_type: string | null;
  source_tier: number;
  investigation_id: string | null;
  content_class: string | null;
  ip_holder_id: string | null;
}

const TIER_FILTERS = ["all", 1, 2, 3, 4, 5] as const;
type TierFilter = (typeof TIER_FILTERS)[number];

function sourceTierLabel(tier: number): string {
  if (tier === 1) return "Primary source";
  if (tier === 2) return "Strong source";
  if (tier === 3) return "Useful source";
  if (tier === 4) return "Needs review";
  if (tier === 5) return "Unverified";
  return "Unrated source";
}

function documentTypeLabel(documentType: string | null): string {
  if (!documentType) return "Source";
  if (documentType.toLowerCase() === "pdf") return "PDF";
  return documentType
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part[0]?.toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

function contentClassLabel(contentClass: string | null): string | null {
  if (!contentClass) return null;
  if (contentClass === "public_domain") return "Public domain";
  if (contentClass === "platform_authored") return "Platform-authored";
  if (contentClass === "opt_in_licensed") return "Publisher licensed";
  if (contentClass === "publisher_opted_in") return "Publisher licensed";
  if (contentClass === "source_declared_open") return "Open source";
  if (contentClass === "restricted_pending_opt_in") return "Preview only";
  if (contentClass === "gated_metadata_only") return "Preview only";
  if (contentClass === "taken_down") return "Unavailable";
  if (contentClass === "personal_reading") return "Private reading";
  if (contentClass === "user_owned") return "Private";
  if (contentClass === "user_public_contribution") return "Public contribution";
  return "Unknown rights";
}

function sourceSummary(row: DocumentRow): string {
  return [
    documentTypeLabel(row.document_type),
    contentClassLabel(row.content_class),
  ].filter(Boolean).join(" · ");
}

function researchHandleLabel(investigationId: string): string {
  const handle = visibleResearchHandle(investigationId);
  return handle ? `Research handle ${handle}` : "Linked research";
}

function visibleResearchHandle(investigationId: string): string {
  return investigationId.replace(/^inv-/, "");
}

function researchFilterParam(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "";
  return trimmed.startsWith("inv-") ? trimmed : `inv-${trimmed}`;
}

export default function DocumentsIndex() {
  const openDocument = useOpenDocument();
  // SPR-09 window-adaptation contract: in a WorkspaceWindow, fill the host
  // container and drop the opaque full-bleed bg. The full-page route remains
  // the normal h-screen operator surface.
  const inWindow = useInWindow();
  const [rows, setRows] = useState<DocumentRow[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [tierFilter, setTierFilter] = useState<TierFilter>("all");
  const [investigationFilter, setInvestigationFilter] = useState<string>("");

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (tierFilter !== "all") {
        params.set("source_tier", String(tierFilter));
      }
      if (investigationFilter.trim()) {
        params.set("investigation_id", researchFilterParam(investigationFilter));
      }
      params.set("limit", "500");
      const resp = await apiFetch(`/documents?${params.toString()}`);
      if (!resp.ok) {
        throw new Error(`Could not load documents (HTTP ${resp.status}).`);
      }
      const data = await resp.json();
      setRows(data.documents ?? []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [tierFilter, investigationFilter]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const counts = useMemo(() => {
    const acc = [0, 0, 0, 0, 0]; // tier 1..5
    for (const r of rows) {
      if (r.source_tier >= 1 && r.source_tier <= 5) {
        acc[r.source_tier - 1] += 1;
      }
    }
    return acc;
  }, [rows]);

  return (
    <div className={`flex flex-col ${inWindow ? "h-full" : "h-screen"}`}>
      <main
        className={`flex-1 overflow-y-auto ${inWindow ? "bg-transparent" : "bg-ice-0 dark:bg-charcoal-2"}`}
      >
        <div className="max-w-4xl mx-auto px-8 py-10 space-y-6">
          <header className="space-y-2">
            <h1 className="text-2xl font-serif text-ink dark:text-bright">
              Documents
            </h1>
            <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
              Review the sources attached to your workspace: PDFs, web pages,
              transcripts, and imported references. Quality labels show how
              much confidence the app has in each source before you open it.
            </p>
          </header>

          <section className="grid grid-cols-5 gap-2">
            {[1, 2, 3, 4, 5].map((t) => (
              <div
                key={t}
                className="border border-rule dark:border-charcoal-1 rounded-md px-3 py-2 text-center"
              >
                <p className="text-base font-serif text-ink dark:text-bright">
                  {counts[t - 1]}
                </p>
                <p className="text-[10px] font-mono text-shadow-1 dark:text-moonlight uppercase">
                  {sourceTierLabel(t)}
                </p>
              </div>
            ))}
          </section>

          <section className="border border-rule dark:border-charcoal-1 rounded-md p-4 space-y-3">
            <div className="flex items-center gap-2 flex-wrap">
              {TIER_FILTERS.map((t) => (
                <button
                  key={String(t)}
                  type="button"
                  onClick={() => setTierFilter(t)}
                  className={`px-2.5 py-1 rounded-md text-xs font-mono transition-colors ${
                    tierFilter === t
                      ? "bg-ink text-white"
                      : "bg-ice-3 dark:bg-charcoal-1 text-ink dark:text-bright hover:bg-ice-4 dark:bg-charcoal-1"
                  }`}
                >
                  {t === "all" ? "All" : sourceTierLabel(t)}
                </button>
              ))}
            </div>
            <input
              type="text"
              value={investigationFilter}
              onChange={(e) => setInvestigationFilter(e.target.value)}
              aria-label="Filter by research handle"
              placeholder="Paste research handle to filter"
              className="w-full text-sm font-serif text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2"
            />
          </section>

          {error && (
            <p className="text-sm text-emperor border border-red-200 bg-red-50 px-3 py-2 rounded">
              {error}
            </p>
          )}

          {loading && (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">Loading…</p>
          )}

          {!loading && rows.length === 0 && !error && (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">
              No documents match this filter.
            </p>
          )}

          {rows.length > 0 && (
            // S10 acceptance: DocumentsIndex uses LemonTable.
            <LemonTable
              rows={rows}
              rowKey={(r) => r.document_id}
              onRowClick={(r) => openDocument(r.document_id)}
              columns={[
                {
                  key: "title",
                  header: "Title",
                  width: "50%",
                  render: (r) => (
                    <div>
                      <p className="font-serif text-ink dark:text-bright truncate">
                        {r.title ?? "Untitled source"}
                      </p>
                      <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight truncate">
                        {sourceSummary(r)}
                      </p>
                      {r.source_uri && (
                        <p className="text-[10px] font-mono text-ink-mute dark:text-moonlight truncate">
                          {r.source_uri}
                        </p>
                      )}
                    </div>
                  ),
                },
                {
                  key: "investigation",
                  header: "Research",
                  render: (r) =>
                    r.investigation_id ? (
                      <span className="font-serif text-[12px] text-ink-soft dark:text-starlight">
                        {researchHandleLabel(r.investigation_id)}
                      </span>
                    ) : (
                      <span className="font-serif text-[12px] text-ink-mute dark:text-moonlight italic">
                        No linked research
                      </span>
                    ),
                },
                {
                  key: "tier",
                  header: "Quality",
                  align: "right",
                  render: (r) => (
                    <LemonTag
                      colour={
                        r.source_tier <= 2
                          ? "aurora"
                          : r.source_tier <= 4
                            ? "muted"
                            : "sun"
                      }
                    >
                      {sourceTierLabel(r.source_tier)}
                    </LemonTag>
                  ),
                },
              ]}
            />
          )}
        </div>
      </main>
    </div>
  );
}
