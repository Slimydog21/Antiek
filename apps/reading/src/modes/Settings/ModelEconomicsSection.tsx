/**
 * ModelEconomicsSection — composite Settings block for model choice + budget +
 * Antiek-bench presentation.
 *
 * Composes existing panels (#788 DecisionTree, #796 UsageBar, #799 Bench) so a
 * single mount point can be added to Settings/index when free. Does not own
 * index.tsx and does not dispatch models.
 */

import AntiekBenchPanel from "./AntiekBenchPanel";
import DecisionTreePanel from "./DecisionTreePanel";
import UsageBarPanel from "./UsageBarPanel";

export interface ModelEconomicsSectionProps {
  /** Optional title override for the section chrome. */
  title?: string;
  showDecisionTree?: boolean;
  showUsageBar?: boolean;
  showAntiekBench?: boolean;
}

export default function ModelEconomicsSection({
  title = "Model economics",
  showDecisionTree = true,
  showUsageBar = true,
  showAntiekBench = true,
}: ModelEconomicsSectionProps) {
  return (
    <section
      className="model-economics-section flex flex-col gap-4"
      data-testid="model-economics-section"
      aria-label={title}
    >
      <header data-testid="model-economics-header">
        <h2 className="font-mono text-sm uppercase tracking-wider">{title}</h2>
        <p className="text-xs opacity-70" data-testid="model-economics-blurb">
          Advisory model selection, budget projection, and weekly Antiek-bench
          presentation. Not production dispatch authority.
        </p>
      </header>
      {showDecisionTree ? (
        <div data-testid="model-economics-decision-tree-slot">
          <DecisionTreePanel />
        </div>
      ) : null}
      {showUsageBar ? (
        <div data-testid="model-economics-usage-bar-slot">
          <UsageBarPanel />
        </div>
      ) : null}
      {showAntiekBench ? (
        <div data-testid="model-economics-bench-slot">
          <AntiekBenchPanel />
        </div>
      ) : null}
    </section>
  );
}
