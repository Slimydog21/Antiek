import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import thinkingArt from "../../brand/werner/poses/session/werner_thinking_session_v1.png";
import livingTvArt from "../../brand/werner/poses/session/werner_living_tv_session_v1.webp";
import LemonTable from "../../components/lemon/LemonTable";
import LemonTag from "../../components/lemon/LemonTag";
import { apiFetch } from "../../lib/api";
import { emitWernerExperience } from "../../werner/reactionBus";

/**
 * Notebooks listing UI (master-spec §4.2 Wedge 2 linchpin).
 *
 * Lists every notebook (user_owned + user_public_contribution),
 * filter by content_class, click to open the existing
 * /notebook/:id detail view. Includes a 'New notebook' form that
 * POSTs to /notebooks and navigates into the new notebook.
 */

interface NotebookSummary {
  notebook_id: string;
  title: string;
  investigation_id: string | null;
  document_id: string | null;
  content_class: string;
  created_at: string;
  updated_at: string;
}

interface ListResponse {
  count: number;
  notebooks: NotebookSummary[];
}

const FILTERS = ["all", "user_owned", "user_public_contribution"] as const;

export default function NotebooksIndex() {
  const navigate = useNavigate();
  const [rows, setRows] = useState<NotebookSummary[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("all");

  // New-notebook draft.
  const [draftTitle, setDraftTitle] = useState<string>("");
  const [draftInvId, setDraftInvId] = useState<string>("");
  const [submitting, setSubmitting] = useState<boolean>(false);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await apiFetch("/notebooks");
      if (!resp.ok) {
        throw new Error(`GET /notebooks: HTTP ${resp.status}`);
      }
      const data: ListResponse = await resp.json();
      setRows(data.notebooks ?? []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const filtered = useMemo(
    () =>
      filter === "all"
        ? rows
        : rows.filter((r) => r.content_class === filter),
    [rows, filter],
  );

  const createNotebook = async () => {
    if (submitting || !draftTitle.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const resp = await apiFetch("/notebooks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: draftTitle.trim(),
          investigation_id: draftInvId.trim() || null,
        }),
      });
      if (!resp.ok) {
        throw new Error(`POST /notebooks: HTTP ${resp.status}`);
      }
      const created: NotebookSummary = await resp.json();
      setDraftTitle("");
      setDraftInvId("");
      if (created.notebook_id) {
        navigate(`/notebook/${encodeURIComponent(created.notebook_id)}`);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col h-screen">
      <main className="flex-1 overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        <div className="max-w-4xl mx-auto px-8 py-10 space-y-6">
          <header className="space-y-2">
            <div className="flex items-center gap-3">
              {/* Session thinking mark — densify Notebooks door with living-TV
                  brand chrome so the literate-analysis surface consumes session
                  Imagine assets, not inventory-only. */}
              <img
                src={thinkingArt}
                alt=""
                aria-hidden="true"
                data-testid="notebooks-home-werner-brand"
                className="h-12 w-12 shrink-0 object-contain"
              />
              <h1 className="text-2xl font-serif text-ink dark:text-bright">
                Notebooks
              </h1>
            </div>
            <img
              src={livingTvArt}
              alt=""
              aria-hidden="true"
              data-testid="notebooks-home-living-tv-art"
              className="h-16 w-full max-w-md rounded-md object-cover object-center"
              loading="lazy"
              decoding="async"
            />
            <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
              Per master-spec §4.2: notebooks are the literate-analysis
              surface — markdown prose interleaved with claim cards,
              region embeds, question cards, and substrate refs.
              Promote-to-public is gated on the §13.9 quality gate.
            </p>
          </header>

          <section className="border border-rule dark:border-charcoal-1 rounded-md p-4 space-y-3">
            <h2 className="text-sm font-serif text-ink dark:text-bright">
              New notebook
            </h2>
            <input
              type="text"
              value={draftTitle}
              onChange={(e) => setDraftTitle(e.target.value)}
              placeholder="Title"
              className="w-full text-sm font-serif text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2"
            />
            <input
              type="text"
              value={draftInvId}
              onChange={(e) => setDraftInvId(e.target.value)}
              placeholder="Investigation ID (optional)"
              className="w-full text-xs font-mono text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2"
            />
            <button
              type="button"
              onClick={() => { emitWernerExperience("piece_started"); void createNotebook(); }}
              disabled={submitting || !draftTitle.trim()}
              className="px-3 py-1.5 rounded-md bg-ink text-white text-xs font-medium hover:bg-shadow-2 transition-colors disabled:opacity-50"
            >
              {submitting ? "Creating…" : "Create notebook"}
            </button>
          </section>

          <section className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              {FILTERS.map((f) => (
                <button
                  key={f}
                  type="button"
                  onClick={() => { emitWernerExperience("highlight"); setFilter(f); }}
                  className={`px-2.5 py-1 rounded-md text-xs font-mono transition-colors ${
                    filter === f
                      ? "bg-ink text-white"
                      : "bg-ice-3 dark:bg-charcoal-1 text-ink dark:text-bright hover:bg-ice-4 dark:bg-charcoal-1"
                  }`}
                >
                  {f.replace(/_/g, " ")}
                </button>
              ))}
            </div>
            <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight">
              {filtered.length} of {rows.length}
            </p>
          </section>

          {error && (
            <p className="text-sm text-emperor border border-red-200 bg-red-50 px-3 py-2 rounded">
              {error}
            </p>
          )}

          {loading && (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">Loading…</p>
          )}

          {!loading && filtered.length === 0 && !error && (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">
              No notebooks match this filter.
            </p>
          )}

          {filtered.length > 0 && (
            // S10 acceptance: NotebooksIndex uses LemonTable.
            <LemonTable
              rows={filtered}
              rowKey={(r) => r.notebook_id}
              onRowClick={(r) =>
                navigate(`/notebook/${encodeURIComponent(r.notebook_id)}`)
              }
              columns={[
                {
                  key: "title",
                  header: "Title",
                  width: "55%",
                  render: (r) => (
                    <div>
                      <p className="font-serif text-ink dark:text-bright truncate">
                        {r.title}
                      </p>
                      <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight truncate">
                        {r.notebook_id}
                        {r.investigation_id && (
                          <> · inv: {r.investigation_id.slice(0, 8)}</>
                        )}
                      </p>
                    </div>
                  ),
                },
                {
                  key: "updated",
                  header: "Updated",
                  render: (r) => (
                    <span className="font-mono text-[12px] text-ink-soft dark:text-starlight">
                      {r.updated_at}
                    </span>
                  ),
                },
                {
                  key: "class",
                  header: "Class",
                  align: "right",
                  render: (r) => (
                    <LemonTag
                      colour={
                        r.content_class === "user_public_contribution"
                          ? "aurora"
                          : "muted"
                      }
                    >
                      {r.content_class.replace(/_/g, " ")}
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
