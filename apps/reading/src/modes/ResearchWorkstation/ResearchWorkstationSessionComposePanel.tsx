/**
 * ResearchWorkstationSessionComposePanel - session readiness snapshot.
 *
 * Free-file. Never authorizes live dispatch.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeResearchWorkstationSession,
  formatResearchWorkstationSessionSummary,
  type ResearchWorkstationSessionCompose,
} from "../../api/researchWorkstationSessionCompose";

export interface ResearchWorkstationSessionComposePanelProps {
  composeFn?: typeof composeResearchWorkstationSession;
}

export default function ResearchWorkstationSessionComposePanel({
  composeFn = composeResearchWorkstationSession,
}: ResearchWorkstationSessionComposePanelProps) {
  const [sessionId, setSessionId] = useState("sess-1");
  const [parentId, setParentId] = useState("asset-1");
  const [floatCount, setFloatCount] = useState("1");
  const [sources, setSources] = useState("2");
  const [quality, setQuality] = useState("0.8");
  const [wouldExceed, setWouldExceed] = useState<"false" | "true" | "null">(
    "false",
  );
  const [twin, setTwin] = useState(true);
  const [cohesive, setCohesive] = useState(false);
  const [override, setOverride] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<ResearchWorkstationSessionCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      const qRaw = quality.trim();
      const quality_overall = qRaw === "" || qRaw === "null" ? null : Number(qRaw);
      setResult(
        composeFn({
          session_id: sessionId,
          parent_asset_id: parentId,
          floating_instance_count: Number(floatCount),
          twin_bound: twin,
          source_family_count: Number(sources),
          quality_overall,
          would_exceed:
            wouldExceed === "null" ? null : wouldExceed === "true",
          cohesive_pack_ready: cohesive,
          operator_override: override,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="research-workstation-session-compose-panel">
      <LemonCard
        title="Research workstation session compose"
        className="research-workstation-session-compose-panel"
      >
        <p className="text-sm opacity-80" data-testid="rwsc-blurb">
          Compose workstation session readiness from floating, twin, sources,
          quality, and budget signals. Pure advisory —
          live_dispatch_authorized stays false.
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Session id</span>
            <LemonInput
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              data-testid="rwsc-session"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Parent asset id</span>
            <LemonInput
              value={parentId}
              onChange={(e) => setParentId(e.target.value)}
              data-testid="rwsc-parent"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Floating instance count</span>
            <LemonInput
              value={floatCount}
              onChange={(e) => setFloatCount(e.target.value)}
              data-testid="rwsc-float"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Source family count</span>
            <LemonInput
              value={sources}
              onChange={(e) => setSources(e.target.value)}
              data-testid="rwsc-sources"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Quality overall (blank/null = unknown)</span>
            <LemonInput
              value={quality}
              onChange={(e) => setQuality(e.target.value)}
              data-testid="rwsc-quality"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>would_exceed</span>
            <select
              value={wouldExceed}
              onChange={(e) =>
                setWouldExceed(e.target.value as "false" | "true" | "null")
              }
              data-testid="rwsc-would"
              className="border border-border rounded px-2 py-1 text-sm"
            >
              <option value="false">false</option>
              <option value="true">true</option>
              <option value="null">null (unknown)</option>
            </select>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={twin}
              onChange={(e) => setTwin(e.target.checked)}
              data-testid="rwsc-twin"
            />
            twin_bound
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={cohesive}
              onChange={(e) => setCohesive(e.target.checked)}
              data-testid="rwsc-cohesive"
            />
            cohesive_pack_ready
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={override}
              onChange={(e) => setOverride(e.target.checked)}
              data-testid="rwsc-override"
            />
            operator_override
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="rwsc-compose"
          >
            Compose session
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="rwsc-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div
              data-testid="rwsc-result"
              className="text-sm flex flex-col gap-1"
            >
              <div data-testid="rwsc-summary">
                {formatResearchWorkstationSessionSummary(result)}
              </div>
              <div data-testid="rwsc-ready">
                session_ready={String(result.session_ready)}
              </div>
              <div data-testid="rwsc-dispatch">
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
