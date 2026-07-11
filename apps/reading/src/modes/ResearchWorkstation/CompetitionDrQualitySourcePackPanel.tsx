/**
 * CompetitionDrQualitySourcePackPanel — world-class DR readiness pack UI.
 *
 * Free-file. live_dispatch_authorized, remote_fetched, backlog_mutated always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeCompetitionDrQualitySourcePack,
  formatCompetitionDrQualitySourcePackSummary,
  type CompetitionDrQualitySourcePackCompose,
} from "../../api/competitionDrQualitySourcePackCompose";

export interface CompetitionDrQualitySourcePackPanelProps {
  composeFn?: typeof composeCompetitionDrQualitySourcePack;
}

export default function CompetitionDrQualitySourcePackPanel({
  composeFn = composeCompetitionDrQualitySourcePack,
}: CompetitionDrQualitySourcePackPanelProps) {
  const [sessionId, setSessionId] = useState("sess-1");
  const [quality, setQuality] = useState("0.8");
  const [wouldExceed, setWouldExceed] = useState<"false" | "true" | "unknown">(
    "false",
  );
  const [requireNoBehind, setRequireNoBehind] = useState(false);
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<CompetitionDrQualitySourcePackCompose | null>(null);

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
    <div data-testid="competition-dr-quality-source-pack-panel">
      <LemonCard
        title="Research · competition + quality + sources pack"
        className="competition-dr-quality-source-pack-panel"
      >
        <p className="text-sm opacity-80" data-testid="cdqsp-blurb">
          World-class DR readiness: competition gaps, arxiv/substack citations,
          quality + budget gate. Pure — live_dispatch stays false.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Session</span>
            <LemonInput
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              data-testid="cdqsp-session"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Quality overall (0..1)</span>
            <LemonInput
              value={quality}
              onChange={(e) => setQuality(e.target.value)}
              data-testid="cdqsp-quality"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>would_exceed</span>
            <select
              value={wouldExceed}
              onChange={(e) =>
                setWouldExceed(e.target.value as "false" | "true" | "unknown")
              }
              data-testid="cdqsp-would"
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
              data-testid="cdqsp-no-behind"
            />
            <span>require_no_behind_gaps</span>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="cdqsp-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="cdqsp-compose"
          >
            Compose competition DR quality+source pack
          </LemonButton>
          {error ? (
            <p className="text-sm text-danger" data-testid="cdqsp-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="cdqsp-result"
            >
              <div data-testid="cdqsp-ready">
                pack_ready={String(result.pack_ready)}
              </div>
              <div data-testid="cdqsp-live">
                live_dispatch_authorized=
                {String(result.live_dispatch_authorized)}
              </div>
              <div data-testid="cdqsp-remote">
                remote_fetched={String(result.remote_fetched)}
              </div>
              <div data-testid="cdqsp-backlog">
                backlog_mutated={String(result.backlog_mutated)}
              </div>
              <div data-testid="cdqsp-summary">
                {formatCompetitionDrQualitySourcePackSummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
