import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import LemonTable from "../../components/lemon/LemonTable";
import LemonTag from "../../components/lemon/LemonTag";
import { apiFetch } from "../../lib/api";

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

const FILTERS = ["all", "user_owned", "user_public_contribution"] as const;
type NotebookFilter = (typeof FILTERS)[number];

const FILTER_LABELS: Record<NotebookFilter, string> = {
  all: "All",
  user_owned: "Private",
  user_public_contribution: "Public contribution",
};

function notebookVisibilityLabel(contentClass: string): string {
  if (contentClass === "user_public_contribution") return "Public contribution";
  if (contentClass === "user_owned") return "Private";
  return "Unclassified";
}

function notebookLinkSummary(row: NotebookSummary): string {
  const links = [
    row.investigation_id ? "linked research" : null,
    row.document_id ? "linked document" : null,
  ].filter(Boolean);
  return links.length > 0 ? links.join(" · ") : "No linked source";
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function nonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function nullableString(value: unknown): string | null {
  return value == null ? null : nonEmptyString(value);
}

function notebookContentClass(value: unknown): NotebookSummary["content_class"] {
  return value === "user_public_contribution"
    ? "user_public_contribution"
    : "user_owned";
}

function safeNotebookSummary(value: unknown): NotebookSummary | null {
  const row = record(value);
  const notebookId = nonEmptyString(row?.notebook_id);
  if (!row || !notebookId) return null;
  return {
    notebook_id: notebookId,
    title: nonEmptyString(row.title) ?? "Untitled notebook",
    investigation_id: nullableString(row.investigation_id),
    document_id: nullableString(row.document_id),
    content_class: notebookContentClass(row.content_class),
    created_at: nonEmptyString(row.created_at) ?? "",
    updated_at: nonEmptyString(row.updated_at) ?? "",
  };
}

function safeNotebookList(value: unknown): NotebookSummary[] {
  const body = record(value);
  const rows = Array.isArray(body?.notebooks) ? body.notebooks : [];
  const seen = new Set<string>();
  return rows.flatMap((item) => {
    const row = safeNotebookSummary(item);
    if (!row || seen.has(row.notebook_id)) return [];
    seen.add(row.notebook_id);
    return [row];
  });
}

export default function NotebooksIndex() {
  const navigate = useNavigate();
  const [rows, setRows] = useState<NotebookSummary[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<NotebookFilter>("all");

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
        throw new Error(`Couldn’t load notebooks (HTTP ${resp.status}).`);
      }
      setRows(safeNotebookList(await resp.json()));
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
        throw new Error(`Couldn’t create the notebook (HTTP ${resp.status}).`);
      }
      const created = safeNotebookSummary(await resp.json());
      setDraftTitle("");
      setDraftInvId("");
      if (created?.notebook_id) {
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
            <h1 className="text-2xl font-serif text-ink dark:text-bright">
              Notebooks
            </h1>
            <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
              A notebook is the place where reading turns into analysis:
              prose, source passages, notes, open questions, links across
              documents, images, math, and reusable sections live together.
              Public sharing stays gated until the quality review clears.
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
              aria-label="Link to research"
              placeholder="Link to research (optional)"
              className="w-full text-sm font-serif text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2"
            />
            <button
              type="button"
              onClick={() => void createNotebook()}
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
                  onClick={() => setFilter(f)}
                  className={`px-2.5 py-1 rounded-md text-xs font-mono transition-colors ${
                    filter === f
                      ? "bg-ink text-white"
                      : "bg-ice-3 dark:bg-charcoal-1 text-ink dark:text-bright hover:bg-ice-4 dark:bg-charcoal-1"
                  }`}
                >
                  {FILTER_LABELS[f]}
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
                        {r.title || "Untitled notebook"}
                      </p>
                      <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight truncate">
                        {notebookLinkSummary(r)}
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
                  header: "Visibility",
                  align: "right",
                  render: (r) => (
                    <LemonTag
                      colour={
                        r.content_class === "user_public_contribution"
                          ? "aurora"
                          : "muted"
                      }
                    >
                      {notebookVisibilityLabel(r.content_class)}
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
