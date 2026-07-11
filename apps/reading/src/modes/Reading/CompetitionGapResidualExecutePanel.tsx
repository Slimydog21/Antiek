/**
 * CompetitionGapResidualExecutePanel — residual → agent execution package.
 *
 * Free-file. execution_authorized, backlog_mutated, store_mutated always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeCompetitionGapResidualExecute,
  formatCompetitionGapResidualExecuteSummary,
  type CompetitionGapResidualExecuteCompose,
} from "../../api/competitionGapResidualExecuteCompose";

export interface CompetitionGapResidualExecutePanelProps {
  composeFn?: typeof composeCompetitionGapResidualExecute;
}

export default function CompetitionGapResidualExecutePanel({
  composeFn = composeCompetitionGapResidualExecute,
}: CompetitionGapResidualExecutePanelProps) {
  const [residualId, setResidualId] = useState("res-citation-1");
  const [text, setText] = useState("Span-level citations in DR output");
  const [hint, setHint] = useState(
    "Wire citation spans into DR quality floor pure modules",
  );
  const [owned, setOwned] = useState(
    "apps/reading/src/api/deepResearchCitationSpans.ts",
  );
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<CompetitionGapResidualExecuteCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFn({
          residual: {
            residual_id: residualId.trim(),
            area: "citation_grounding",
            competitor: "perplexity",
            residual_text: text.trim(),
            antiek_status: "behind",
            priority: "P0",
            execution_hint: hint.trim(),
          },
          operator_ack: ack,
          proposed_owned_files: owned.trim() ? [owned.trim()] : null,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="competition-gap-residual-execute-panel">
      <LemonCard
        title="Competition gap residual · execution package"
        className="competition-gap-residual-execute-panel"
      >
        <p className="text-sm opacity-80" data-testid="cgre-blurb">
          Package one competition residual for perfect future-agent execution.
          Pure — execution_authorized stays false.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Residual id</span>
            <LemonInput
              value={residualId}
              onChange={(e) => setResidualId(e.target.value)}
              data-testid="cgre-id"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Residual text</span>
            <LemonInput
              value={text}
              onChange={(e) => setText(e.target.value)}
              data-testid="cgre-text"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Execution hint</span>
            <LemonInput
              value={hint}
              onChange={(e) => setHint(e.target.value)}
              data-testid="cgre-hint"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Proposed owned file</span>
            <LemonInput
              value={owned}
              onChange={(e) => setOwned(e.target.value)}
              data-testid="cgre-owned"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="cgre-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="cgre-compose"
          >
            Compose execution package
          </LemonButton>
          {error ? (
            <p className="text-sm text-danger" data-testid="cgre-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="cgre-result"
            >
              <div data-testid="cgre-ready">
                package_ready={String(result.package_ready)}
              </div>
              <div data-testid="cgre-exec">
                execution_authorized=
                {String(result.execution_authorized)}
              </div>
              <div data-testid="cgre-backlog">
                backlog_mutated={String(result.backlog_mutated)}
              </div>
              <div data-testid="cgre-summary">
                {formatCompetitionGapResidualExecuteSummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
