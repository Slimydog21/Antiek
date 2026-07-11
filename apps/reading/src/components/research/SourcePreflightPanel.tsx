/**
 * SourcePreflightPanel — no-spend source pack preflight UI.
 *
 * Consumes POST /research/source-policy/preflight via #820 client.
 * Never invents offline_probe_ok or runner_consumes_today.
 */

import { useState } from "react";
import { LemonButton, LemonCard } from "../lemon";
import {
  formatProbeHonesty,
  postSourcePreflight,
  type SourcePolicy,
  type SourcePolicyPreflight,
} from "../../api/sourcePreflight";

const ALL: SourcePolicy[] = ["arxiv", "substack", "web", "operator_corpus"];

export interface SourcePreflightPanelProps {
  preflightFn?: typeof postSourcePreflight;
  initialPolicies?: SourcePolicy[];
}

export default function SourcePreflightPanel({
  preflightFn = postSourcePreflight,
  initialPolicies = ["arxiv", "substack"],
}: SourcePreflightPanelProps) {
  const [selected, setSelected] = useState<SourcePolicy[]>(initialPolicies);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SourcePolicyPreflight | null>(null);

  function toggle(p: SourcePolicy) {
    setSelected((prev) =>
      prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p],
    );
    setResult(null);
    setError(null);
  }

  async function onRun() {
    setBusy(true);
    setError(null);
    try {
      const body = await preflightFn({ source_policy: selected });
      setResult(body);
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div data-testid="source-preflight-panel">
      <LemonCard title="Source policy preflight" className="source-preflight-panel">
        <p className="text-sm opacity-80" data-testid="source-preflight-blurb">
          Offline readiness preflight for knowledge-dense sources (arxiv,
          Substack, web, operator corpus). Probe flags stay honest — never
          invented as true.
        </p>
        <div className="flex flex-wrap gap-3 mt-3">
          {ALL.map((p) => (
            <label key={p} className="text-sm flex items-center gap-1">
              <input
                type="checkbox"
                checked={selected.includes(p)}
                onChange={() => toggle(p)}
                data-testid={`source-preflight-toggle-${p}`}
              />
              {p}
            </label>
          ))}
        </div>
        <div className="mt-3">
          <LemonButton
            variant="primary"
            disabled={busy || selected.length === 0}
            onClick={() => void onRun()}
            data-testid="source-preflight-run"
          >
            {busy ? "Running…" : "Run preflight"}
          </LemonButton>
        </div>
        {error ? (
          <div className="text-sm text-danger mt-2" data-testid="source-preflight-error">
            {error}
          </div>
        ) : null}
        {result ? (
          <div data-testid="source-preflight-result" className="mt-3 flex flex-col gap-2">
            <div data-testid="source-preflight-receipt">
              Receipt: {result.source_receipt_id}
            </div>
            <div data-testid="source-preflight-gather">
              Gather mode: {result.gather_mode}
            </div>
            <ul data-testid="source-preflight-entries">
              {result.entries.map((e) => (
                <li key={e.source} data-testid={`source-preflight-entry-${e.source}`}>
                  {formatProbeHonesty(e)} — status={e.status}; adapter=
                  {e.adapter_importable ? "importable" : "not importable"}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </LemonCard>
    </div>
  );
}
