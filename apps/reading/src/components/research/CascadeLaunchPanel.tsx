/**
 * CascadeLaunchPanel — deep-research plan launch with source_policy honesty.
 *
 * Uses postCascadeLaunch (#838). Free-file: does not own cascade_routes or
 * DeepResearchWorkspace index. require_source_preflight without a policy
 * surfaces an error without inventing a successful launch.
 */

import { useMemo, useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../lemon";
import {
  ALLOWED_SOURCE_POLICIES,
  postCascadeLaunch,
  type CascadeLaunchResult,
  type SourcePolicyName,
} from "../../api/cascadeLaunch";

export interface CascadeLaunchPanelProps {
  launchFn?: typeof postCascadeLaunch;
  initialRootId?: string;
  initialPolicies?: SourcePolicyName[];
  initialRequirePreflight?: boolean;
}

export default function CascadeLaunchPanel({
  launchFn = postCascadeLaunch,
  initialRootId = "",
  initialPolicies = ["arxiv", "substack"],
  initialRequirePreflight = true,
}: CascadeLaunchPanelProps) {
  const [rootId, setRootId] = useState(initialRootId);
  const [selected, setSelected] = useState<SourcePolicyName[]>(initialPolicies);
  const [requirePreflight, setRequirePreflight] = useState(
    initialRequirePreflight,
  );
  const [budgetRaw, setBudgetRaw] = useState("0.50");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CascadeLaunchResult | null>(null);

  const budget = useMemo(() => {
    const n = Number(budgetRaw);
    return Number.isFinite(n) ? n : NaN;
  }, [budgetRaw]);

  function toggle(p: SourcePolicyName) {
    setSelected((prev) =>
      prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p],
    );
    setResult(null);
    setError(null);
  }

  async function onLaunch() {
    setBusy(true);
    setError(null);
    try {
      const body = await launchFn({
        root_id: rootId,
        source_policy: selected.length ? selected : null,
        require_source_preflight: requirePreflight,
        per_research_budget_usd: budget,
      });
      setResult(body);
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div data-testid="cascade-launch-panel">
      <LemonCard title="Cascade deep-research launch" className="cascade-launch-panel">
        <p className="text-sm opacity-80" data-testid="cascade-launch-blurb">
          Launch a plan with optional knowledge-dense source packs (arxiv,
          Substack, web, operator corpus). When preflight is required, a pack
          must be selected — success is never invented without a receipt.
        </p>

        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Plan root id</span>
            <LemonInput
              value={rootId}
              onChange={(e) => {
                setRootId(e.target.value);
                setResult(null);
                setError(null);
              }}
              data-testid="cascade-launch-root"
              aria-label="Plan root id"
            />
          </label>

          <label className="text-sm flex flex-col gap-1">
            <span>Per-research budget USD</span>
            <LemonInput
              value={budgetRaw}
              onChange={(e) => {
                setBudgetRaw(e.target.value);
                setResult(null);
                setError(null);
              }}
              data-testid="cascade-launch-budget"
              aria-label="Per-research budget USD"
            />
          </label>

          <div className="flex flex-wrap gap-3">
            {ALLOWED_SOURCE_POLICIES.map((p) => (
              <label key={p} className="text-sm flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={selected.includes(p)}
                  onChange={() => toggle(p)}
                  data-testid={`cascade-launch-src-${p}`}
                />
                {p}
              </label>
            ))}
          </div>

          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={requirePreflight}
              onChange={(e) => {
                setRequirePreflight(e.target.checked);
                setResult(null);
                setError(null);
              }}
              data-testid="cascade-launch-require"
            />
            Require source preflight (fail closed without pack)
          </label>

          <LemonButton
            variant="primary"
            disabled={busy}
            onClick={() => void onLaunch()}
            data-testid="cascade-launch-run"
          >
            {busy ? "Launching…" : "Launch cascade"}
          </LemonButton>

          {error ? (
            <div className="text-sm text-danger" data-testid="cascade-launch-error">
              {error}
            </div>
          ) : null}

          {result ? (
            <div data-testid="cascade-launch-result" className="flex flex-col gap-1">
              <div data-testid="cascade-launch-policy">
                Policy:{" "}
                {result.source_policy && result.source_policy.length
                  ? result.source_policy.join(", ")
                  : "(none)"}
              </div>
              <div data-testid="cascade-launch-require-echo">
                Require preflight: {result.require_source_preflight ? "yes" : "no"}
              </div>
              <div data-testid="cascade-launch-receipt">
                Receipt:{" "}
                {result.source_preflight
                  ? String(
                      (result.source_preflight as { source_receipt_id?: string })
                        .source_receipt_id ?? "present",
                    )
                  : "(none)"}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
