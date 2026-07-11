/**
 * ResearchWrestleCompetitionQualityPanel — wrestle + world-class DR pack UI.
 *
 * Free-file. live_dispatch_authorized, remote_fetched, backlog_mutated always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeResearchWrestleCompetitionQuality,
  formatResearchWrestleCompetitionQualitySummary,
  type ResearchWrestleCompetitionQualityCompose,
} from "../../api/researchWrestleCompetitionQualityCompose";

export interface ResearchWrestleCompetitionQualityPanelProps {
  composeFn?: typeof composeResearchWrestleCompetitionQuality;
}

export default function ResearchWrestleCompetitionQualityPanel({
  composeFn = composeResearchWrestleCompetitionQuality,
}: ResearchWrestleCompetitionQualityPanelProps) {
  const [sessionId, setSessionId] = useState("sess-1");
  const [parent, setParent] = useState("paper-1");
  const [quality, setQuality] = useState("0.8");
  const [wouldExceed, setWouldExceed] = useState<"false" | "true" | "unknown">(
    "false",
  );
  const [requireNoBehind, setRequireNoBehind] = useState(false);
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<ResearchWrestleCompetitionQualityCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      const q = Number(quality);
      const would_exceed =
        wouldExceed === "unknown" ? null : wouldExceed === "true";
      setResult(
        composeFn({
          session_id: sessionId.trim(),
          parent_asset_id: parent.trim(),
          floating_instance_count: 2,
          completed_floating_count: 1,
          twin_insight_count: 3,
          twin_question_count: 2,
          open_question_count: 1,
          preferred_view_mode: "floating",
          competitor_decisions: [
            {
              competitor: "Perplexity",
              area: "citation_grounding",
              decision_summary: "Inline citations with source cards",
              antiek_status: "parity",
            },
            {
              competitor: "OpenAI DR",
              area: "multi_agent_orchestration",
              decision_summary: "Planner + browser agents",
              antiek_status: "behind",
              residual: "strengthen collective floating cohesive pack",
            },
          ],
          requested_families: ["arxiv", "substack"],
          citations: [
            {
              citation_id: "c1",
              family: "arxiv",
              title: "Scaling Laws under Noise",
              external_id: "arxiv:2301.00001",
            },
            {
              citation_id: "c2",
              family: "substack",
              title: "Research notes on evals",
              url: "https://example.substack.com/p/evals",
            },
          ],
          quality_overall: Number.isFinite(q) ? q : null,
          quality_floor: 0.5,
          would_exceed,
          operator_ack: ack,
          require_no_behind_gaps: requireNoBehind,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="research-wrestle-competition-quality-panel">
      <LemonCard
        title="Research · wrestle + competition quality"
        className="research-wrestle-competition-quality-panel"
      >
        <p className="text-sm opacity-80" data-testid="rwcq-blurb">
          Live wrestle substrate plus world-class DR pack (competition gaps,
          arxiv/substack citations, quality/budget). Pure — no live dispatch.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Session</span>
            <LemonInput
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              data-testid="rwcq-session"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Parent asset</span>
            <LemonInput
              value={parent}
              onChange={(e) => setParent(e.target.value)}
              data-testid="rwcq-parent"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Quality overall (0..1)</span>
            <LemonInput
              value={quality}
              onChange={(e) => setQuality(e.target.value)}
              data-testid="rwcq-quality"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>would_exceed</span>
            <select
              value={wouldExceed}
              onChange={(e) =>
                setWouldExceed(e.target.value as "false" | "true" | "unknown")
              }
              data-testid="rwcq-would"
              className="border border-border rounded px-2 py-1 text-sm"
            >
              <option value="false">false</option>
              <option value="true">true</option>
              <option value="unknown">unknown (null)</option>
            </select>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={requireNoBehind}
              onChange={(e) => setRequireNoBehind(e.target.checked)}
              data-testid="rwcq-no-behind"
            />
            <span>require_no_behind_gaps</span>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="rwcq-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="rwcq-compose"
          >
            Compose wrestle + competition quality
          </LemonButton>
          {error ? (
            <p className="text-sm text-danger" data-testid="rwcq-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="rwcq-result"
            >
              <div data-testid="rwcq-ready">
                session_ready={String(result.session_ready)}
              </div>
              <div data-testid="rwcq-wrestle">
                wrestle_ready={String(result.wrestle.wrestle_ready)}
              </div>
              <div data-testid="rwcq-pack">
                quality_pack_ready=
                {String(result.competition_quality.pack_ready)}
              </div>
              <div data-testid="rwcq-live">
                live_dispatch_authorized=
                {String(result.live_dispatch_authorized)}
              </div>
              <div data-testid="rwcq-remote">
                remote_fetched={String(result.remote_fetched)}
              </div>
              <div data-testid="rwcq-backlog">
                backlog_mutated={String(result.backlog_mutated)}
              </div>
              <div data-testid="rwcq-summary">
                {formatResearchWrestleCompetitionQualitySummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
