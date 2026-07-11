/**
 * FloatingMultiSelectCollectiveCohesivePanel — multi-select floating
 * instances as one cohesive deep-research unit.
 *
 * Free-file. live_dispatched/pack_dispatched/merge/analysis_written always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeFloatingMultiSelectCollectiveCohesive,
  formatFloatingMultiSelectCollectiveCohesiveSummary,
  type FloatingMultiSelectCollectiveCohesiveCompose,
  type MultiSelectPackMode,
} from "../../api/floatingMultiSelectCollectiveCohesiveCompose";

export interface FloatingMultiSelectCollectiveCohesivePanelProps {
  composeFn?: typeof composeFloatingMultiSelectCollectiveCohesive;
}

export default function FloatingMultiSelectCollectiveCohesivePanel({
  composeFn = composeFloatingMultiSelectCollectiveCohesive,
}: FloatingMultiSelectCollectiveCohesivePanelProps) {
  const [prompt, setPrompt] = useState(
    "Synthesize selected floating researches as one unit",
  );
  const [mode, setMode] = useState<MultiSelectPackMode>("cohesive_prompt");
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<FloatingMultiSelectCollectiveCohesiveCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFn({
          session_id: "sess-demo",
          parent_asset_id: "asset-demo",
          members: [
            {
              instance_id: "float-1",
              parent_asset_id: "asset-demo",
              status: "open",
              highlight: "highlight A",
              prior_prompt: "chase A",
              context: ["ctx-a"],
            },
            {
              instance_id: "float-2",
              parent_asset_id: "asset-demo",
              status: "completed",
              highlight: "highlight B",
              findings: ["finding-b"],
            },
            {
              instance_id: "float-3",
              parent_asset_id: "asset-demo",
              status: "completed",
              highlight: "highlight C",
              findings: ["finding-c"],
            },
          ],
          selected_instance_ids: ["float-1", "float-2", "float-3"],
          pack_mode: mode,
          cohesive_prompt: prompt.trim(),
          operator_ack: ack,
          analysis_kind:
            mode === "cohesive_plus_analysis" ? "draft_analysis" : null,
          extra_context: ["operator note"],
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="floating-multi-select-collective-cohesive-panel">
      <LemonCard
        title="Reading · multi-select → cohesive collective"
        className="floating-multi-select-collective-cohesive-panel"
      >
        <p className="text-sm opacity-80" data-testid="fmsc-blurb">
          Multi-select floating deep researches and prompt them as one cohesive
          unit (optional draft analysis). Pure — never dispatches or writes.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Cohesive prompt</span>
            <LemonInput
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              data-testid="fmsc-prompt"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Pack mode</span>
            <select
              value={mode}
              onChange={(e) =>
                setMode(e.target.value as MultiSelectPackMode)
              }
              data-testid="fmsc-mode"
              className="border border-border rounded px-2 py-1 text-sm"
            >
              <option value="cohesive_prompt">cohesive_prompt</option>
              <option value="collective_pack">collective_pack</option>
              <option value="cohesive_plus_analysis">
                cohesive_plus_analysis
              </option>
            </select>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="fmsc-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            type="primary"
            onClick={onCompose}
            data-testid="fmsc-compose"
          >
            Compose multi-select pack
          </LemonButton>
        </div>
        {error && (
          <p className="text-sm text-danger mt-2" data-testid="fmsc-error">
            {error}
          </p>
        )}
        {result && (
          <div className="mt-3 text-sm" data-testid="fmsc-result">
            <p data-testid="fmsc-summary">
              {formatFloatingMultiSelectCollectiveCohesiveSummary(result)}
            </p>
            <ul className="list-disc pl-5 mt-1 opacity-80">
              <li>pack_ready={String(result.pack_ready)}</li>
              <li>live_dispatched={String(result.live_dispatched)}</li>
              <li>pack_dispatched={String(result.pack_dispatched)}</li>
              <li>merge_executed={String(result.merge_executed)}</li>
              <li>analysis_written={String(result.analysis_written)}</li>
              <li>
                cohesive=
                {result.cohesive
                  ? `${result.cohesive.member_count} members`
                  : "null"}
              </li>
              <li>
                analysis=
                {result.analysis ? result.analysis.kind : "null"}
              </li>
            </ul>
          </div>
        )}
      </LemonCard>
    </div>
  );
}
