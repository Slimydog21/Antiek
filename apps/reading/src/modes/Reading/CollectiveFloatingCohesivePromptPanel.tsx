/**
 * CollectiveFloatingCohesivePromptPanel - multi-select pack → cohesive prompt.
 *
 * Free-file. Never live-dispatches; live_dispatched always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  buildCollectiveFloatingCohesivePrompt,
  formatCohesivePromptSummary,
  type CohesiveUnitPromptIntent,
} from "../../api/collectiveFloatingCohesivePrompt";

export interface CollectiveFloatingCohesivePromptPanelProps {
  buildFn?: typeof buildCollectiveFloatingCohesivePrompt;
}

export default function CollectiveFloatingCohesivePromptPanel({
  buildFn = buildCollectiveFloatingCohesivePrompt,
}: CollectiveFloatingCohesivePromptPanelProps) {
  const [parent, setParent] = useState("asset-1");
  const [idsRaw, setIdsRaw] = useState("fdr_1\nfdr_2");
  const [prompt, setPrompt] = useState(
    "Treat these floating researches as one unit: reconcile claims and list open questions",
  );
  const [contextRaw, setContextRaw] = useState("");
  const [ack, setAck] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CohesiveUnitPromptIntent | null>(null);

  function buildMembers() {
    const ids = idsRaw
      .split(/\r?\n/)
      .map((s) => s.trim())
      .filter(Boolean);
    return ids.map((instance_id) => ({
      instance_id,
      parent_asset_id: parent.trim(),
      status: "completed" as const,
    }));
  }

  function onBuild() {
    setError(null);
    setResult(null);
    try {
      const extra = contextRaw
        .split(/\r?\n/)
        .map((s) => s.trim())
        .filter(Boolean);
      setResult(
        buildFn(buildMembers(), {
          cohesive_prompt: prompt,
          operator_ack: ack,
          extra_context: extra.length ? extra : null,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="collective-floating-cohesive-prompt-panel">
      <LemonCard
        title="Collective floating → cohesive prompt"
        className="collective-floating-cohesive-prompt-panel"
      >
        <p className="text-sm opacity-80" data-testid="cfcp-blurb">
          Multi-select floating deep-research instances and prompt them as one
          cohesive unit. Pure pack intent — live_dispatched stays false.
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Parent asset id</span>
            <LemonInput
              value={parent}
              onChange={(e) => setParent(e.target.value)}
              data-testid="cfcp-parent"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Instance ids (one per line, ≥2)</span>
            <textarea
              value={idsRaw}
              onChange={(e) => setIdsRaw(e.target.value)}
              data-testid="cfcp-ids"
              className="border border-border rounded px-2 py-1 text-sm min-h-[4rem]"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Cohesive prompt</span>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              data-testid="cfcp-prompt"
              className="border border-border rounded px-2 py-1 text-sm min-h-[4rem]"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Extra context (optional, one per line)</span>
            <textarea
              value={contextRaw}
              onChange={(e) => setContextRaw(e.target.value)}
              data-testid="cfcp-context"
              className="border border-border rounded px-2 py-1 text-sm min-h-[3rem]"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="cfcp-ack"
            />
            operator_ack (sets pack_ready; still no live dispatch)
          </label>
          <LemonButton
            variant="primary"
            onClick={onBuild}
            data-testid="cfcp-build"
          >
            Build cohesive pack intent
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="cfcp-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div
              data-testid="cfcp-result"
              className="text-sm flex flex-col gap-1"
            >
              <div data-testid="cfcp-summary">
                {formatCohesivePromptSummary(result)}
              </div>
              <div data-testid="cfcp-dispatched">
                live_dispatched={String(result.live_dispatched)}
              </div>
              <div data-testid="cfcp-ready">
                pack_ready={String(result.pack_ready)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
