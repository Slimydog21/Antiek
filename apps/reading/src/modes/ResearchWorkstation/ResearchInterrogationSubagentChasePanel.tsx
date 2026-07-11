/**
 * ResearchInterrogationSubagentChasePanel — pure chase plan UI.
 *
 * Free-file. live_dispatched, pack_dispatched, record_persisted,
 * prompts_injected always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeResearchInterrogationSubagentChase,
  formatResearchInterrogationSubagentChaseSummary,
  type ChaseMode,
  type ResearchInterrogationSubagentChaseCompose,
} from "../../api/researchInterrogationSubagentChaseCompose";

export interface ResearchInterrogationSubagentChasePanelProps {
  composeFn?: typeof composeResearchInterrogationSubagentChase;
}

export default function ResearchInterrogationSubagentChasePanel({
  composeFn = composeResearchInterrogationSubagentChase,
}: ResearchInterrogationSubagentChasePanelProps) {
  const [sessionId, setSessionId] = useState("sess-1");
  const [parent, setParent] = useState("paper-1");
  const [q1, setQ1] = useState("What is the core claim?");
  const [q2, setQ2] = useState("What evidence is missing?");
  const [mode, setMode] = useState<ChaseMode>("swarm_fanout");
  const [ack, setAck] = useState(true);
  const [wouldExceed, setWouldExceed] = useState<"unknown" | "true" | "false">(
    "false",
  );
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<ResearchInterrogationSubagentChaseCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      const would_exceed: boolean | null =
        wouldExceed === "unknown"
          ? null
          : wouldExceed === "true"
            ? true
            : false;
      const questions =
        mode === "single_question"
          ? [{ question_id: "q1", body: q1.trim(), priority: 1 }]
          : [
              { question_id: "q1", body: q1.trim(), priority: 2 },
              { question_id: "q2", body: q2.trim(), priority: 1 },
            ];
      setResult(
        composeFn({
          session_id: sessionId.trim(),
          parent_asset_id: parent.trim(),
          questions,
          chase_mode: mode,
          would_exceed,
          source_families: ["arxiv", "substack"],
          mark_for_twin_record: true,
          operator_ack: ack,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="research-interrogation-subagent-chase-panel">
      <LemonCard
        title="Research · interrogation → subagent chase"
        className="research-interrogation-subagent-chase-panel"
      >
        <p className="text-sm opacity-80" data-testid="risc-blurb">
          Plan subagent chases off open interrogation questions while you
          wrestle with the asset. Pure intent — live_dispatched stays false.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Session</span>
            <LemonInput
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              data-testid="risc-session"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Parent asset</span>
            <LemonInput
              value={parent}
              onChange={(e) => setParent(e.target.value)}
              data-testid="risc-parent"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Question 1</span>
            <LemonInput
              value={q1}
              onChange={(e) => setQ1(e.target.value)}
              data-testid="risc-q1"
            />
          </label>
          {mode !== "single_question" ? (
            <label className="text-sm flex flex-col gap-1">
              <span>Question 2</span>
              <LemonInput
                value={q2}
                onChange={(e) => setQ2(e.target.value)}
                data-testid="risc-q2"
              />
            </label>
          ) : null}
          <label className="text-sm flex flex-col gap-1">
            <span>Chase mode</span>
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value as ChaseMode)}
              data-testid="risc-mode"
              className="border border-border rounded px-2 py-1 text-sm"
            >
              <option value="single_question">single_question</option>
              <option value="swarm_fanout">swarm_fanout</option>
              <option value="collective_merge_after">
                collective_merge_after
              </option>
            </select>
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>would_exceed (budget)</span>
            <select
              value={wouldExceed}
              onChange={(e) =>
                setWouldExceed(e.target.value as "unknown" | "true" | "false")
              }
              data-testid="risc-would-exceed"
              className="border border-border rounded px-2 py-1 text-sm"
            >
              <option value="false">false (budget ok)</option>
              <option value="true">true (would exceed)</option>
              <option value="unknown">unknown (null)</option>
            </select>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="risc-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="risc-compose"
          >
            Compose chase plan
          </LemonButton>
          {error ? (
            <p className="text-sm text-danger" data-testid="risc-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="risc-result"
            >
              <div data-testid="risc-ready">
                chase_ready={String(result.chase_ready)}
              </div>
              <div data-testid="risc-slots">slots={result.slot_count}</div>
              <div data-testid="risc-live">
                live_dispatched={String(result.live_dispatched)}
              </div>
              <div data-testid="risc-pack">
                pack_dispatched={String(result.pack_dispatched)}
              </div>
              <div data-testid="risc-record">
                record_persisted={String(result.record_persisted)}
              </div>
              <div data-testid="risc-prompts">
                prompts_injected={String(result.prompts_injected)}
              </div>
              <div data-testid="risc-summary">
                {formatResearchInterrogationSubagentChaseSummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
