import { useCallback, useEffect, useState } from "react";

import SessionBrandChrome from "../../brand/SessionBrandChrome";
import { apiFetch } from "../../lib/api";
import { GateLedger } from "./GateLedger";
import type { GateView } from "./GateLedger";
import { Roadmap } from "./Roadmap";
import type { RoadmapView } from "./Roadmap";

/**
 * Coordination mode — one operator surface for "what's blocked and why"
 * (antiek-unified SPR-05).
 *
 * Two read-only views, both derived on read from canonical sources this mode
 * never writes:
 *
 *  - Gate ledger: a view over docs/operator_gate_actions.md (GET
 *    /coordination/gates). The eight binding gates, once, with a per-product
 *    impact column. No per-product gate duplication.
 *  - Roadmap: the five specs' rosters + SPR-01's dependency DAG (GET
 *    /coordination/roadmap). 45 sprints reconciled, DRW critical path explicit,
 *    unblocked-now derived from dependency state.
 *
 * Slots into the SPR-04 shared/operator bucket. Read-only — there is no control
 * here that mutates a gate or a sprint; gate state changes only in the
 * operator's source markdown.
 */

interface GatesResponse {
  source_path: string;
  gates: GateView[];
}

export default function Coordination() {
  const [gates, setGates] = useState<GatesResponse | null>(null);
  const [roadmap, setRoadmap] = useState<RoadmapView | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [gatesResp, roadmapResp] = await Promise.all([
        apiFetch("/coordination/gates"),
        apiFetch("/coordination/roadmap"),
      ]);
      if (!gatesResp.ok) {
        throw new Error(`GET /coordination/gates failed: HTTP ${gatesResp.status}`);
      }
      if (!roadmapResp.ok) {
        throw new Error(`GET /coordination/roadmap failed: HTTP ${roadmapResp.status}`);
      }
      setGates((await gatesResp.json()) as GatesResponse);
      setRoadmap((await roadmapResp.json()) as RoadmapView);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return (
    <div className="flex flex-col h-screen">
      <main className="flex-1 overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        <div className="max-w-4xl mx-auto px-8 py-10 space-y-10">
          <SessionBrandChrome
            testIdPrefix="coordination-home"
            title="Coordination"
          >
            <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
              What&rsquo;s blocked and why. The gate ledger is a read-only view over
              the canonical operator gate file; the roadmap reads the five
              specs&rsquo; rosters and the dependency DAG. Nothing on this page can
              change a gate&rsquo;s state — that is an operator action in the source
              file.
            </p>
          </SessionBrandChrome>

          {loading && (
            <p className="text-sm text-shadow-1 dark:text-moonlight">
              Loading coordination view…
            </p>
          )}
          {error && <p className="text-sm text-emperor">{error}</p>}

          {gates && (
            <GateLedger gates={gates.gates} sourcePath={gates.source_path} />
          )}
          {roadmap && <Roadmap roadmap={roadmap} />}
        </div>
      </main>
    </div>
  );
}
