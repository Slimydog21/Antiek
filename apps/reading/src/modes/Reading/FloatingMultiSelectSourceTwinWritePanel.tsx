/**
 * FloatingMultiSelectSourceTwinWritePanel — free-file.
 */

import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeFloatingMultiSelectSourceTwinWrite,
  formatFloatingMultiSelectSourceTwinWriteSummary,
  type FloatingMultiSelectSourceTwinWriteCompose,
} from "../../api/floatingMultiSelectSourceTwinWriteCompose";

export default function FloatingMultiSelectSourceTwinWritePanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<FloatingMultiSelectSourceTwinWriteCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFloatingMultiSelectSourceTwinWrite({
          session_id: "sess-demo",
          draft_id: "draft-demo",
          parent_asset_id: "asset-demo",
          members: [
            {
              instance_id: "inst-a",
              parent_asset_id: "asset-demo",
              status: "completed",
              highlight: "scaling claim",
              findings: ["finding-a"],
            },
            {
              instance_id: "inst-b",
              parent_asset_id: "asset-demo",
              status: "completed",
              findings: ["finding-b"],
            },
          ],
          selected_instance_ids: ["inst-a", "inst-b"],
          pack_mode: "cohesive_prompt",
          cohesive_prompt: "Synthesize multi-select into write draft",
          operator_ack: ack,
          requested_families: ["arxiv"],
          sources: [
            {
              source_id: "arx-demo",
              family: "arxiv",
              title: "Demo paper",
              html_fragment: "<article>HTML</article>",
            },
          ],
          quality_overall: 0.85,
          would_exceed: false,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="floating-multi-select-source-twin-write-panel">
      <LemonCard title="Research · multi-select + sources → twin → write">
        <p className="text-sm opacity-80">
          Cohesive multi-agent DR with sources feeds twin then write draft +
          analysis. Pure.
        </p>
        <label className="text-sm flex items-center gap-2 mt-2">
          <input
            type="checkbox"
            checked={ack}
            onChange={(e) => setAck(e.target.checked)}
            data-testid="fmstw-ack"
          />
          operator_ack
        </label>
        <LemonButton
          type="primary"
          onClick={onCompose}
          className="mt-2"
          data-testid="fmstw-compose"
        >
          Compose multi-select → write
        </LemonButton>
        {error && <p className="text-sm text-danger mt-2">{error}</p>}
        {result && (
          <div className="mt-3 text-sm" data-testid="fmstw-result">
            <p>{formatFloatingMultiSelectSourceTwinWriteSummary(result)}</p>
            <ul className="list-disc pl-5">
              <li>pack_ready={String(result.pack_ready)}</li>
              <li>draft_written={String(result.draft_written)}</li>
              <li>analysis_written={String(result.analysis_written)}</li>
            </ul>
          </div>
        )}
      </LemonCard>
    </div>
  );
}
