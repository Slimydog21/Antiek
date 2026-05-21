import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { apiFetch } from "../../lib/api";
import HeaderBar from "../shared/HeaderBar";

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
      <HeaderBar />
      <main className="flex-1 overflow-y-auto bg-white">
        <div className="max-w-4xl mx-auto px-8 py-10 space-y-6">
          <header className="space-y-2">
            <h1 className="text-2xl font-serif text-stone-900">
              Notebooks
            </h1>
            <p className="text-sm text-stone-600 leading-relaxed">
              Per master-spec §4.2: notebooks are the literate-analysis
              surface — markdown prose interleaved with claim cards,
              region embeds, question cards, and substrate refs.
              Promote-to-public is gated on the §13.9 quality gate.
            </p>
          </header>

          <section className="border border-stone-200 rounded-md p-4 space-y-3">
            <h2 className="text-sm font-serif text-stone-900">
              New notebook
            </h2>
            <input
              type="text"
              value={draftTitle}
              onChange={(e) => setDraftTitle(e.target.value)}
              placeholder="Title"
              className="w-full text-sm font-serif text-stone-900 border border-stone-200 rounded p-2"
            />
            <input
              type="text"
              value={draftInvId}
              onChange={(e) => setDraftInvId(e.target.value)}
              placeholder="Investigation ID (optional)"
              className="w-full text-xs font-mono text-stone-900 border border-stone-200 rounded p-2"
            />
            <button
              type="button"
              onClick={() => void createNotebook()}
              disabled={submitting || !draftTitle.trim()}
              className="px-3 py-1.5 rounded-md bg-stone-900 text-white text-xs font-medium hover:bg-stone-800 transition-colors disabled:opacity-50"
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
                  onClick={() => setFilter(f)}
                  className={`px-2.5 py-1 rounded-md text-xs font-mono transition-colors ${
                    filter === f
                      ? "bg-stone-900 text-white"
                      : "bg-stone-100 text-stone-700 hover:bg-stone-200"
                  }`}
                >
                  {f.replace(/_/g, " ")}
                </button>
              ))}
            </div>
            <p className="text-[11px] font-mono text-stone-500">
              {filtered.length} of {rows.length}
            </p>
          </section>

          {error && (
            <p className="text-sm text-red-700 border border-red-200 bg-red-50 px-3 py-2 rounded">
              {error}
            </p>
          )}

          {loading && (
            <p className="text-sm text-stone-500 italic">Loading…</p>
          )}

          {!loading && filtered.length === 0 && !error && (
            <p className="text-sm text-stone-500 italic">
              No notebooks match this filter.
            </p>
          )}

          {filtered.length > 0 && (
            <section className="border border-stone-200 rounded-md divide-y divide-stone-100">
              {filtered.map((r) => (
                <Link
                  key={r.notebook_id}
                  to={`/notebook/${encodeURIComponent(r.notebook_id)}`}
                  className="block px-4 py-3 hover:bg-stone-50 transition-colors"
                >
                  <div className="flex items-baseline justify-between gap-3">
                    <p className="text-sm font-serif text-stone-900 truncate flex-1">
                      {r.title}
                    </p>
                    <span
                      className={`text-[10px] uppercase tracking-wider font-mono px-2 py-0.5 rounded shrink-0 ${
                        r.content_class === "user_public_contribution"
                          ? "bg-emerald-100 text-emerald-700"
                          : "bg-stone-100 text-stone-700"
                      }`}
                    >
                      {r.content_class.replace(/_/g, " ")}
                    </span>
                  </div>
                  <p className="text-[11px] font-mono text-stone-500 truncate">
                    {r.notebook_id} · updated {r.updated_at}
                    {r.investigation_id && (
                      <> · inv: {r.investigation_id.slice(0, 8)}</>
                    )}
                  </p>
                </Link>
              ))}
            </section>
          )}
        </div>
      </main>
    </div>
  );
}
