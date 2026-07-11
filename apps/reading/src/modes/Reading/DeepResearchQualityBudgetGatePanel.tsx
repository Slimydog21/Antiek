/**
 * DeepResearchQualityBudgetGatePanel — quality + budget launch gate.
 *
 * Free-file. live_dispatch_authorized always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeDeepResearchQualityBudgetGate,
  formatDeepResearchQualityBudgetGateSummary,
  type DeepResearchQualityBudgetGateCompose,
} from "../../api/deepResearchQualityBudgetGateCompose";

export interface DeepResearchQualityBudgetGatePanelProps {
  composeFn?: typeof composeDeepResearchQualityBudgetGate;
}

export default function DeepResearchQualityBudgetGatePanel({
  composeFn = composeDeepResearchQualityBudgetGate,
}: DeepResearchQualityBudgetGatePanelProps) {
  const [sessionId, setSessionId] = useState("dr-1");
  const [quality, setQuality] = useState("0.82");
  const [wouldExceed, setWouldExceed] = useState<"false" | "true" | "null">(
    "false",
  );
  const [citation, setCitation] = useState(true);
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<DeepResearchQualityBudgetGateCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      const would_exceed =
        wouldExceed === "null"
          ? null
          : wouldExceed === "true"
            ? true
            : false;
      setResult(
        composeFn({
          session_id: sessionId.trim(),
          quality_overall: Number(quality),
          quality_floor: 0.5,
          would_exceed,
          citation_pack_ready: citation,
          operator_ack: ack,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="deep-research-quality-budget-gate-panel">
      <LemonCard
        title="Deep research · quality + budget gate"
        className="deep-research-quality-budget-gate-panel"
      >
        <p className="text-sm opacity-80" data-testid="drqbg-blurb">
          Gate DR launch on quality floor and budget honesty. Pure —
          live_dispatch_authorized stays false.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Session id</span>
            <LemonInput
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              data-testid="drqbg-session"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Quality overall</span>
            <LemonInput
              value={quality}
              onChange={(e) => setQuality(e.target.value)}
              data-testid="drqbg-quality"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>would_exceed</span>
            <select
              value={wouldExceed}
              onChange={(e) =>
                setWouldExceed(e.target.value as "false" | "true" | "null")
              }
              data-testid="drqbg-budget"
              className="border border-border rounded px-2 py-1 text-sm"
            >
              <option value="false">false</option>
              <option value="true">true</option>
              <option value="null">null</option>
            </select>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={citation}
              onChange={(e) => setCitation(e.target.checked)}
              data-testid="drqbg-citation"
            />
            <span>citation_pack_ready</span>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="drqbg-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="drqbg-compose"
          >
            Compose gate
          </LemonButton>
          {error ? (
            <p className="text-sm text-danger" data-testid="drqbg-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="drqbg-result"
            >
              <div data-testid="drqbg-ready">
                gate_ready={String(result.gate_ready)}
              </div>
              <div data-testid="drqbg-live">
                live_dispatch_authorized=
                {String(result.live_dispatch_authorized)}
              </div>
              <div data-testid="drqbg-summary">
                {formatDeepResearchQualityBudgetGateSummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
