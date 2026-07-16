import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import conservatoryArt from "../../brand/werner/notebooks/recursive_notebook_conservatory_v1.webp";
import LemonTable from "../../components/lemon/LemonTable";
import LemonTag from "../../components/lemon/LemonTag";
import { apiFetch } from "../../lib/api";
import "./recursive-notebook-conservatory.css";

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
type NotebookFilter = (typeof FILTERS)[number];

export type NotebookConservatoryPhase =
  | "Surveying"
  | "Ready"
  | "Empty beds"
  | "Planting"
  | "Needs attention";

export function RecursiveNotebookConservatoryFrame({
  phase,
  visualFixture = false,
  children,
}: {
  phase: NotebookConservatoryPhase;
  visualFixture?: boolean;
  children: ReactNode;
}) {
  return (
    <div className={`recursive-notebook-conservatory ${visualFixture ? "recursive-notebook-conservatory--fixture" : ""}`}>
      <img
        src={conservatoryArt}
        alt=""
        aria-hidden="true"
        draggable={false}
        decoding="async"
        data-testid="recursive-notebook-conservatory-art"
      />
      <div className="recursive-notebook-conservatory__veil" aria-hidden="true" />
      <header className="recursive-notebook-conservatory__masthead">
        <div>
          <p className="recursive-notebook-conservatory__eyebrow">Antiek · notebook conservatory</p>
          <h1>Cultivate the notes that think with you</h1>
          <p>Keep claims, questions, source traces, and working prose together—then reopen any notebook where the thinking left off.</p>
        </div>
        <div className="recursive-notebook-conservatory__phase">
          <span aria-hidden="true" />
          <strong>{phase}</strong>
        </div>
      </header>
      <div className="recursive-notebook-conservatory__workspace">{children}</div>
    </div>
  );
}

export default function NotebooksIndex() {
  const navigate = useNavigate();
  const [rows, setRows] = useState<NotebookSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<NotebookFilter>("all");
  const [draftTitle, setDraftTitle] = useState("");
  const [draftInvId, setDraftInvId] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await apiFetch("/notebooks");
      if (!resp.ok) throw new Error("notebook-list-request-failed");
      const data: ListResponse = await resp.json();
      setRows(data.notebooks ?? []);
    } catch {
      setError("The notebook conservatory could not be surveyed. Try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const filtered = useMemo(
    () => filter === "all" ? rows : rows.filter((row) => row.content_class === filter),
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
      if (!resp.ok) throw new Error("notebook-create-request-failed");
      const created: NotebookSummary = await resp.json();
      setDraftTitle("");
      setDraftInvId("");
      if (created.notebook_id) {
        navigate(`/notebook/${encodeURIComponent(created.notebook_id)}`);
      }
    } catch {
      setError("The notebook could not be planted. Try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const phase: NotebookConservatoryPhase = error
    ? "Needs attention"
    : submitting
      ? "Planting"
      : loading
        ? "Surveying"
        : rows.length
          ? "Ready"
          : "Empty beds";

  return (
    <RecursiveNotebookConservatoryFrame phase={phase}>
      <div className="recursive-notebook-conservatory__console space-y-6">
        <section className="recursive-notebook-conservatory__inventory" aria-labelledby="notebook-inventory-heading">
          <div>
            <p className="recursive-notebook-conservatory__section-label">Living inventory</p>
            <h2 id="notebook-inventory-heading">Your working books</h2>
            <p>Private working notebooks and public contributions remain visibly distinct.</p>
          </div>
          <div className="recursive-notebook-conservatory__counts" aria-label="Notebook inventory counts">
            <span><strong>{rows.length}</strong> total</span>
            <span><strong>{rows.filter((row) => row.content_class === "user_owned").length}</strong> private</span>
            <span><strong>{rows.filter((row) => row.content_class === "user_public_contribution").length}</strong> public</span>
          </div>
        </section>

        <form
          className="recursive-notebook-conservatory__new space-y-3"
          aria-labelledby="new-notebook-heading"
          onSubmit={(event) => {
            event.preventDefault();
            void createNotebook();
          }}
        >
          <div>
            <p className="recursive-notebook-conservatory__section-label">Plant a working book</p>
            <h2 id="new-notebook-heading">New notebook</h2>
          </div>
          <label>
            <span>Notebook title</span>
            <input
              type="text"
              value={draftTitle}
              onChange={(event) => setDraftTitle(event.target.value)}
              placeholder="e.g. Models as research collaborators"
              autoComplete="off"
            />
          </label>
          <label>
            <span>Investigation ID <em>optional</em></span>
            <input
              type="text"
              value={draftInvId}
              onChange={(event) => setDraftInvId(event.target.value)}
              placeholder="Bind this notebook to an investigation"
              autoComplete="off"
            />
          </label>
          <button type="submit" disabled={submitting || !draftTitle.trim()}>
            {submitting ? "Planting notebook…" : "Create notebook"}
          </button>
        </form>

        <section className="recursive-notebook-conservatory__catalogue" aria-labelledby="notebook-catalogue-heading">
          <div className="recursive-notebook-conservatory__catalogue-head">
            <div>
              <p className="recursive-notebook-conservatory__section-label">Conservatory beds</p>
              <h2 id="notebook-catalogue-heading">Notebook catalogue</h2>
            </div>
            <p aria-live="polite">{filtered.length} of {rows.length}</p>
          </div>
          <div className="recursive-notebook-conservatory__filters" aria-label="Filter notebooks by content class">
            {FILTERS.map((candidate) => (
              <button
                key={candidate}
                type="button"
                onClick={() => setFilter(candidate)}
                aria-pressed={filter === candidate}
              >
                {candidate === "all" ? "all notebooks" : candidate.replace(/_/g, " ")}
              </button>
            ))}
          </div>

          {error && <p role="alert" className="recursive-notebook-conservatory__error">{error}</p>}
          {loading && <p role="status" className="recursive-notebook-conservatory__status">Surveying the conservatory…</p>}
          {!loading && filtered.length === 0 && !error && (
            <p role="status" className="recursive-notebook-conservatory__status">
              {filter === "all" ? "No working books yet. Plant the first notebook above." : "No notebooks grow in this bed yet."}
            </p>
          )}

          {filtered.length > 0 && (
            <LemonTable
              rows={filtered}
              rowKey={(row) => row.notebook_id}
              onRowClick={(row) => navigate(`/notebook/${encodeURIComponent(row.notebook_id)}`)}
              columns={[
                {
                  key: "title",
                  header: "Title",
                  width: "55%",
                  render: (row) => (
                    <div>
                      <p className="font-serif text-ink dark:text-bright truncate">{row.title}</p>
                      <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight truncate">
                        {row.notebook_id}{row.investigation_id && <> · inv: {row.investigation_id.slice(0, 8)}</>}
                      </p>
                    </div>
                  ),
                },
                {
                  key: "updated",
                  header: "Updated",
                  render: (row) => <span className="font-mono text-[12px] text-ink-soft dark:text-starlight">{row.updated_at}</span>,
                },
                {
                  key: "class",
                  header: "Class",
                  align: "right",
                  render: (row) => (
                    <LemonTag colour={row.content_class === "user_public_contribution" ? "aurora" : "muted"}>
                      {row.content_class.replace(/_/g, " ")}
                    </LemonTag>
                  ),
                },
              ]}
            />
          )}
        </section>
      </div>
    </RecursiveNotebookConservatoryFrame>
  );
}
