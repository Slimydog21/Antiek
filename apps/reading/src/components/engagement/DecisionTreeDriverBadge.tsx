/**
 * DecisionTreeDriverBadge — show installed decision-tree driver (residual cw).
 *
 * Read-only advisory surface: model choice is Settings-owned; this badge
 * makes the active driver visible on research/reading hosts without implying
 * NotDiamond authority.
 */

import { useEffect, useState } from "react";
import {
  fetchDecisionTreeSelection,
  type DecisionTreeSelectionResponse,
} from "../../api/settings";

export function DecisionTreeDriverBadge() {
  const [tree, setTree] = useState<DecisionTreeSelectionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void fetchDecisionTreeSelection()
      .then((t) => {
        if (!cancelled) setTree(t);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div
      className="text-[11px] font-mono text-shadow-1 dark:text-moonlight"
      data-testid="decision-tree-driver-badge"
      data-view-format="html"
    >
      {error ? (
        <span data-testid="decision-tree-driver-error">Driver unknown</span>
      ) : tree?.installed && tree.model_id ? (
        <span data-testid="decision-tree-driver-active">
          Driver: {tree.provider_id ?? "?"} / {tree.model_id}
        </span>
      ) : (
        <span data-testid="decision-tree-driver-none">
          Driver: (none — Settings → decision tree)
        </span>
      )}
    </div>
  );
}

export default DecisionTreeDriverBadge;
