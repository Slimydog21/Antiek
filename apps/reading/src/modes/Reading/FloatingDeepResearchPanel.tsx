/**
 * FloatingDeepResearchPanel - spawn/view/merge intents for highlight research.
 *
 * Free-file under Reading/. Pure client; no live provider dispatch.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  formatFloatingSummary,
  markFloatingCompleted,
  proposeCollectivePack,
  proposeDraftMerge,
  proposeFullMerge,
  setFloatingViewMode,
  spawnFloatingFromHighlight,
  type CollectivePackIntent,
  type FloatingDeepResearchInstance,
  type MergeIntent,
} from "../../api/floatingDeepResearch";

export interface FloatingDeepResearchPanelProps {
  /** Required gate provenance from reader host. */
  gated: boolean;
  initialParentAssetId?: string;
  initialHighlight?: string;
  spawnFn?: typeof spawnFloatingFromHighlight;
}

export default function FloatingDeepResearchPanel({
  gated,
  initialParentAssetId = "",
  initialHighlight = "",
  spawnFn = spawnFloatingFromHighlight,
}: FloatingDeepResearchPanelProps) {
  const [parent, setParent] = useState(initialParentAssetId);
  const [highlight, setHighlight] = useState(initialHighlight);
  const [prompt, setPrompt] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [instances, setInstances] = useState<FloatingDeepResearchInstance[]>(
    [],
  );
  const [mergeIntent, setMergeIntent] = useState<MergeIntent | null>(null);
  const [packIntent, setPackIntent] = useState<CollectivePackIntent | null>(
    null,
  );
  const [selected, setSelected] = useState<string[]>([]);

  function clearIntents() {
    setMergeIntent(null);
    setPackIntent(null);
  }

  function onSpawn() {
    setError(null);
    clearIntents();
    try {
      if (typeof gated !== "boolean") {
        throw new Error(
          "gated must be an explicit boolean from highlight provenance (fail closed)",
        );
      }
      const inst = spawnFn({
        parent_asset_id: parent.trim(),
        highlight: highlight.trim(),
        prompt: prompt.trim() || undefined,
        gated,
      });
      setInstances((prev) => [...prev, inst]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function updateInstance(
    id: string,
    fn: (i: FloatingDeepResearchInstance) => FloatingDeepResearchInstance,
  ) {
    setError(null);
    clearIntents();
    try {
      setInstances((prev) =>
        prev.map((i) => {
          if (i.instance_id !== id) return i;
          return fn(i);
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function onDraftMerge(id: string) {
    setError(null);
    setPackIntent(null);
    try {
      const inst = instances.find((i) => i.instance_id === id);
      if (!inst) throw new Error("instance not found");
      setMergeIntent(proposeDraftMerge(inst));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function onFullMerge(id: string) {
    setError(null);
    setPackIntent(null);
    try {
      const inst = instances.find((i) => i.instance_id === id);
      if (!inst) throw new Error("instance not found");
      setMergeIntent(proposeFullMerge(inst, { operator_ack: true }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function toggleSelect(id: string) {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  function onCollective() {
    setError(null);
    setMergeIntent(null);
    try {
      const chosen = instances.filter((i) => selected.includes(i.instance_id));
      setPackIntent(proposeCollectivePack(chosen));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="floating-deep-research-panel">
      <LemonCard
        title="Floating deep research"
        className="floating-deep-research-panel"
      >
        <p className="text-sm opacity-80" data-testid="fdr-blurb">
          Spawn a deep-research instance from a highlight. Float, fullscreen,
          draft-merge, full-merge (ack), or collective pack. Pure client —
          live_dispatched and merge_executed stay false.
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Parent asset id</span>
            <LemonInput
              value={parent}
              onChange={(e) => setParent(e.target.value)}
              data-testid="fdr-parent"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Highlight</span>
            <LemonInput
              value={highlight}
              onChange={(e) => setHighlight(e.target.value)}
              data-testid="fdr-highlight"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Prompt (optional)</span>
            <LemonInput
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              data-testid="fdr-prompt"
            />
          </label>
          <LemonButton
            variant="primary"
            onClick={onSpawn}
            data-testid="fdr-spawn"
          >
            Spawn floating instance
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="fdr-error">
              {error}
            </div>
          ) : null}
          <div data-testid="fdr-instances" className="flex flex-col gap-2">
            {instances.length === 0 ? (
              <div className="text-xs opacity-70" data-testid="fdr-empty">
                No instances — spawn from a highlight (no invent).
              </div>
            ) : (
              instances.map((inst) => (
                <div
                  key={inst.instance_id}
                  className="rounded border border-border p-2 text-sm"
                  data-testid={`fdr-instance-${inst.instance_id}`}
                >
                  <div data-testid={`fdr-summary-${inst.instance_id}`}>
                    {formatFloatingSummary(inst)}
                  </div>
                  <div className="flex flex-wrap gap-2 mt-2">
                    <LemonButton
                      onClick={() =>
                        updateInstance(inst.instance_id, (i) =>
                          setFloatingViewMode(i, "floating"),
                        )
                      }
                      data-testid={`fdr-float-${inst.instance_id}`}
                    >
                      Float
                    </LemonButton>
                    <LemonButton
                      onClick={() =>
                        updateInstance(inst.instance_id, (i) =>
                          setFloatingViewMode(i, "fullscreen"),
                        )
                      }
                      data-testid={`fdr-full-${inst.instance_id}`}
                    >
                      Fullscreen
                    </LemonButton>
                    <LemonButton
                      onClick={() =>
                        updateInstance(inst.instance_id, markFloatingCompleted)
                      }
                      data-testid={`fdr-complete-${inst.instance_id}`}
                    >
                      Mark completed
                    </LemonButton>
                    <LemonButton
                      onClick={() => onDraftMerge(inst.instance_id)}
                      data-testid={`fdr-draft-${inst.instance_id}`}
                    >
                      Draft merge intent
                    </LemonButton>
                    <LemonButton
                      onClick={() => onFullMerge(inst.instance_id)}
                      data-testid={`fdr-merge-${inst.instance_id}`}
                    >
                      Full merge intent
                    </LemonButton>
                    <label className="text-xs flex items-center gap-1">
                      <input
                        type="checkbox"
                        checked={selected.includes(inst.instance_id)}
                        onChange={() => toggleSelect(inst.instance_id)}
                        data-testid={`fdr-select-${inst.instance_id}`}
                      />
                      collective
                    </label>
                  </div>
                </div>
              ))
            )}
          </div>
          <LemonButton onClick={onCollective} data-testid="fdr-collective">
            Propose collective pack
          </LemonButton>
          {mergeIntent ? (
            <div data-testid="fdr-merge-intent" className="text-sm">
              {mergeIntent.kind} · executed=
              {String(mergeIntent.merge_executed)} · ack=
              {String(mergeIntent.operator_ack)}
            </div>
          ) : null}
          {packIntent ? (
            <div data-testid="fdr-pack-intent" className="text-sm">
              collective_pack · n={packIntent.instance_ids.length} ·
              dispatched={String(packIntent.pack_dispatched)}
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
