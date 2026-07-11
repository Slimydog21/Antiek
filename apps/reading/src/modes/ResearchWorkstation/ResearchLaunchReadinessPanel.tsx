/**
 * ResearchLaunchReadinessPanel - advisory launch gate for deep research.
 *
 * Free-file. live_dispatch_authorized always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  evaluateResearchLaunchReadiness,
  formatLaunchReadinessSummary,
  type ResearchLaunchReadinessDecision,
} from "../../api/researchLaunchReadiness";

export interface ResearchLaunchReadinessPanelProps {
  evaluateFn?: typeof evaluateResearchLaunchReadiness;
  initialSessionId?: string;
}

export default function ResearchLaunchReadinessPanel({
  evaluateFn = evaluateResearchLaunchReadiness,
  initialSessionId = "",
}: ResearchLaunchReadinessPanelProps) {
  const [sessionId, setSessionId] = useState(initialSessionId);
  const [sourcesRaw, setSourcesRaw] = useState("2");
  const [qualityRaw, setQualityRaw] = useState("");
  const [floorRaw, setFloorRaw] = useState("0.5");
  const [exceedMode, setExceedMode] = useState<"false" | "true" | "null">(
    "false",
  );
  const [override, setOverride] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<ResearchLaunchReadinessDecision | null>(null);

  function onEval() {
    setError(null);
    setResult(null);
    try {
      const source_family_count = Number(sourcesRaw);
      const quality_overall =
        qualityRaw.trim() === "" ? null : Number(qualityRaw);
      const quality_floor = Number(floorRaw);
      const would_exceed =
        exceedMode === "null" ? null : exceedMode === "true";
      setResult(
        evaluateFn({
          session_id: sessionId.trim(),
          source_family_count,
          quality_overall,
          quality_floor,
          would_exceed,
          operator_override: override,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="research-launch-readiness-panel">
      <LemonCard
        title="Research launch readiness"
        className="research-launch-readiness-panel"
      >
        <p className="text-sm opacity-80" data-testid="rlr-blurb">
          Gate deep research launch on sources, quality floor, and budget
          projection honesty. live_dispatch_authorized always stays false.
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Session id</span>
            <LemonInput
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              data-testid="rlr-session"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Source family count</span>
            <LemonInput
              value={sourcesRaw}
              onChange={(e) => setSourcesRaw(e.target.value)}
              data-testid="rlr-sources"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Quality overall (blank = unknown)</span>
            <LemonInput
              value={qualityRaw}
              onChange={(e) => setQualityRaw(e.target.value)}
              data-testid="rlr-quality"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Quality floor</span>
            <LemonInput
              value={floorRaw}
              onChange={(e) => setFloorRaw(e.target.value)}
              data-testid="rlr-floor"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>would_exceed</span>
            <select
              value={exceedMode}
              onChange={(e) =>
                setExceedMode(e.target.value as "false" | "true" | "null")
              }
              data-testid="rlr-exceed"
              className="border border-border rounded px-2 py-1"
            >
              <option value="false">false</option>
              <option value="true">true</option>
              <option value="null">null (unknown)</option>
            </select>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={override}
              onChange={(e) => setOverride(e.target.checked)}
              data-testid="rlr-override"
            />
            operator_override
          </label>
          <LemonButton
            variant="primary"
            onClick={onEval}
            data-testid="rlr-run"
          >
            Evaluate readiness
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="rlr-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div data-testid="rlr-result" className="text-sm flex flex-col gap-1">
              <div data-testid="rlr-summary">
                {formatLaunchReadinessSummary(result)}
              </div>
              <div data-testid="rlr-launch">
                launch_ready={String(result.launch_ready)}
              </div>
              <div data-testid="rlr-live">
                live_dispatch_authorized=
                {String(result.live_dispatch_authorized)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
