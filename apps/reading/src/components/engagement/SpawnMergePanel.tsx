import { useCallback, useState } from "react";
import {
  mergeSpawnOutputs,
  type MergeMode,
  type MergeProductResponse,
} from "../../api/engagement";
import { openWindow } from "../windows/openWindow";
import { SandboxedHtmlFrame } from "../windows/HostedHtmlDocumentHost";

export type OpenMergedResearchWindowOpts = {
  titleStem?: string;
  source?: string;
  idPrefix?: string;
  windowMode?: "floating" | "full";
};

export function openMergedResearchWindow(
  result: Pick<MergeProductResponse, "document_id" | "mode" | "html" | "view_format">,
  opts: OpenMergedResearchWindowOpts = {},
): string | null {
  if (result.view_format !== "html" || !result.html?.trim()) {
    return null;
  }
  const stem = (opts.titleStem || "Merged research").trim() || "Merged research";
  const source = (opts.source || "spawn_merge_panel").trim() || "spawn_merge_panel";
  const idPrefix = (opts.idPrefix || "win:merge").trim() || "win:merge";
  const windowMode = opts.windowMode === "full" ? "full" : "floating";
  const idSuffix = windowMode === "full" ? ":full" : "";
  return openWindow(
    "hosted_html_document",
    {
      document_id: result.document_id,
      title: `${stem} (${result.mode})`,
      html: result.html,
      view_format: "html",
      source,
    },
    {
      id: `${idPrefix}:${result.document_id}${idSuffix}`,
      title: stem,
      mode: windowMode,
    },
  );
}

export type SpawnMergePanelProps = {
  spawnId: string;
  parentAssetId: string;
  onMerged?: (result: MergeProductResponse) => void;
  autoOpenDraft?: boolean;
};

export function SpawnMergePanel({
  spawnId,
  parentAssetId,
  onMerged,
  autoOpenDraft = true,
}: SpawnMergePanelProps) {
  const [result, setResult] = useState<MergeProductResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [autoOpenedWindowId, setAutoOpenedWindowId] = useState<string | null>(
    null,
  );

  const merge = useCallback(
    async (mode: MergeMode) => {
      const sid = spawnId.trim();
      const parent = parentAssetId.trim();
      if (!sid || !parent) {
        setError("spawnId and parentAssetId are required");
        return;
      }
      setBusy(true);
      setError(null);
      setAutoOpenedWindowId(null);
      try {
        const out = await mergeSpawnOutputs({
          parent_asset_id: parent,
          spawn_ids: [sid],
          mode,
          include_html: true,
        });
        if (out.view_format !== "html") {
          throw new Error("merge view_format must be html");
        }
        let notes = [...(out.notes || [])];
        const final = { ...out, notes };
        setResult(final);
        onMerged?.(final);

        // The parent is already visible, while a new draft needs its own surface.
        if (
          autoOpenDraft &&
          mode === "draft_combined" &&
          final.view_format === "html" &&
          final.html?.trim()
        ) {
          const winId = openMergedResearchWindow(final);
          if (winId) {
            setAutoOpenedWindowId(winId);
            notes = [
              ...notes,
              "Draft combined auto-opened in hosted HTML window.",
            ];
            setResult({ ...final, notes });
          }
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [spawnId, parentAssetId, onMerged, autoOpenDraft],
  );

  return (
    <section
      className="spawn-merge-panel space-y-2"
      data-testid="spawn-merge-panel"
      data-view-format="html"
      data-auto-open-draft={autoOpenDraft ? "true" : "false"}
      aria-label="Merge this deep research"
    >
      <header>
        <h2 className="text-sm font-medium text-ink dark:text-parchment">
          Merge into reading asset
        </h2>
        <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight">
          Spawn <code>{spawnId}</code> → parent <code>{parentAssetId}</code>
          {autoOpenDraft
            ? " · draft auto-opens HTML window"
            : " · draft open is manual"}
        </p>
      </header>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          data-testid="spawn-merge-draft"
          disabled={busy}
          onClick={() => void merge("draft_combined")}
          className="rounded border border-ink/30 px-2 py-1 text-[12px] font-mono hover:bg-ink/5 disabled:opacity-50 dark:border-bright/30"
        >
          {busy ? "Merging…" : "Create draft combined"}
        </button>
        <button
          type="button"
          data-testid="spawn-merge-parent"
          disabled={busy}
          onClick={() => void merge("into_parent")}
          className="rounded border border-ink/30 px-2 py-1 text-[12px] font-mono hover:bg-ink/5 disabled:opacity-50 dark:border-bright/30"
        >
          {busy ? "Merging…" : "Merge into parent"}
        </button>
      </div>

      {error ? (
        <p className="text-[11px] font-mono text-emperor" role="alert">
          {error}
        </p>
      ) : null}

      {result ? (
        <div
          className="space-y-2 rounded border border-ink/10 p-2 dark:border-bright/10"
          data-testid="spawn-merge-result"
          data-view-format="html"
          data-mode={result.mode}
        >
          <p className="text-[12px] font-mono text-ink dark:text-bright">
            mode=<code>{result.mode}</code> · document=
            <code>{result.document_id}</code> · draft_leaves_parent=
            {String(result.draft_leaves_parent)}
          </p>
          {autoOpenedWindowId ? (
            <p
              className="text-[11px] font-mono text-aurora"
              data-testid="spawn-merge-auto-open-window"
              role="status"
            >
              Auto-opened window {autoOpenedWindowId}
            </p>
          ) : null}
          {result.notes?.map((n) => (
            <p
              key={n}
              className="text-[11px] text-ink-mute dark:text-moonlight"
            >
              {n}
            </p>
          ))}
          {result.html && result.view_format === "html" ? (
            <>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  data-testid="spawn-merge-open-window"
                  onClick={() => {
                    openMergedResearchWindow(result);
                  }}
                  className="rounded border border-ink/30 px-2 py-1 text-[11px] font-mono hover:bg-ink/5 dark:border-bright/30"
                >
                  Open merged HTML in window
                </button>
                <button
                  type="button"
                  data-testid="spawn-merge-open-full"
                  onClick={() => {
                    openMergedResearchWindow(result, { windowMode: "full" });
                  }}
                  className="rounded border border-ink/30 px-2 py-1 text-[11px] font-mono hover:bg-ink/5 dark:border-bright/30"
                >
                  Open merged HTML full
                </button>
              </div>
              <div className="flex h-40" data-testid="spawn-merge-html">
                <SandboxedHtmlFrame html={result.html} title="Merged research preview" />
              </div>
            </>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

export default SpawnMergePanel;
