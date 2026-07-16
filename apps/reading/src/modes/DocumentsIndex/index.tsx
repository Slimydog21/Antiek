import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import thinkingArt from "../../brand/werner/poses/session/werner_thinking_session_v1.png";
import livingTvArt from "../../brand/werner/poses/session/werner_living_tv_session_v1.webp";
import LemonTable from "../../components/lemon/LemonTable";
import LemonTag from "../../components/lemon/LemonTag";
import { apiFetch } from "../../lib/api";
import { emitWernerExperience } from "../../werner/reactionBus";

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
    <div className="flex flex-col h-screen">
      <main className="flex-1 overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        <div className="max-w-4xl mx-auto px-8 py-10 space-y-6">
          <header className="space-y-2">
            <div className="flex items-center gap-3">
              <img
                src={thinkingArt}
                alt=""
                aria-hidden="true"
                data-testid="documents-home-werner-brand"
                className="h-12 w-12 shrink-0 object-contain"
              />
              <h1 className="text-2xl font-serif text-ink dark:text-bright">
                Documents
              </h1>
            </div>
            <img
              src={livingTvArt}
              alt=""
              aria-hidden="true"
              data-testid="documents-home-living-tv-art"
              className="h-16 w-full max-w-md rounded-md object-cover object-center"
              loading="lazy"
              decoding="async"
            />
            <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
              Substrate-attached documents (PDFs + web sources +
              transcripts). Tier reflects source quality per master-
              spec §9.5: Tier 1 peer-reviewed primary, Tier 5
              anonymous.
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
                  Tier {t}
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
                  onClick={() => { emitWernerExperience("highlight"); setTierFilter(t); }}
                  className={`px-2.5 py-1 rounded-md text-xs font-mono transition-colors ${
                    tierFilter === t
                      ? "bg-ink text-white"
                      : "bg-ice-3 dark:bg-charcoal-1 text-ink dark:text-bright hover:bg-ice-4 dark:bg-charcoal-1"
                  }`}
                >
                  {t === "all" ? "all" : `tier ${t}`}
                </button>
              ))}
            </div>
            <input
              type="text"
              value={investigationFilter}
              onChange={(e) => setInvestigationFilter(e.target.value)}
              placeholder="filter by investigation_id"
              className="w-full text-xs font-mono text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2"
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
      </main>
    </div>
  );
}
