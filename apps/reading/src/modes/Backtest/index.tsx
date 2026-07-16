import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import Werner from "../../brand/Werner";
import environment from "../../brand/werner/backtest/decision_weather_station_environment_v1.webp";
import { apiFetch } from "../../lib/api";
import "./decision-weather-station.css";

type UnknownRow = Record<string, unknown>;

export interface BacktestReport {
  synthesis_id: string;
  synthesis_timestamp: string;
  target_question: string;
  status: string;
  implicit_recommendation: string | null;
  substrate_manifest_counts: Record<string, number>;
  added_edges_since: number;
  superseded_edges_since: number;
  cited_edges_now_superseded_count: number;
  chunks_retired_downward_count: number;
  outcomes_recorded: number;
  cited_edges_now_superseded: UnknownRow[];
  chunks_retired_downward: UnknownRow[];
  outcomes: UnknownRow[];
}

export type BacktestViewProps = {
  synthesisId: string;
  report?: BacktestReport | null;
  state?: "ready" | "loading" | "not-found" | "error";
  onRetry?: () => void;
};

const text = (value: unknown) =>
  typeof value === "string" && value.trim() ? value : null;
const finite = (value: unknown) =>
  typeof value === "number" && Number.isFinite(value) ? value : null;
const rows = (value: unknown): UnknownRow[] =>
  Array.isArray(value)
    ? value.filter(
        (row): row is UnknownRow =>
          Boolean(row) && typeof row === "object" && !Array.isArray(row),
      )
    : [];

function When({ value }: { value: unknown }) {
  const label = text(value);
  if (!label) return <span>Time unavailable</span>;
  const parsed = Date.parse(label);
  return Number.isNaN(parsed) ? (
    <span>{label}</span>
  ) : (
    <time dateTime={label}>
      {new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(parsed)}
    </time>
  );
}

function Count({ value }: { value: unknown }) {
  const count = finite(value);
  return (
    <>
      {count === null ? "Not reported" : new Intl.NumberFormat().format(count)}
    </>
  );
}

function Signal({
  label,
  value,
  note,
  kind = "context",
}: {
  label: string;
  value: unknown;
  note: string;
  kind?: "context" | "load";
}) {
  const count = finite(value);
  return (
    <article className={`dws-signal dws-signal--${kind}`}>
      <p className="dws-signal__value">
        <Count value={value} />
      </p>
      <h3>{label}</h3>
      <p>{note}</p>
      {kind === "load" && count !== null && count > 0 ? (
        <span className="dws-flag">Review cited evidence</span>
      ) : null}
    </article>
  );
}

function EmptySection({ children }: { children: string }) {
  return <p className="dws-empty">{children}</p>;
}

function EdgeRow({ row }: { row: UnknownRow }) {
  const source = text(row.source),
    target = text(row.target),
    relation = text(row.relation);
  if (!source || !target || !relation)
    return (
      <li className="dws-detail dws-detail--unavailable">
        Detail unavailable in this report.
      </li>
    );
  return (
    <li className="dws-detail">
      <p className="dws-detail__statement">
        <strong>{source}</strong>
        <span>{relation}</span>
        <strong>{target}</strong>
      </p>
      <dl>
        <div>
          <dt>Edge</dt>
          <dd>{text(row.edge_id) ?? "Unavailable"}</dd>
        </div>
        <div>
          <dt>Closed</dt>
          <dd>
            <When value={row.valid_until} />
          </dd>
        </div>
        <div>
          <dt>Superseded by</dt>
          <dd>{text(row.superseded_by) ?? "No replacement edge recorded"}</dd>
        </div>
      </dl>
    </li>
  );
}

function ChunkRow({ row }: { row: UnknownRow }) {
  const id = text(row.chunk_id),
    from = finite(row.original_tier),
    to = finite(row.override_tier);
  if (!id || from === null || to === null)
    return (
      <li className="dws-detail dws-detail--unavailable">
        Detail unavailable in this report.
      </li>
    );
  return (
    <li className="dws-detail">
      <p className="dws-detail__statement">
        <strong>{id}</strong>
        <span>
          Tier {from} → Tier {to}
        </span>
      </p>
      <p>{text(row.reason) ?? "No retiering reason recorded."}</p>
      <p className="dws-meta">
        <When value={row.set_at} />
      </p>
    </li>
  );
}

