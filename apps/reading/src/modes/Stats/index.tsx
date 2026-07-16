import { useCallback, useEffect, useRef, useState } from "react";

import { useInWindow } from "../../components/windows/windowHostContext";
import { apiFetch } from "../../lib/api";
import atlasEnvironment from "../../brand/werner/stats/substrate_atlas_environment_v1.webp";
import "./substrate-atlas.css";

export interface StatsResponse {
  counts?: Record<string, number>;
  warnings?: unknown[];
}

export const TABLE_GROUPS = [
  {
    title: "Research",
    tables: ["investigations", "documents", "chunks", "nodes", "edges"],
  },
  { title: "Notebooks", tables: ["notebooks", "notebook_blocks"] },
  { title: "Interviews", tables: ["interview_projects", "interviews"] },
  { title: "IP + payouts", tables: ["ip_holders", "payout_transfers"] },
  { title: "Outcomes + shared substrate", tables: ["outcomes", "skill_rules"] },
  { title: "Privacy + governance", tables: ["deletion_requests"] },
] as const;

export type StatsViewProps = {
  data: StatsResponse | null;
  loading?: boolean;
  error?: boolean;
  onRefresh?: () => void;
  inWindow?: boolean;
};

function displayCount(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value.toLocaleString()
    : "Unknown";
}

/** The single production/presentational boundary; stories render this directly. */
export function StatsView({
  data,
  loading = false,
  error = false,
  onRefresh,
  inWindow = false,
}: StatsViewProps) {
  const warningCount = Array.isArray(data?.warnings) ? data.warnings.length : 0;
  const Surface = inWindow ? "section" : "main";

  return (
    <div
      className={`substrate-atlas flex flex-col ${inWindow ? "substrate-atlas--window h-full" : "h-screen"}`}
    >
      <Surface
        aria-label={inWindow ? "Substrate atlas" : undefined}
        className={`substrate-atlas__main flex-1 overflow-y-auto ${inWindow ? "bg-transparent" : "bg-ice-0 dark:bg-charcoal-2"}`}
      >
        {!inWindow && (
          <img
            className="substrate-atlas__environment"
            src={atlasEnvironment}
            alt=""
            aria-hidden="true"
            draggable={false}
          />
        )}
        {!inWindow && (
          <div className="substrate-atlas__veil" aria-hidden="true" />
        )}
        <div className="substrate-atlas__console">
          <header className="substrate-atlas__header">
            <div>
              <p className="substrate-atlas__eyebrow">
                Durable substrate · cardinality survey
              </p>
              <h1>Substrate atlas</h1>
              <p className="substrate-atlas__lede">
                A measured inventory of Antiek’s load-bearing tables. Unknown
                means an area was not reported—not empty.
              </p>
            </div>
            <button
              type="button"
              onClick={onRefresh}
              disabled={loading}
              className="substrate-atlas__refresh"
            >
              {loading ? "Surveying…" : "Refresh survey"}
            </button>
          </header>

          {error && (
            <div
              className="substrate-atlas__notice substrate-atlas__notice--error"
              role="alert"
            >
              <strong>Survey unavailable.</strong> We couldn’t measure the
              substrate. Try again.
            </div>
          )}
          {warningCount > 0 && (
            <div className="substrate-atlas__notice" role="status">
              Some substrate areas could not be measured{" "}
              <span>
                {warningCount.toLocaleString()}{" "}
                {warningCount === 1 ? "area" : "areas"}
              </span>
            </div>
          )}
          {loading && !data && (
            <p className="substrate-atlas__loading" role="status">
              Calibrating instruments…
            </p>
          )}

          <div className="substrate-atlas__groups" aria-busy={loading}>
            {TABLE_GROUPS.map((group, index) => (
              <section
                className="substrate-atlas__group"
                key={group.title}
                aria-labelledby={`atlas-group-${index}`}
              >
                <div className="substrate-atlas__group-heading">
                  <span aria-hidden="true">0{index + 1}</span>
                  <h2 id={`atlas-group-${index}`}>{group.title}</h2>
                </div>
                <dl>
                  {group.tables.map((table) => (
                    <div className="substrate-atlas__metric" key={table}>
                      <dt>{table.replace(/_/g, " ")}</dt>
                      <dd>{displayCount(data?.counts?.[table])}</dd>
                    </div>
                  ))}
                </dl>
              </section>
            ))}
          </div>
        </div>
      </Surface>
    </div>
  );
}

export default function Stats() {
  const inWindow = useInWindow();
  const [data, setData] = useState<StatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const request = useRef(0);

  const reload = useCallback(async () => {
    const id = ++request.current;
    setLoading(true);
    setError(false);
    try {
      const response = await apiFetch("/stats");
      if (!response.ok) throw new Error("stats request failed");
      const next = (await response.json()) as StatsResponse;
      if (id === request.current) setData(next);
    } catch {
      if (id === request.current) setError(true);
    } finally {
      if (id === request.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
    return () => {
      request.current += 1;
    };
  }, [reload]);
  return (
    <StatsView
      data={data}
      loading={loading}
      error={error}
      onRefresh={() => void reload()}
      inWindow={inWindow}
    />
  );
}
