/**
 * WorkstationRecordPromptModelDecisionPanel — records → prompt → model UI.
 *
 * Free-file. record_persisted, prompts_injected, live_router always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeWorkstationRecordPromptModelDecision,
  formatWorkstationRecordPromptModelDecisionSummary,
  type WorkstationRecordPromptModelDecisionCompose,
} from "../../api/workstationRecordPromptModelDecisionCompose";

export interface WorkstationRecordPromptModelDecisionPanelProps {
  composeFn?: typeof composeWorkstationRecordPromptModelDecision;
}

export default function WorkstationRecordPromptModelDecisionPanel({
  composeFn = composeWorkstationRecordPromptModelDecision,
}: WorkstationRecordPromptModelDecisionPanelProps) {
  const [sessionId, setSessionId] = useState("sess-1");
  const [parent, setParent] = useState("paper-1");
  const [insight, setInsight] = useState("scaling holds under noise");
  const [question, setQuestion] = useState("What is the failure mode?");
  const [prompt, setPrompt] = useState("Summarize open questions for next pass");
  const [modelId, setModelId] = useState("gpt-5");
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<WorkstationRecordPromptModelDecisionCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFn({
          session_id: sessionId.trim(),
          parent_asset_id: parent.trim(),
          records: [
            {
              record_id: "r1",
              kind: "insight",
              body: insight.trim(),
              source_ref: parent.trim(),
            },
            {
              record_id: "r2",
              kind: "question",
              body: question.trim(),
            },
          ],
          user_prompt: prompt.trim(),
          selected_model_id: modelId,
          models: [
            {
              model_id: "gpt-5",
              tier: "frontier",
              projected_cost_usd_high: 2,
            },
            {
              model_id: "composer-2.5",
              tier: "workhorse",
              projected_cost_usd_high: 0.5,
            },
          ],
          daily_cap_usd: 100,
          spent_usd: 40,
          projected_cost_usd_high: modelId === "gpt-5" ? 2 : 0.5,
          operator_ack: ack,
          focus_task: "deep_research",
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="workstation-record-prompt-model-decision-panel">
      <LemonCard
        title="Research · records → prompt → model decision"
        className="workstation-record-prompt-model-decision-panel"
      >
        <p className="text-sm opacity-80" data-testid="wrpmd-blurb">
          Record insights/questions, bridge into prompt context, choose model
          with usage bar + budget projection. Pure — never injects live.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Session</span>
            <LemonInput
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              data-testid="wrpmd-session"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Parent asset</span>
            <LemonInput
              value={parent}
              onChange={(e) => setParent(e.target.value)}
              data-testid="wrpmd-parent"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Insight</span>
            <LemonInput
              value={insight}
              onChange={(e) => setInsight(e.target.value)}
              data-testid="wrpmd-insight"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Question</span>
            <LemonInput
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              data-testid="wrpmd-question"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>User prompt</span>
            <LemonInput
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              data-testid="wrpmd-prompt"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Model</span>
            <select
              value={modelId}
              onChange={(e) => setModelId(e.target.value)}
              data-testid="wrpmd-model"
              className="border border-border rounded px-2 py-1 text-sm"
            >
              <option value="gpt-5">gpt-5</option>
              <option value="composer-2.5">composer-2.5</option>
            </select>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="wrpmd-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="wrpmd-compose"
          >
            Compose records → prompt → model
          </LemonButton>
          {error ? (
            <p className="text-sm text-danger" data-testid="wrpmd-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="wrpmd-result"
            >
              <div data-testid="wrpmd-ready">
                pack_ready={String(result.pack_ready)}
              </div>
              <div data-testid="wrpmd-usage">
                usage_percent=
                {result.usage_percent === null
                  ? "null"
                  : String(result.usage_percent)}
              </div>
              <div data-testid="wrpmd-would">
                would_exceed=
                {result.would_exceed === null
                  ? "null"
                  : String(result.would_exceed)}
              </div>
              <div data-testid="wrpmd-inject">
                prompts_injected={String(result.prompts_injected)}
              </div>
              <div data-testid="wrpmd-router">
                live_router_authorized=
                {String(result.live_router_authorized)}
              </div>
              <div data-testid="wrpmd-summary">
                {formatWorkstationRecordPromptModelDecisionSummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
