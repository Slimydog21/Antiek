/**
 * SpawnMergePanel — single deep-research spawn → draft or parent merge.
 *
 * Residual (ci): highlight → floating DR → merge into the reading asset
 * without multi-select collective friction. Composes shipped
 * mergeSpawnOutputs (draft_combined | into_parent). HTML-first only.
 * Residual (cp): seed twin notes on the merged document_id after success.
 * Residual (eh): onMerged notifies parent so research context remounts
 * after draft/parent merge + twin seed.
 * Residual (el): auto-open draft_combined HTML in hosted_html_document so the
 * draft joins the reading/research flywheel without a second click (parent
 * merge stays manual — parent may already be open).
 * Residual (ev): manual re-open as full working-region window after merge.
 * Residual (fn): Open Write handoff link for merged HTML document_id (fl/fm).
 * Residual (qd): dual handoff html_draft + twin_seed (parity marketplace/MO).
 * Residual (ho): spawn-merge-metrics machine attrs for draft/parent merge audit.
 * Residual (ih): Settings deep-link for driver + budget.
 * Residual (kn): surface recommended_research_tier + research_tiers from merge.
 * Residual (lj): DecisionTreeDriverBadge with merge recommended tier (or prop).
 * Residual (qh): DecisionTreeDriverBadge promptText for cost projection foresight.
 * Residual (nn): dual-gate L1–L4 checklist deep-link (prep only).
 */

import { useCallback, useMemo, useState } from "react";
import {
  mergeSpawnOutputs,
  seedTwinNotes,
  type MergeMode,
  type MergeProductResponse,
} from "../../api/engagement";
import { openWindow } from "../windows/openWindow";
import {
  buildMergedDocWriteHref,
  plainTextFromHtml,
} from "../../workspace/twinWriteSeed";
import { DecisionTreeDriverBadge } from "./DecisionTreeDriverBadge";

export type OpenMergedResearchWindowOpts = {
  /** Window + payload title stem (default: Merged research). */
  titleStem?: string;
  /** Payload source tag for provenance. */
  source?: string;
  /** Window id prefix (default: win:merge). */
  idPrefix?: string;
  /**
   * Residual (ev): floating (default) or full working-region window.
   * Auto-open stays floating; operators can re-open full after merge.
   */
  windowMode?: "floating" | "full";
};

/** Open merged HTML as hosted document (HTML-first; never PDF). Shared by spawn + collective. */
export function openMergedResearchWindow(
  result: Pick<MergeProductResponse, "document_id" | "mode" | "html" | "view_format">,
  opts: OpenMergedResearchWindowOpts = {},
): string | null {
  if (result.view_format !== "html" || !result.html?.trim()) {
    return null;
  }
  const stem = (opts.titleStem || "Merged research").trim() || "Merged research";
  // Residual (aah): default source must be `spawn_merge` so auto-open / manual
  // hosted HTML floats preserve Open Write + Antiek-bench write-seed provenance
  // (KNOWN_HOST_WRITE_SOURCES). Prior `spawn_merge_panel` collapsed to
  // hosted_html_document on HostedHtml Open Write.
  const source = (opts.source || "spawn_merge").trim() || "spawn_merge";
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
  /** Residual (eh): after successful HTML merge (+ twin seed attempt). */
  onMerged?: (result: MergeProductResponse) => void;
  /**
   * Residual (el): when true (default), open hosted HTML window after a
   * successful draft_combined merge. into_parent never auto-opens.
   */
  autoOpenDraft?: boolean;
  /**
   * Residual (lj): optional pre-merge research tier for driver badge;
   * after merge, recommended_research_tier from product wins.
   */
  researchTier?: "fast" | "deep" | "wrestle" | string | null;
};

