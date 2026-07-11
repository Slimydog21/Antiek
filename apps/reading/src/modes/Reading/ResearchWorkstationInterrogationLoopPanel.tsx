/**
 * ResearchWorkstationInterrogationLoopPanel — chase questions → prompt pack.
 *
 * Free-file. live_dispatch/record/prompts always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeResearchWorkstationInterrogationLoop,
  formatResearchWorkstationInterrogationLoopSummary,
  type ResearchWorkstationInterrogationLoopCompose,
} from "../../api/researchWorkstationInterrogationLoopCompose";

export interface ResearchWorkstationInterrogationLoopPanelProps {
  composeFn?: typeof composeResearchWorkstationInterrogationLoop;
}

export default function ResearchWorkstationInterrogationLoopPanel({
  composeFn = composeResearchWorkstationInterrogationLoop,
}: ResearchWorkstationInterrogationLoopPanelProps) {
  const [q1, setQ1] = useState("What is the core claim?");
  const [prompt, setPrompt] = useState(
    "Interrogate this asset and chase open questions",
  );
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<ResearchWorkstationInterrogationLoopCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFn({
          session_id: "sess-demo",
          parent_asset_id: "asset-demo",
          questions: [
            {
              question_id: "q1",
              body: q1.trim() || "Open question",
              priority: 2,
            },
            {
              question_id: "q2",
              body: "What counter-evidence exists?",
              priority: 1,
            },
          ],
          chase_mode: "swarm_fanout",
          prior_records: [
            {
              record_id: "i-demo",
              kind: "insight",
              body: "Session insight from prior wrestle",
            },
          ],
          user_prompt: prompt.trim() || "Continue interrogation",
          selected_model_id: "gpt-5.5",
          models: [
            { model_id: "gpt-5.5", projected_cost_usd_high: 0.4 },
            { model_id: "grok-4.5", projected_cost_usd_high: 0.2 },
          ],
          daily_cap_usd: 25,
          spent_usd: 2,
          projected_cost_usd_high: 0.4,
          would_exceed: false,
          source_families: ["arxiv", "web"],
          operator_ack: ack,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="research-workstation-interrogation-loop-panel">
      <LemonCard
        title="Research · interrogate → chase → prompt"
        className="research-workstation-interrogation-loop-panel"
      >
        <p className="text-sm opacity-80" data-testid="rwil-blurb">
          Send subagents to chase questions while recording session substrate
          into the next prompt and model decision. Pure — never dispatches.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Primary question</span>
            <LemonInput
              value={q1}
              onChange={(e) => setQ1(e.target.value)}
              data-testid="rwil-q1"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>User prompt</span>
            <LemonInput
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              data-testid="rwil-prompt"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="rwil-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            type="primary"
            onClick={onCompose}
            data-testid="rwil-compose"
          >
            Compose interrogation loop
          </LemonButton>
        </div>
        {error && (
          <p className="text-sm text-danger mt-2" data-testid="rwil-error">
            {error}
          </p>
        )}
        {result && (
          <div className="mt-3 text-sm" data-testid="rwil-result">
            <p data-testid="rwil-summary">
              {formatResearchWorkstationInterrogationLoopSummary(result)}
            </p>
            <ul className="list-disc pl-5 mt-1 opacity-80">
              <li>loop_ready={String(result.loop_ready)}</li>
              <li>chase_slots={result.chase.slot_count}</li>
              <li>live_dispatched={String(result.live_dispatched)}</li>
              <li>record_persisted={String(result.record_persisted)}</li>
              <li>prompts_injected={String(result.prompts_injected)}</li>
            </ul>
          </div>
        )}
      </LemonCard>
    </div>
  );
}
