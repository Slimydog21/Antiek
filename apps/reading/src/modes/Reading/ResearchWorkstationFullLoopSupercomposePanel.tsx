/**
 * ResearchWorkstationFullLoopSupercomposePanel — full research loop readiness.
 *
 * Free-file. live_dispatch_authorized always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeResearchWorkstationFullLoop,
  formatResearchWorkstationFullLoopSummary,
  type ResearchWorkstationFullLoopSupercompose,
} from "../../api/researchWorkstationFullLoopSupercompose";

export interface ResearchWorkstationFullLoopSupercomposePanelProps {
  composeFn?: typeof composeResearchWorkstationFullLoop;
}

export default function ResearchWorkstationFullLoopSupercomposePanel({
  composeFn = composeResearchWorkstationFullLoop,
}: ResearchWorkstationFullLoopSupercomposePanelProps) {
  const [sessionId, setSessionId] = useState("ws-1");
  const [sources, setSources] = useState("2");
  const [attachReady, setAttachReady] = useState(true);
  const [wouldExceed, setWouldExceed] = useState<"false" | "true" | "null">(
    "false",
  );
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<ResearchWorkstationFullLoopSupercompose | null>(null);

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
          wrestle: {
            session_id: sessionId.trim(),
            parent_asset_id: "asset-1",
            floating_instance_count: 2,
            completed_floating_count: 1,
            twin_insight_count: 2,
            twin_question_count: 1,
            open_question_count: 1,
            source_family_count: Number(sources),
            citation_pack_ready: true,
            quality_overall: 0.85,
            would_exceed,
            preferred_view_mode: "floating",
          },
          source_attach: {
            attach_ready: attachReady,
            remote_fetched: false,
            source_count: Number(sources),
          },
          view_mode: {
            preferred_view_mode: "floating",
            floating_instance_count: 2,
          },
          budget: {
            would_exceed,
            selected_model_id: "gpt-5",
          },
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="research-workstation-full-loop-supercompose-panel">
      <LemonCard
        title="Research workstation · full loop super-compose"
        className="research-workstation-full-loop-supercompose-panel"
      >
        <p className="text-sm opacity-80" data-testid="rwfl-blurb">
          Wrestle + HTML sources + view mode + budget as one readiness
          snapshot. Pure — live_dispatch_authorized stays false.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Session id</span>
            <LemonInput
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              data-testid="rwfl-session"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Source count</span>
            <LemonInput
              value={sources}
              onChange={(e) => setSources(e.target.value)}
              data-testid="rwfl-sources"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={attachReady}
              onChange={(e) => setAttachReady(e.target.checked)}
              data-testid="rwfl-attach"
            />
            <span>source attach_ready</span>
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>would_exceed</span>
            <select
              value={wouldExceed}
              onChange={(e) =>
                setWouldExceed(e.target.value as "false" | "true" | "null")
              }
              data-testid="rwfl-budget"
              className="border border-border rounded px-2 py-1 text-sm"
            >
              <option value="false">false</option>
              <option value="true">true</option>
              <option value="null">null</option>
            </select>
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="rwfl-compose"
          >
            Compose full loop
          </LemonButton>
          {error ? (
            <p className="text-sm text-danger" data-testid="rwfl-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="rwfl-result"
            >
              <div data-testid="rwfl-ready">
                full_loop_ready={String(result.full_loop_ready)}
              </div>
              <div data-testid="rwfl-live">
                live_dispatch_authorized=
                {String(result.live_dispatch_authorized)}
              </div>
              <div data-testid="rwfl-summary">
                {formatResearchWorkstationFullLoopSummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
