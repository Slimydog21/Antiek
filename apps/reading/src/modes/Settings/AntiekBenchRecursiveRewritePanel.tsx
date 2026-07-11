/**
 * AntiekBenchRecursiveRewritePanel - propose weekly bench rewrites.
 *
 * Free-file. Advisory only; applied always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  formatBenchRewriteSummary,
  proposeAntiekBenchRecursiveRewrite,
  type BenchRewriteProposal,
} from "../../api/antiekBenchRecursiveRewrite";

export interface AntiekBenchRecursiveRewritePanelProps {
  proposeFn?: typeof proposeAntiekBenchRecursiveRewrite;
  initialWeekLabel?: string;
}

export default function AntiekBenchRecursiveRewritePanel({
  proposeFn = proposeAntiekBenchRecursiveRewrite,
  initialWeekLabel = "",
}: AntiekBenchRecursiveRewritePanelProps) {
  const [week, setWeek] = useState(initialWeekLabel);
  const [patternsRaw, setPatternsRaw] = useState(
    "citation_binding|model-a|failed|3\ncitation_binding|model-b|worked|2",
  );
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BenchRewriteProposal | null>(null);

  function onPropose() {
    setError(null);
    setResult(null);
    try {
      const patterns = patternsRaw
        .split(/\r?\n/)
        .map((l) => l.trim())
        .filter(Boolean)
        .map((line, i) => {
          const parts = line.split("|").map((p) => p.trim());
          if (parts.length < 3) {
            throw new Error(
              `line ${i + 1} must be task_family|model_id|outcome|n?`,
            );
          }
          const outcome = parts[2] as
            | "worked"
            | "failed"
            | "mixed"
            | "unknown";
          const n = parts[3] ? Number(parts[3]) : undefined;
          return {
            task_family: parts[0],
            model_id: parts[1],
            outcome,
            n,
          };
        });
      setResult(
        proposeFn({
          week_label: week.trim(),
          patterns,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="antiek-bench-recursive-rewrite-panel">
      <LemonCard
        title="Antiek-bench recursive rewrite"
        className="antiek-bench-recursive-rewrite-panel"
      >
        <p className="text-sm opacity-80" data-testid="abrr-blurb">
          Learn from weekly usage outcomes to propose sub-benchmark rewrites.
          Advisory only — applied stays false (no production bench mutation).
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Week label</span>
            <LemonInput
              value={week}
              onChange={(e) => setWeek(e.target.value)}
              data-testid="abrr-week"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Patterns (task|model|outcome|n per line)</span>
            <textarea
              value={patternsRaw}
              onChange={(e) => setPatternsRaw(e.target.value)}
              data-testid="abrr-patterns"
              className="border border-border rounded px-2 py-1 text-sm min-h-[5rem]"
            />
          </label>
          <LemonButton
            variant="primary"
            onClick={onPropose}
            data-testid="abrr-run"
          >
            Propose rewrite
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="abrr-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div data-testid="abrr-result" className="text-sm flex flex-col gap-1">
              <div data-testid="abrr-summary">
                {formatBenchRewriteSummary(result)}
              </div>
              <div data-testid="abrr-applied">
                applied={String(result.applied)}
              </div>
              <div data-testid="abrr-count">
                proposals={result.proposals.length}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