function OutcomeItems({
  label,
  items,
  render,
}: {
  label: string;
  items: UnknownRow[];
  render: (row: UnknownRow, index: number) => React.ReactNode;
}) {
  if (!items.length) return null;
  return (
    <section className="dws-observation-group">
      <h4>{label}</h4>
      <ul>{items.map(render)}</ul>
    </section>
  );
}

function OutcomeRow({ row }: { row: UnknownRow }) {
  const observer = text(row.observer),
    observedAt = text(row.observed_at);
  if (!observer || !observedAt)
    return (
      <li className="dws-detail dws-detail--unavailable">
        Observation detail unavailable in this report.
      </li>
    );
  const theses = rows(row.thesis_outcomes),
    falsifications = rows(row.falsification_outcomes),
    risks = rows(row.execution_risk_outcomes);
  return (
    <li className="dws-detail dws-observation">
      <header>
        <div>
          <p className="dws-kicker">Observed by</p>
          <h3>{observer}</h3>
        </div>
        <p className="dws-meta">
          <When value={observedAt} />
        </p>
      </header>
      <OutcomeItems
        label="Thesis observations"
        items={theses}
        render={(item, i) => (
          <li key={i}>
            <strong>{text(item.thesis_claim) ?? "Claim unavailable"}</strong>
            <span>
              {text(item.outcome)?.replaceAll("_", " ") ??
                "Outcome unavailable"}
            </span>
            {text(item.evidence) ? <p>{text(item.evidence)}</p> : null}
          </li>
        )}
      />
      <OutcomeItems
        label="Falsification observations"
        items={falsifications}
        render={(item, i) => (
          <li key={i}>
            <strong>{text(item.condition) ?? "Condition unavailable"}</strong>
            <span>
              {typeof item.occurred === "boolean"
                ? item.occurred
                  ? "Occurred"
                  : "Not observed"
                : "Result unavailable"}
            </span>
            {text(item.evidence) ? <p>{text(item.evidence)}</p> : null}
          </li>
        )}
      />
      <OutcomeItems
        label="Execution-risk observations"
        items={risks}
        render={(item, i) => (
          <li key={i}>
            <strong>{text(item.risk) ?? "Risk unavailable"}</strong>
            <span>
              {typeof item.manifested === "boolean"
                ? item.manifested
                  ? "Manifested"
                  : "Not observed"
                : "Result unavailable"}
              {text(item.severity_actual)
                ? ` · ${text(item.severity_actual)} severity`
                : ""}
            </span>
            {text(item.evidence) ? <p>{text(item.evidence)}</p> : null}
          </li>
        )}
      />
      {text(row.notes) ? (
        <p className="dws-notes">
          <strong>Observer note</strong>
          {text(row.notes)}
        </p>
      ) : null}
      {!theses.length &&
      !falsifications.length &&
      !risks.length &&
      !text(row.notes) ? (
        <p className="dws-empty">No observation details were included.</p>
      ) : null}
    </li>
  );
}

function EvidenceSection({
  id,
  title,
  description,
  reported,
  items,
  children,
}: {
  id: string;
  title: string;
  description: string;
  reported: number;
  items: UnknownRow[];
  children: React.ReactNode;
}) {
  const mismatch = Number.isFinite(reported) && reported !== items.length;
  return (
    <section className="dws-panel" aria-labelledby={id}>
      <header className="dws-panel__header">
        <div>
          <p className="dws-kicker">Measured report</p>
          <h2 id={id}>{title}</h2>
          <p>{description}</p>
        </div>
        <span className="dws-count">
          <Count value={reported} />
        </span>
      </header>
      {mismatch ? (
        <p className="dws-integrity" role="status">
          The report summary says {reported}, while {items.length} detail{" "}
          {items.length === 1 ? "row is" : "rows are"} available here.
        </p>
      ) : null}
      {items.length ? (
        <ul className="dws-list">{children}</ul>
      ) : (
        <EmptySection>No detail rows were reported.</EmptySection>
      )}
    </section>
  );
}

