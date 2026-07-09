/**
 * CollectiveResearchPanel — multi-select deep-research instances → one unit.
 *
 * Operator selects multiple spawn ids (from floating sessions) and can:
 * 1. Merge them via /engagement/collective into a cohesive prompt block
 * 2. Merge them into a draft-combined or parent document via /engagement/merge
 * 3. Residual (cf): Create written analysis draft (collective + draft document)
 */

import { useCallback, useState } from "react";
import {
  fetchCollectiveResearch,
  mergeSpawnOutputs,
  type CollectiveResponse,
  type MergeMode,
  type MergeProductResponse,
} from "../../api/engagement";
import { openWindow } from "../windows/openWindow";

export type CollectiveResearchPanelProps = {
  /** Pre-listed spawn ids available for multi-select */
  availableSpawnIds: string[];
  /** Parent asset for document merge (draft or into_parent). Required for doc merge. */
  parentAssetId?: string | null;
};

export function CollectiveResearchPanel({
  availableSpawnIds,
  parentAssetId = null,
}: CollectiveResearchPanelProps) {
  const [selected, setSelected] = useState<string[]>([]);
  const [unit, setUnit] = useState<CollectiveResponse | null>(null);
  const [docMerge, setDocMerge] = useState<MergeProductResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const toggle = (id: string) => {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  const mergeCollective = useCallback(async () => {
    if (selected.length < 1) return;
    setBusy(true);
    setError(null);
    try {
      const result = await fetchCollectiveResearch({ spawn_ids: selected });
      if (result.view_format !== "html") {
        throw new Error("collective view_format must be html");
      }
      setUnit(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [selected]);

  const mergeDocument = useCallback(
    async (mode: MergeMode) => {
      if (selected.length < 1) return;
      if (!parentAssetId?.trim()) {
        setError("parentAssetId is required for document merge");
        return;
      }
      setBusy(true);
      setError(null);
      try {
        const result = await mergeSpawnOutputs({
          parent_asset_id: parentAssetId,
          spawn_ids: selected,
          mode,
          include_html: true,
        });
        if (result.view_format !== "html") {
          throw new Error("merge view_format must be html");
        }
        setDocMerge(result);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [selected, parentAssetId],
  );

  /** Residual (cf): cohesive unit prompt + draft HTML analysis document. */
  const createWrittenAnalysis = useCallback(async () => {
    if (selected.length < 1) return;
    if (!parentAssetId?.trim()) {
      setError("parentAssetId is required for written analysis draft");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const collective = await fetchCollectiveResearch({ spawn_ids: selected });
      if (collective.view_format !== "html") {
        throw new Error("collective view_format must be html");
      }
      setUnit(collective);
      const draft = await mergeSpawnOutputs({
        parent_asset_id: parentAssetId,
        spawn_ids: selected,
        mode: "draft_combined",
        include_html: true,
      });
      if (draft.view_format !== "html") {
        throw new Error("analysis draft view_format must be html");
      }
      setDocMerge({
        ...draft,
        // surface analysis product label without changing API contract shape
        notes: [
          ...(draft.notes || []),
          "Written analysis draft from collective deep research (residual cf).",
        ],
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [selected, parentAssetId]);

  return (
    <section
      className="collective-research-panel"
      data-view-format="html"
      data-testid="collective-research-panel"
      aria-label="Collective deep research"
    >
      <header>
        <h2>Collective deep research</h2>
        <p className="meta">
          Merge multiple subagent instances into one prompt unit, or into a
          draft-combined / parent HTML document
        </p>
        {parentAssetId ? (
          <p className="meta" data-testid="collective-parent-asset">
            Parent asset: <code>{parentAssetId}</code>
          </p>
        ) : null}
      </header>

      <ul className="spawn-list">
        {availableSpawnIds.map((id) => (
          <li key={id}>
            <label>
              <input
                type="checkbox"
                checked={selected.includes(id)}
                onChange={() => toggle(id)}
                disabled={busy}
              />{" "}
              <code>{id}</code>
            </label>
          </li>
        ))}
      </ul>

      <div className="collective-actions" style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
        <button
          type="button"
          data-testid="collective-merge-prompt"
          onClick={() => void mergeCollective()}
          disabled={busy || selected.length < 1}
        >
          {busy ? "Merging…" : `Merge ${selected.length} spawn(s) as prompt`}
        </button>
        <button
          type="button"
          data-testid="collective-merge-draft"
          onClick={() => void mergeDocument("draft_combined")}
          disabled={busy || selected.length < 1 || !parentAssetId}
          title={
            parentAssetId
              ? "Create draft-combined document; parent unchanged"
              : "Requires parentAssetId"
          }
        >
          Merge to draft document
        </button>
        <button
          type="button"
          data-testid="collective-merge-parent"
          onClick={() => void mergeDocument("into_parent")}
          disabled={busy || selected.length < 1 || !parentAssetId}
          title={
            parentAssetId
              ? "Merge into parent asset in-place"
              : "Requires parentAssetId"
          }
        >
          Merge into parent
        </button>
        <button
          type="button"
          data-testid="collective-written-analysis"
          onClick={() => void createWrittenAnalysis()}
          disabled={busy || selected.length < 1 || !parentAssetId}
          title={
            parentAssetId
              ? "Collective prompt unit + draft-combined HTML analysis"
              : "Requires parentAssetId"
          }
        >
          Create written analysis
        </button>
      </div>

      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}

      {unit ? (
        <div className="collective-result">
          <p>
            collective <code>{unit.collective_id}</code> · spawns=
            {unit.spawn_count} · twins={unit.twin_count} · refs={unit.ref_count}
          </p>
          <pre className="prompt-block" data-testid="collective-prompt-block">
            {unit.prompt_block}
          </pre>
        </div>
      ) : null}

      {docMerge ? (
        <div
          className="document-merge-result"
          data-testid="collective-doc-merge-result"
          data-view-format="html"
        >
          <p>
            mode=<code>{docMerge.mode}</code> · document=
            <code>{docMerge.document_id}</code> · draft_leaves_parent=
            {String(docMerge.draft_leaves_parent)}
          </p>
          {docMerge.notes?.map((n) => (
            <p key={n} className="meta">
              {n}
            </p>
          ))}
          {/* Residual (cg): open draft analysis HTML in floating window. */}
          {docMerge.html && docMerge.view_format === "html" ? (
            <button
              type="button"
              data-testid="collective-open-analysis-window"
              onClick={() => {
                openWindow(
                  "hosted_html_document",
                  {
                    document_id: docMerge.document_id,
                    title: `Written analysis (${docMerge.mode})`,
                    html: docMerge.html,
                    view_format: "html",
                    source: "collective_written_analysis",
                  },
                  {
                    id: `win:analysis:${docMerge.document_id}`,
                    title: "Written analysis",
                    mode: "floating",
                  },
                );
              }}
            >
              Open analysis in window
            </button>
          ) : null}
          {docMerge.html ? (
            <div
              className="merge-html"
              data-testid="collective-doc-merge-html"
              dangerouslySetInnerHTML={{ __html: docMerge.html }}
            />
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

export default CollectiveResearchPanel;
