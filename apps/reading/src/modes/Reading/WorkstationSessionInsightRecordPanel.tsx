/**
 * WorkstationSessionInsightRecordPanel — wrestle memory pack.
 *
 * Free-file. record_persisted, prompts_injected, store_mutated always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeWorkstationSessionInsightRecord,
  formatWorkstationSessionInsightRecordSummary,
  type WorkstationSessionInsightRecordCompose,
} from "../../api/workstationSessionInsightRecordCompose";

export interface WorkstationSessionInsightRecordPanelProps {
  composeFn?: typeof composeWorkstationSessionInsightRecord;
}

export default function WorkstationSessionInsightRecordPanel({
  composeFn = composeWorkstationSessionInsightRecord,
}: WorkstationSessionInsightRecordPanelProps) {
  const [sessionId, setSessionId] = useState("ws-1");
  const [parent, setParent] = useState("asset-1");
  const [insight, setInsight] = useState("claim holds under noise");
  const [question, setQuestion] = useState("what is the sample size?");
  const [ack, setAck] = useState(true);
  const [forPrompt, setForPrompt] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<WorkstationSessionInsightRecordCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFn({
          session_id: sessionId.trim(),
          parent_asset_id: parent.trim(),
          operator_ack: ack,
          mark_for_prompt_context: forPrompt,
          records: [
            {
              record_id: "r1",
              kind: "insight",
              body: insight.trim() || "insight",
            },
            {
              record_id: "r2",
              kind: "question",
              body: question.trim() || "question",
            },
          ],
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="workstation-session-insight-record-panel">
      <LemonCard
        title="Workstation · session insight/question record"
        className="workstation-session-insight-record-panel"
      >
        <p className="text-sm opacity-80" data-testid="wsir-blurb">
          Record insights, questions, and data while wrestling — recursive
          substrate that can inform prompts. Pure — record_persisted and
          prompts_injected stay false.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Session id</span>
            <LemonInput
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              data-testid="wsir-session"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Parent asset</span>
            <LemonInput
              value={parent}
              onChange={(e) => setParent(e.target.value)}
              data-testid="wsir-parent"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Insight</span>
            <LemonInput
              value={insight}
              onChange={(e) => setInsight(e.target.value)}
              data-testid="wsir-insight"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Question</span>
            <LemonInput
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              data-testid="wsir-question"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={forPrompt}
              onChange={(e) => setForPrompt(e.target.checked)}
              data-testid="wsir-prompt"
            />
            <span>mark_for_prompt_context</span>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="wsir-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="wsir-compose"
          >
            Compose session record pack
          </LemonButton>
          {error ? (
            <p className="text-sm text-danger" data-testid="wsir-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="wsir-result"
            >
              <div data-testid="wsir-ready">
                record_ready={String(result.record_ready)}
              </div>
              <div data-testid="wsir-persisted">
                record_persisted={String(result.record_persisted)}
              </div>
              <div data-testid="wsir-injected">
                prompts_injected={String(result.prompts_injected)}
              </div>
              <div data-testid="wsir-summary">
                {formatWorkstationSessionInsightRecordSummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
