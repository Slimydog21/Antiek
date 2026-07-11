/**
 * CompetitionDeepResearchGapPanel - operator gap matrix for DR product.
 *
 * Free-file. Caller-supplied competitor decisions only; no scrape.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  buildCompetitionDeepResearchGap,
  formatCompetitionGapSummary,
  type CompetitionGapMatrix,
  type GapStatus,
  type DecisionArea,
} from "../../api/competitionDeepResearchGap";

const AREAS: DecisionArea[] = [
  "source_acquisition",
  "citation_grounding",
  "multi_agent_orchestration",
  "budget_controls",
  "html_native_reading",
  "model_routing",
  "evaluation_harness",
  "unattended_swarm",
];

export interface CompetitionDeepResearchGapPanelProps {
  buildFn?: typeof buildCompetitionDeepResearchGap;
}

export default function CompetitionDeepResearchGapPanel({
  buildFn = buildCompetitionDeepResearchGap,
}: CompetitionDeepResearchGapPanelProps) {
  const [competitor, setCompetitor] = useState("");
  const [area, setArea] = useState<DecisionArea>("source_acquisition");
  const [summary, setSummary] = useState("");
  const [status, setStatus] = useState<GapStatus>("unknown");
  const [residual, setResidual] = useState("");
  const [rowsJson, setRowsJson] = useState("[]");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CompetitionGapMatrix | null>(null);

  function onAddRow() {
    setError(null);
    try {
      const rows = JSON.parse(rowsJson) as unknown[];
      if (!Array.isArray(rows)) throw new Error("rows JSON must be an array");
      rows.push({
        competitor: competitor.trim(),
        area,
        decision_summary: summary.trim(),
        antiek_status: status,
        residual: residual.trim() || undefined,
      });
      setRowsJson(JSON.stringify(rows, null, 2));
      setCompetitor("");
      setSummary("");
      setResidual("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function onBuild() {
    setError(null);
    setResult(null);
    try {
      const decisions = JSON.parse(rowsJson) as unknown;
      if (!Array.isArray(decisions)) {
        throw new Error("decisions JSON must be an array");
      }
      setResult(
        buildFn({
          decisions: decisions as Parameters<typeof buildFn>[0]["decisions"],
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="competition-deep-research-gap-panel">
      <LemonCard
        title="Competition deep research gap matrix"
        className="competition-deep-research-gap-panel"
      >
        <p className="text-sm opacity-80" data-testid="cdrg-blurb">
          Record competitor technical decisions and Antiek gap status. Operator
          authored only — no invent / no live scrape. backlog_mutated stays
          false.
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Competitor</span>
            <LemonInput
              value={competitor}
              onChange={(e) => setCompetitor(e.target.value)}
              data-testid="cdrg-competitor"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Decision area</span>
            <select
              value={area}
              onChange={(e) => setArea(e.target.value as DecisionArea)}
              data-testid="cdrg-area"
              className="border border-border rounded px-2 py-1"
            >
              {AREAS.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Decision summary</span>
            <LemonInput
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              data-testid="cdrg-summary-input"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Antiek status</span>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value as GapStatus)}
              data-testid="cdrg-status"
              className="border border-border rounded px-2 py-1"
            >
              <option value="ahead">ahead</option>
              <option value="parity">parity</option>
              <option value="behind">behind</option>
              <option value="unknown">unknown</option>
            </select>
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Residual (optional)</span>
            <LemonInput
              value={residual}
              onChange={(e) => setResidual(e.target.value)}
              data-testid="cdrg-residual"
            />
          </label>
          <LemonButton onClick={onAddRow} data-testid="cdrg-add">
            Add decision row
          </LemonButton>
          <label className="text-sm flex flex-col gap-1">
            <span>Decisions JSON</span>
            <textarea
              value={rowsJson}
              onChange={(e) => setRowsJson(e.target.value)}
              data-testid="cdrg-json"
              className="border border-border rounded px-2 py-1 text-sm min-h-[5rem] font-mono"
            />
          </label>
          <LemonButton
            variant="primary"
            onClick={onBuild}
            data-testid="cdrg-run"
          >
            Build gap matrix
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="cdrg-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div data-testid="cdrg-result" className="text-sm flex flex-col gap-1">
              <div data-testid="cdrg-summary">
                {formatCompetitionGapSummary(result)}
              </div>
              <div data-testid="cdrg-behind">
                behind_count={result.behind_count}
              </div>
              <div data-testid="cdrg-backlog">
                backlog_mutated={String(result.backlog_mutated)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
