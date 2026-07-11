/**
 * ResearchWrestleSessionSupercomposePanel — wrestle-loop readiness.
 *
 * Free-file. live_dispatch_authorized always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeResearchWrestleSession,
  formatResearchWrestleSessionSummary,
  type ResearchWrestleSessionSupercompose,
} from "../../api/researchWrestleSessionSupercompose";

export interface ResearchWrestleSessionSupercomposePanelProps {
  composeFn?: typeof composeResearchWrestleSession;
}

export default function ResearchWrestleSessionSupercomposePanel({
  composeFn = composeResearchWrestleSession,
}: ResearchWrestleSessionSupercomposePanelProps) {
  const [sessionId, setSessionId] = useState("ws-1");
  const [parent, setParent] = useState("asset-1");
  const [floating, setFloating] = useState("2");
  const [completed, setCompleted] = useState("1");
  const [insights, setInsights] = useState("3");
  const [twinQ, setTwinQ] = useState("2");
  const [openQ, setOpenQ] = useState("1");
  const [sources, setSources] = useState("2");
  const [quality, setQuality] = useState("0.8");
  const [citation, setCitation] = useState(true);
  const [wouldExceed, setWouldExceed] = useState<"false" | "true" | "null">(
    "false",
  );
  const [override, setOverride] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<ResearchWrestleSessionSupercompose | null>(null);

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
          parent_asset_id: parent.trim(),
          floating_instance_count: Number(floating),
          completed_floating_count: Number(completed),
          twin_insight_count: Number(insights),
          twin_question_count: Number(twinQ),
          open_question_count: Number(openQ),
          source_family_count: Number(sources),
          citation_pack_ready: citation,
          quality_overall: Number(quality),
          would_exceed,
          preferred_view_mode: "floating",
          operator_override: override,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="research-wrestle-session-supercompose-panel">
      <LemonCard
        title="Research wrestle session super-compose"
        className="research-wrestle-session-supercompose-panel"
      >
        <p className="text-sm opacity-80" data-testid="rwss-blurb">
          Interrogate · assess · wrestle readiness from floating instances,
          twin insights/questions, sources, quality, and budget. Pure —
          live_dispatch_authorized stays false.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Session id</span>
            <LemonInput
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              data-testid="rwss-session"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Parent asset</span>
            <LemonInput
              value={parent}
              onChange={(e) => setParent(e.target.value)}
              data-testid="rwss-parent"
            />
          </label>
          <div className="grid grid-cols-2 gap-2">
            <label className="text-sm flex flex-col gap-1">
              <span>Floating count</span>
              <LemonInput
                value={floating}
                onChange={(e) => setFloating(e.target.value)}
                data-testid="rwss-floating"
              />
            </label>
            <label className="text-sm flex flex-col gap-1">
              <span>Completed floating</span>
              <LemonInput
                value={completed}
                onChange={(e) => setCompleted(e.target.value)}
                data-testid="rwss-completed"
              />
            </label>
            <label className="text-sm flex flex-col gap-1">
              <span>Twin insights</span>
              <LemonInput
                value={insights}
                onChange={(e) => setInsights(e.target.value)}
                data-testid="rwss-insights"
              />
            </label>
            <label className="text-sm flex flex-col gap-1">
              <span>Twin questions</span>
              <LemonInput
                value={twinQ}
                onChange={(e) => setTwinQ(e.target.value)}
                data-testid="rwss-twinq"
              />
            </label>
            <label className="text-sm flex flex-col gap-1">
              <span>Open questions</span>
              <LemonInput
                value={openQ}
                onChange={(e) => setOpenQ(e.target.value)}
                data-testid="rwss-openq"
              />
            </label>
            <label className="text-sm flex flex-col gap-1">
              <span>Source families</span>
              <LemonInput
                value={sources}
                onChange={(e) => setSources(e.target.value)}
                data-testid="rwss-sources"
              />
            </label>
            <label className="text-sm flex flex-col gap-1">
              <span>Quality overall</span>
              <LemonInput
                value={quality}
                onChange={(e) => setQuality(e.target.value)}
                data-testid="rwss-quality"
              />
            </label>
          </div>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={citation}
              onChange={(e) => setCitation(e.target.checked)}
              data-testid="rwss-citation"
            />
            <span>Citation pack ready</span>
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>would_exceed</span>
            <select
              value={wouldExceed}
              onChange={(e) =>
                setWouldExceed(e.target.value as "false" | "true" | "null")
              }
              data-testid="rwss-would-exceed"
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
              checked={override}
              onChange={(e) => setOverride(e.target.checked)}
              data-testid="rwss-override"
            />
            <span>operator_override</span>
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="rwss-compose"
          >
            Compose wrestle readiness
          </LemonButton>
          {error ? (
            <p className="text-sm text-danger" data-testid="rwss-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="rwss-result"
            >
              <div data-testid="rwss-ready">
                wrestle_ready={String(result.wrestle_ready)}
              </div>
              <div data-testid="rwss-live">
                live_dispatch_authorized=
                {String(result.live_dispatch_authorized)}
              </div>
              <div data-testid="rwss-gates">
                floating={String(result.floating_ready)} twin=
                {String(result.twin_ready)} sources=
                {String(result.sources_ready)} quality=
                {String(result.quality_ready)} budget=
                {String(result.budget_ready)}
              </div>
              <div data-testid="rwss-summary">
                {formatResearchWrestleSessionSummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
