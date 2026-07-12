/**
 * FloatingMultiSelectSourceAttachQualityTwinPanel — free-file.
 */

import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeFloatingMultiSelectSourceAttachQualityTwin,
  formatFloatingMultiSelectSourceAttachQualityTwinSummary,
  type FloatingMultiSelectSourceAttachQualityTwinCompose,
} from "../../api/floatingMultiSelectSourceAttachQualityTwinCompose";

export default function FloatingMultiSelectSourceAttachQualityTwinPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<FloatingMultiSelectSourceAttachQualityTwinCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFloatingMultiSelectSourceAttachQualityTwin({
          session_id: "sess-demo",
          parent_asset_id: "asset-demo",
          members: [
            {
              instance_id: "inst-a",
              parent_asset_id: "asset-demo",
              status: "open",
              highlight: "scaling claim",
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
          cohesive_prompt: "Synthesize with sources into twin",
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
    <div data-testid="floating-multi-select-source-attach-quality-twin-panel">
      <LemonCard title="Research · multi-select + sources → twin">
        <p className="text-sm opacity-80">
          Cohesive multi-agent DR with sources feeding recursive twin. Pure.
        </p>
        <label className="text-sm flex items-center gap-2 mt-2">
          <input
            type="checkbox"
            checked={ack}
            onChange={(e) => setAck(e.target.checked)}
            data-testid="fmsaqt-ack"
          />
          operator_ack
        </label>
        <LemonButton
          type="primary"
          onClick={onCompose}
          className="mt-2"
          data-testid="fmsaqt-compose"
        >
          Compose multi-select → twin
        </LemonButton>
        {error && <p className="text-sm text-danger mt-2">{error}</p>}
        {result && (
          <div className="mt-3 text-sm" data-testid="fmsaqt-result">
            <p>
              {formatFloatingMultiSelectSourceAttachQualityTwinSummary(result)}
            </p>
            <ul className="list-disc pl-5">
              <li>pack_ready={String(result.pack_ready)}</li>
              <li>twin_written={String(result.twin_written)}</li>
            </ul>
          </div>
        )}
      </LemonCard>
    </div>
  );
}