export function SpawnMergePanel({
  spawnId,
  parentAssetId,
  onMerged,
  autoOpenDraft = true,
  researchTier = null,
}: SpawnMergePanelProps) {
  const [result, setResult] = useState<MergeProductResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [autoOpenedWindowId, setAutoOpenedWindowId] = useState<string | null>(
    null,
  );

  // Residual (lj): post-merge recommended tier wins over prop / default deep.
  const badgeResearchTier = useMemo(() => {
    const fromResult = (result?.recommended_research_tier || "")
      .trim()
      .toLowerCase();
    if (fromResult) return fromResult;
    const fromProp = (researchTier || "").trim().toLowerCase();
    return fromProp || "deep";
  }, [result?.recommended_research_tier, researchTier]);

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
        // Residual (cp): recursive note-taker seed on merged document.
        let notes = [...(out.notes || [])];
        try {
          const twins = await seedTwinNotes({
            asset_id: out.document_id,
            title: `Merged research (${mode}) from ${sid}`,
            body_text: `Parent ${parent} · spawn ${sid} · mode ${mode}`,
            source_spawn_id: sid,
            include_html: false,
            force_offline: true,
          });
          notes = [
            ...notes,
            twins.seeded
              ? "Twin notes seeded on merged document (recursive note-taker)."
              : `Twin seed: ${twins.seed_skipped || "skipped"}`,
          ];
        } catch {
          notes = [...notes, "Twin seed skipped (API unavailable)."];
        }
        const final = { ...out, notes };
        setResult(final);
        onMerged?.(final);

        // Residual (el): draft_combined → auto-open hosted HTML flywheel.
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
              "Draft combined auto-opened in hosted HTML window (el).",
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
        {/* Residual (ih/nn): Settings + dual-gate checklist (merge path prep). */}
        <p className="text-[11px] font-mono space-x-3">
          <a
            href="/settings#decision-tree-panel"
            data-testid="spawn-merge-settings-link"
            className="underline opacity-80 hover:opacity-100"
            title="Open Settings decision-tree: driver, budget bar, sample cost projection"
          >
            Settings · driver & budget
          </a>
          <a
            href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l6-collective"
            data-testid="spawn-merge-dual-gate-checklist-link"
            className="underline opacity-80 hover:opacity-100"
            title="Dual-gate L1–L4 checklist (prep only; offline default)"
          >
            Dual-gate L1–L4 checklist
          </a>
        </p>
        {/* Residual (lj): model driver + budget + depth (parity collective lg). */}
        <div
          className="mt-1"
          data-testid="spawn-merge-driver-badge-mount"
          data-view-format="html"
          data-research-tier={badgeResearchTier}
        >
          <DecisionTreeDriverBadge
            researchTier={badgeResearchTier}
            promptText={
              (result?.html
                ? plainTextFromHtml(result.html)
                : "") ||
              `spawn merge · ${spawnId.trim()} → ${parentAssetId.trim()}`
            }
          />
        </div>
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
          data-recommended-research-tier={
            (result.recommended_research_tier || "").trim().toLowerCase() || ""
          }
        >
          {/* Residual (ho/kn): machine-readable merge outcome + depth identity. */}
          <div
            data-testid="spawn-merge-metrics"
            data-mode={result.mode}
            data-document-id={result.document_id ?? ""}
            data-draft-leaves-parent={String(
              Boolean(result.draft_leaves_parent),
            )}
            data-spawn-id={spawnId}
            data-parent-asset-id={parentAssetId}
            data-view-format="html"
            data-auto-open-draft={autoOpenDraft ? "true" : "false"}
            data-recommended-research-tier={
              (result.recommended_research_tier || "").trim().toLowerCase() ||
              ""
            }
            data-research-tiers={(result.research_tiers || []).join(",")}
            role="status"
          >
            Spawn merge · mode={result.mode} · document={result.document_id}
            {result.recommended_research_tier
              ? ` · recommended_tier=${result.recommended_research_tier}`
              : ""}
            {(result.research_tiers || []).length
              ? ` · tiers=${(result.research_tiers || []).join(",")}`
              : ""}
          </div>
          <p className="text-[12px] font-mono text-ink dark:text-bright">
            mode=<code>{result.mode}</code> · document=
            <code>{result.document_id}</code> · draft_leaves_parent=
            {String(result.draft_leaves_parent)}
          </p>
          {/* Residual (kn): depth posture chrome (parity collective ke). */}
          {result.recommended_research_tier ? (
            <p
              className="text-[11px] font-mono opacity-90"
              data-testid="spawn-merge-research-tier"
              data-recommended-research-tier={String(
                result.recommended_research_tier,
              )
                .trim()
                .toLowerCase()}
              role="status"
            >
              Recommended research tier:{" "}
              <strong>{result.recommended_research_tier}</strong>
              {(result.research_tiers || []).length
                ? ` · members=${(result.research_tiers || []).join(",")}`
                : ""}
              {String(result.recommended_research_tier).toLowerCase() ===
              "wrestle"
                ? " · multi-minute long-horizon depth"
                : String(result.recommended_research_tier).toLowerCase() ===
                    "fast"
                  ? " · flash / distill depth"
                  : " · deep / synthesize depth"}
            </p>
          ) : null}
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
                {/* Residual (fn): handoff merged HTML draft into Write mode. */}
                <a
                  href={buildMergedDocWriteHref({
                    documentId: result.document_id,
                    title: `Merged research · ${result.document_id}`,
                    html: result.html,
                    source: "spawn_merge",
                  })}
                  data-testid="spawn-merge-open-write"
                  data-view-format="html"
                  data-has-twin-seed="1"
                  className="rounded border border-ink/30 px-2 py-1 text-[11px] font-mono underline hover:bg-ink/5 dark:border-bright/30"
                  title="Open Write with merged HTML + twin_seed (seeds note-taker when empty)"
                >
                  Open Write (HTML draft)
                </a>
              </div>
              <div
                className="prose max-h-40 overflow-auto text-sm"
                data-testid="spawn-merge-html"
                dangerouslySetInnerHTML={{ __html: result.html }}
              />
            </>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

export default SpawnMergePanel;
