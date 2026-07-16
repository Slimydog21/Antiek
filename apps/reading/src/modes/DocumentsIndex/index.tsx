import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import LemonTable from "../../components/lemon/LemonTable";
import LemonTag from "../../components/lemon/LemonTag";
import archiveAtlas from "../../brand/werner/documents/evidence_archive_atlas_v1.webp";
import { apiFetch } from "../../lib/api";
import "./evidence-archive-atlas.css";

/**
 * Documents listing UI (master-spec §4.1).
 *
 * Operator-facing list of substrate-attached documents with
 * source-tier + investigation filters. Each row links to
 * /wrestle/:documentId where the existing PDF + region-selection
 * surface lives.
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

export type EvidenceArchivePhase = "Surveying" | "Charted" | "Empty range" | "Needs attention";

export function EvidenceArchiveAtlasFrame({ phase, visualFixture = false, children }: { phase: EvidenceArchivePhase; visualFixture?: boolean; children: React.ReactNode }) {
  return (
    <div className={`evidence-archive-atlas ${visualFixture ? "evidence-archive-atlas--fixture" : ""}`}>
      <img src={archiveAtlas} alt="" aria-hidden="true" draggable={false} decoding="async" data-testid="evidence-archive-atlas-art" />
      <div className="evidence-archive-atlas__veil" aria-hidden="true" />
      <header className="evidence-archive-atlas__masthead">
        <div>
          <p className="evidence-archive-atlas__eyebrow">Antiek · evidence archive atlas</p>
          <h1>Survey what the substrate holds</h1>
          <p>Chart the evidence already filed in Antiek, then open any record in its authoritative reader.</p>
        </div>
        <div className="evidence-archive-atlas__phase"><span aria-hidden="true" /><strong>{phase}</strong></div>
      </header>
      <div className="evidence-archive-atlas__workspace">{children}</div>
    </div>
  );
}

export default function DocumentsIndex() {
  const navigate = useNavigate();
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
        params.set("investigation_id", investigationFilter.trim());
      }
      params.set("limit", "500");
      const resp = await apiFetch(`/documents?${params.toString()}`);
      if (!resp.ok) {
        throw new Error(`GET /documents: HTTP ${resp.status}`);
      }
      const data = await resp.json();
      setRows(data.documents ?? []);
    } catch {
      setError("The archive could not be charted. Try again.");
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
    <EvidenceArchiveAtlasFrame phase={error ? "Needs attention" : loading ? "Surveying" : rows.length ? "Charted" : "Empty range"}>
        <div className="evidence-archive-atlas__console space-y-6">

          <section className="evidence-archive-atlas__tiers grid grid-cols-5 gap-2" aria-label="Documents by source tier" aria-describedby="evidence-archive-tier-caption">
            {[1, 2, 3, 4, 5].map((t) => (
              <div
                key={t}
                className="border border-rule dark:border-charcoal-1 rounded-md px-3 py-2 text-center"
              >
                <p className="text-base font-serif text-ink dark:text-bright">
                  {counts[t - 1]}
                </p>
                <p className="text-[10px] font-mono text-shadow-1 dark:text-moonlight uppercase">
                  Tier {t}
                </p>
              </div>
            ))}
          </section>

          <p id="evidence-archive-tier-caption" className="evidence-archive-atlas__tier-caption">Tier 1 is peer-reviewed primary evidence; Tier 5 is anonymous material. The archive preserves that source-quality distinction.</p>

          <section className="evidence-archive-atlas__filters border border-rule dark:border-charcoal-1 rounded-md p-4 space-y-3" aria-label="Archive filters">
            <div className="flex items-center gap-2 flex-wrap">
              {TIER_FILTERS.map((t) => (
                <button
                  key={String(t)}
                  type="button"
                  onClick={() => setTierFilter(t)}
                  aria-pressed={tierFilter === t}
                  className={`px-2.5 py-1 rounded-md text-xs font-mono transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aurora focus-visible:ring-offset-2 ${
                    tierFilter === t
                      ? "bg-ink text-white"
                      : "bg-ice-3 dark:bg-charcoal-1 text-ink dark:text-bright hover:bg-ice-4 dark:hover:bg-charcoal-2"
                  }`}
                >
                  {t === "all" ? "all" : `tier ${t}`}
                </button>
              ))}
            </div>
            <label className="block text-xs font-medium text-ink dark:text-bright">Investigation id
              <input
                type="text"
                value={investigationFilter}
                onChange={(e) => setInvestigationFilter(e.target.value)}
                placeholder="filter by investigation_id"
                className="mt-1.5 w-full text-xs font-mono text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2"
              />
            </label>
          </section>

          {error && (
            <p role="alert" className="text-sm text-emperor border border-emperor/30 bg-emperor/10 px-3 py-2 rounded">
              {error}
            </p>
          )}

          {loading && (
            <p role="status" className="text-sm text-shadow-1 dark:text-moonlight italic">Charting the archive…</p>
          )}

          {!loading && rows.length === 0 && !error && (
            <p role="status" className="text-sm text-shadow-1 dark:text-moonlight italic">
              {tierFilter === "all" && !investigationFilter.trim() ? "Nothing is filed yet. Bring sources into range first." : "No documents match this filter."}
            </p>
          )}

          {rows.length > 0 && (
            // S10 acceptance: DocumentsIndex uses LemonTable.
            <LemonTable
              rows={rows}
              rowKey={(r) => r.document_id}
              onRowClick={(r) =>
                navigate(`/wrestle/${encodeURIComponent(r.document_id)}`)
              }
              columns={[
                {
                  key: "title",
                  header: "Title",
                  width: "50%",
                  render: (r) => (
                    <div>
                      <p className="font-serif text-ink dark:text-bright truncate">
                        {r.title ?? r.document_id}
                      </p>
                      <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight truncate">
                        {r.document_id}
                        {r.document_type && <> · {r.document_type}</>}
                        {r.content_class && <> · {r.content_class}</>}
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
                  header: "Investigation",
                  render: (r) =>
                    r.investigation_id ? (
                      <span className="font-mono text-[12px] text-ink-soft dark:text-starlight">
                        {r.investigation_id.slice(0, 12)}
                      </span>
                    ) : (
                      <span className="font-mono text-[11px] text-ink-mute dark:text-moonlight italic">
                        unassigned
                      </span>
                    ),
                },
                {
                  key: "tier",
                  header: "Tier",
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
                      tier {r.source_tier}
                    </LemonTag>
                  ),
                },
              ]}
            />
          )}
        </div>
    </EvidenceArchiveAtlasFrame>
  );
}
