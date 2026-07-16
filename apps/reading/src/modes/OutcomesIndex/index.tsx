import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import observatoryArt from "../../brand/werner/outcomes/calibration_observatory_environment_v1.webp";
import LemonTable from "../../components/lemon/LemonTable";
import { apiFetch } from "../../lib/api";
import "./calibration-observatory.css";

export interface OutcomeRow {
  outcome_id: string;
  synthesis_id: string;
  observer: string;
  observed_at: string;
}

interface CalibrationObservatoryFrameProps {
  rows: OutcomeRow[];
  loading: boolean;
  error: boolean;
  observerFilter: string;
  onObserverFilterChange: (value: string) => void;
  onRetry: () => void;
  onOpenSynthesis: (synthesisId: string) => void;
  fixture?: boolean;
}

const SAFE_ERROR_MESSAGE =
  "Outcomes could not be loaded. Your research record is unchanged.";

/**
 * Presentational state boundary used by production and deterministic stories.
 * The raster is atmosphere only; live HTML owns every fact and action.
 */
export function CalibrationObservatoryFrame({
  rows,
  loading,
  error,
  observerFilter,
  onObserverFilterChange,
  onRetry,
  onOpenSynthesis,
  fixture = false,
}: CalibrationObservatoryFrameProps) {
  return (
    <div
      className={`calibration-observatory${fixture ? " calibration-observatory--fixture" : ""}`}
    >
      <img
        src={observatoryArt}
        alt=""
        aria-hidden="true"
        draggable={false}
        decoding="async"
      />
      <div className="calibration-observatory__veil" aria-hidden="true" />

      <header className="calibration-observatory__masthead">
        <p className="calibration-observatory__eyebrow">
          Antiek · calibration observatory
        </p>
        <h1>Outcomes</h1>
        <p>
          A record of the judgments you made across investigations—kept so
          future work can learn from what held up, what did not, and what
          remains unresolved.
        </p>
      </header>

      <div className="calibration-observatory__console">
        <div className="calibration-observatory__card">
          <section
            className="calibration-observatory__filter"
            aria-label="Filter outcomes by observer"
          >
            <label htmlFor="calibration-observer-filter">
              Filter by observer
            </label>
            <input
              id="calibration-observer-filter"
              type="text"
              value={observerFilter}
              onChange={(event) => onObserverFilterChange(event.target.value)}
              placeholder="__operator__ — leave blank for all"
            />
          </section>

          {error && (
            <div role="alert" className="calibration-observatory__error">
              <span>{SAFE_ERROR_MESSAGE}</span>
              <button type="button" onClick={onRetry}>
                Try again
              </button>
            </div>
          )}

          {loading && !error && (
            <p role="status" className="calibration-observatory__status">
              Reading the outcomes record…
            </p>
          )}

          {!loading && rows.length === 0 && !error && (
            <div className="calibration-observatory__empty">
              <p>No judgments match this observer yet.</p>
              <p>
                When you mark a synthesis validated, falsified, or
                indeterminate, its judgment will appear here.
              </p>
            </div>
          )}

          {!loading && !error && rows.length > 0 && (
            <LemonTable
              rows={rows}
              rowKey={(row) => row.outcome_id}
              onRowClick={(row) => onOpenSynthesis(row.synthesis_id)}
              columns={[
                {
                  key: "synthesis",
                  header: "Synthesis",
                  width: "55%",
                  render: (row) => (
                    <button
                      type="button"
                      className="calibration-observatory__synthesis-link"
                      onClick={(event) => {
                        event.stopPropagation();
                        onOpenSynthesis(row.synthesis_id);
                      }}
                    >
                      {row.synthesis_id}
                    </button>
                  ),
                },
                {
                  key: "observed",
                  header: "Observed",
                  render: (row) => (
                    <span className="calibration-observatory__observer">
                      {row.observed_at} · {row.observer}
                    </span>
                  ),
                },
                {
                  key: "outcome",
                  header: "Outcome id",
                  align: "right",
                  render: (row) => (
                    <span className="calibration-observatory__outcome-id">
                      {row.outcome_id}
                    </span>
                  ),
                },
              ]}
            />
          )}
        </div>
      </div>
    </div>
  );
}

export default function OutcomesIndex() {
  const navigate = useNavigate();
  const [rows, setRows] = useState<OutcomeRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [observerFilter, setObserverFilter] = useState("");
  const requestGeneration = useRef(0);

  const reload = useCallback(async () => {
    const generation = ++requestGeneration.current;
    setLoading(true);
    setError(false);
    try {
      const params = new URLSearchParams();
      if (observerFilter.trim()) {
        params.set("observer", observerFilter.trim());
      }
      params.set("limit", "200");
      const response = await apiFetch(`/outcomes?${params.toString()}`);
      if (!response.ok) throw new Error("Outcomes request failed");
      const data = await response.json();
      if (generation === requestGeneration.current) {
        setRows(data.outcomes ?? []);
      }
    } catch {
      if (generation === requestGeneration.current) {
        setError(true);
      }
    } finally {
      if (generation === requestGeneration.current) {
        setLoading(false);
      }
    }
  }, [observerFilter]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return (
    <CalibrationObservatoryFrame
      rows={rows}
      loading={loading}
      error={error}
      observerFilter={observerFilter}
      onObserverFilterChange={setObserverFilter}
      onRetry={() => void reload()}
      onOpenSynthesis={(synthesisId) =>
        navigate(`/outcomes/${encodeURIComponent(synthesisId)}`)
      }
    />
  );
}