export function BacktestView({
  synthesisId,
  report = null,
  state = "ready",
  onRetry,
}: BacktestViewProps) {
  const noDrift =
    report &&
    report.cited_edges_now_superseded_count === 0 &&
    report.chunks_retired_downward_count === 0;
  const edges = rows(report?.cited_edges_now_superseded),
    chunks = rows(report?.chunks_retired_downward),
    outcomes = rows(report?.outcomes);
  return (
    <main className="dws-shell">
      <img
        className="dws-environment"
        src={environment}
        alt=""
        aria-hidden="true"
      />
      <div className="dws-veil" aria-hidden="true" />
      <div className="dws-content">
        <header className="dws-hero">
          <div>
            <p className="dws-eyebrow">Backtest · evidence aging</p>
            <h1>Decision weather station</h1>
            <p>
              Inspect what changed beneath an archived synthesis. This report
              separates background substrate churn from changes to evidence the
              synthesis actually cited.
            </p>
            <p className="dws-id">Synthesis · {synthesisId || "Unavailable"}</p>
          </div>
          <Werner
            mood={
              state === "loading"
                ? "thinking"
                : state === "not-found" || state === "error"
                  ? "empty"
                  : "idle"
            }
            size={88}
            label="Werner keeping watch at the decision weather station"
          />
        </header>
        {state === "loading" ? (
          <section className="dws-state" aria-live="polite">
            <span className="dws-pulse" aria-hidden="true" />
            <h2>Reading the instruments…</h2>
            <p>Comparing the archived manifest with the substrate now.</p>
          </section>
        ) : null}
        {state === "not-found" ? (
          <section className="dws-state">
            <h2>No archived synthesis found</h2>
            <p>
              A backtest can only inspect a synthesis that was archived with a
              substrate manifest.
            </p>
          </section>
        ) : null}
        {state === "error" ? (
          <section className="dws-state" role="alert">
            <h2>The station could not load this report</h2>
            <p>
              No conclusions were inferred. Try the read-only backtest again.
            </p>
            {onRetry ? (
              <button type="button" onClick={onRetry}>
                Try again
              </button>
            ) : null}
          </section>
        ) : null}
        {state === "ready" && report ? (
          <>
            <section
              className="dws-panel dws-synthesis"
              aria-labelledby="dws-synthesis"
            >
              <p className="dws-kicker">
                Archived position · not a current verdict
              </p>
              <h2 id="dws-synthesis">
                {report.target_question || "Target question unavailable"}
              </h2>
              <dl>
                <div>
                  <dt>Archived</dt>
                  <dd>
                    <When value={report.synthesis_timestamp} />
                  </dd>
                </div>
                <div>
                  <dt>Status then</dt>
                  <dd>{report.status || "Unavailable"}</dd>
                </div>
                <div>
                  <dt>Recommendation then</dt>
                  <dd>{report.implicit_recommendation || "None recorded"}</dd>
                </div>
                <div>
                  <dt>Manifest entries</dt>
                  <dd>
                    <Count
                      value={Object.values(
                        report.substrate_manifest_counts || {},
                      ).reduce((sum, value) => sum + (finite(value) ?? 0), 0)}
                    />
                  </dd>
                </div>
              </dl>
            </section>
            {noDrift ? (
              <section className="dws-weather dws-weather--quiet">
                <span aria-hidden="true">○</span>
                <div>
                  <p className="dws-kicker">Measured evidence weather</p>
                  <h2>No cited-evidence drift found</h2>
                  <p>
                    This report found no superseded cited edges or
                    downward-retiered cited chunks. That does not establish that
                    the synthesis remains true.
                  </p>
                </div>
              </section>
            ) : (
              <section className="dws-weather dws-weather--review">
                <span aria-hidden="true">↯</span>
                <div>
                  <p className="dws-kicker">Measured evidence weather</p>
                  <h2>Cited evidence needs review</h2>
                  <p>
                    At least one source relationship or chunk used by the
                    synthesis changed after it was archived. Inspect the rows
                    before grading outcomes.
                  </p>
                </div>
              </section>
            )}
            <section className="dws-zone" aria-labelledby="dws-context">
              <header>
                <p className="dws-kicker">Context only</p>
                <h2 id="dws-context">What changed around it</h2>
                <p>
                  These are global substrate movements since archive time. They
                  are not evidence for or against this synthesis.
                </p>
              </header>
              <div className="dws-signals">
                <Signal
                  label="Edges added"
                  value={report.added_edges_since}
                  note="New relationships entered the wider graph."
                />
                <Signal
                  label="Edges superseded"
                  value={report.superseded_edges_since}
                  note="Relationships changed across the wider graph."
                />
              </div>
            </section>
            <section className="dws-zone" aria-labelledby="dws-load">
              <header>
                <p className="dws-kicker">Load-bearing evidence</p>
                <h2 id="dws-load">What changed beneath it</h2>
                <p>
                  Only evidence the archived synthesis cited appears in this
                  warning layer.
                </p>
              </header>
              <div className="dws-signals">
                <Signal
                  kind="load"
                  label="Cited edges superseded"
                  value={report.cited_edges_now_superseded_count}
                  note="Cited relationships that later closed or were replaced."
                />
                <Signal
                  kind="load"
                  label="Cited chunks demoted"
                  value={report.chunks_retired_downward_count}
                  note="Cited passages whose evidence tier was lowered."
                />
              </div>
            </section>
            <EvidenceSection
              id="dws-edges"
              title="Superseded cited edges"
              description="Relationship changes among the synthesis’s cited evidence."
              reported={report.cited_edges_now_superseded_count}
              items={edges}
            >
              {edges.map((row, i) => (
                <EdgeRow key={text(row.edge_id) ?? i} row={row} />
              ))}
            </EvidenceSection>
            <EvidenceSection
              id="dws-chunks"
              title="Downward-retiered cited chunks"
              description="Evidence-quality changes among passages the synthesis cited."
              reported={report.chunks_retired_downward_count}
              items={chunks}
            >
              {chunks.map((row, i) => (
                <ChunkRow key={text(row.chunk_id) ?? i} row={row} />
              ))}
            </EvidenceSection>
            <EvidenceSection
              id="dws-outcomes"
              title="Human-recorded outcomes"
              description="Observer records are evidence for review, not an automatic confidence score."
              reported={report.outcomes_recorded}
              items={outcomes}
            >
              {outcomes.map((row, i) => (
                <OutcomeRow key={text(row.outcome_id) ?? i} row={row} />
              ))}
            </EvidenceSection>
            <footer className="dws-footer">
              <div>
                <p className="dws-kicker">Next instrument</p>
                <h2>Grade with the evidence in view</h2>
                <p>
                  Outcome grading remains a separate human act. This report does
                  not silently update the archived synthesis.
                </p>
              </div>
              <Link to={`/outcomes/${encodeURIComponent(report.synthesis_id)}`}>
                Open outcome grading <span aria-hidden="true">→</span>
              </Link>
            </footer>
          </>
        ) : null}
      </div>
    </main>
  );
}

export default function Backtest() {
  const { synthesisId = "" } = useParams<{ synthesisId: string }>();
  const [report, setReport] = useState<BacktestReport | null>(null);
  const [state, setState] = useState<BacktestViewProps["state"]>(
    synthesisId ? "loading" : "not-found",
  );
  const request = useRef(0);
  const reload = useCallback(async () => {
    const token = ++request.current;
    if (!synthesisId) {
      setReport(null);
      setState("not-found");
      return;
    }
    setReport(null);
    setState("loading");
    try {
      const response = await apiFetch(
        `/backtest/${encodeURIComponent(synthesisId)}`,
      );
      if (token !== request.current) return;
      if (response.status === 404) {
        setState("not-found");
        return;
      }
      if (!response.ok) throw new Error("backtest unavailable");
      setReport((await response.json()) as BacktestReport);
      setState("ready");
    } catch {
      if (token === request.current) setState("error");
    }
  }, [synthesisId]);
  useEffect(() => {
    void reload();
    return () => {
      request.current += 1;
    };
  }, [reload]);
  return (
    <BacktestView
      synthesisId={synthesisId}
      report={report}
      state={state}
      onRetry={() => void reload()}
    />
  );
}
