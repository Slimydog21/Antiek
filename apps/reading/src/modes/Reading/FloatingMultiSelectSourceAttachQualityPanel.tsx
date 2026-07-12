/**
 * FloatingMultiSelectSourceAttachQualityPanel — free-file.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeFloatingMultiSelectSourceAttachQuality,
  formatFloatingMultiSelectSourceAttachQualitySummary,
  type FloatingMultiSelectSourceAttachQualityCompose,
} from "../../api/floatingMultiSelectSourceAttachQualityCompose";

export default function FloatingMultiSelectSourceAttachQualityPanel() {
  const [prompt, setPrompt] = useState(
    "Synthesize selected floats with arxiv/substack",
  );
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<FloatingMultiSelectSourceAttachQualityCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFloatingMultiSelectSourceAttachQuality({
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
              highlight: "counter-evidence",
              findings: ["finding-b"],
            },
          ],
          selected_instance_ids: ["inst-a", "inst-b"],
          pack_mode: "cohesive_prompt",
          cohesive_prompt: prompt.trim() || "Synthesize",
          operator_ack: ack,
          requested_families: ["arxiv", "substack"],
          sources: [
            {
              source_id: "arx-demo",
              family: "arxiv",
              title: "Demo paper",
              html_fragment: "<article>HTML</article>",
            },
            {
              source_id: "sub-demo",
              family: "substack",
              title: "Demo essay",
              html_fragment: "<article>essay</article>",
            },
          ],
          quality_overall: 0.85,
          quality_floor: 0.7,
          would_exceed: false,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="floating-multi-select-source-attach-quality-panel">
      <LemonCard title="Research · multi-select floats + source quality">
        <p className="text-sm opacity-80">
          Cohesive multi-agent DR with arxiv/substack quality attach. Pure.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <LemonInput
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            data-testid="fmsaq-prompt"
          />
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="fmsaq-ack"
            />
            operator_ack
          </label>
          <LemonButton
            type="primary"
            onClick={onCompose}
            data-testid="fmsaq-compose"
          >
            Compose multi-select + sources
          </LemonButton>
        </div>
        {error && <p className="text-sm text-danger mt-2">{error}</p>}
        {result && (
          <div className="mt-3 text-sm" data-testid="fmsaq-result">
            <p>
              {formatFloatingMultiSelectSourceAttachQualitySummary(result)}
            </p>
            <ul className="list-disc pl-5">
              <li>pack_ready={String(result.pack_ready)}</li>
              <li>remote_fetched={String(result.remote_fetched)}</li>
              <li>live_dispatched={String(result.live_dispatched)}</li>
            </ul>
          </div>
        )}
      </LemonCard>
    </div>
  );
}
