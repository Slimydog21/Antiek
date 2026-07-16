import {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Link } from "react-router-dom";

import Werner from "../../brand/Werner";
import environment from "../../brand/werner/skill-rules/skill_rule_conservatory_environment_v1.webp";
import { apiFetch } from "../../lib/api";
import "./skill-rule-conservatory.css";

export interface SkillRule {
  rule_id: string;
  rule_text: string;
  rule_kind: string;
  domain: string;
  epsilon_budget_consumed: number;
  source_user_count: number;
  confidence: string;
  extracted_at: string | null;
}

export type SkillRuleFilters = {
  query: string;
  domain: string;
  confidence: string;
};
export type SkillRulesViewProps = {
  rules: SkillRule[];
  state?: "ready" | "loading" | "error";
  filters: SkillRuleFilters;
  filtersApplied?: boolean;
  onFiltersChange: (filters: SkillRuleFilters) => void;
  onApply: () => void;
  onClear: () => void;
  onRetry?: () => void;
};

const CONFIDENCE_ORDER = ["high", "moderate", "low"] as const;
const safeNumber = (value: unknown) =>
  typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value
    : null;
const safeText = (value: unknown) =>
  typeof value === "string" && value.trim() ? value : null;
const isSkillRuleRow = (value: unknown): value is SkillRule =>
  Boolean(value) &&
  typeof value === "object" &&
  !Array.isArray(value) &&
  Boolean(safeText((value as Record<string, unknown>).rule_id));

function When({ value }: { value: unknown }) {
  const label = safeText(value);
  if (!label) return <>Time not reported</>;
  const parsed = Date.parse(label);
  return Number.isNaN(parsed) ? (
    <>Time not reported</>
  ) : (
    <time dateTime={label}>
      {new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(
        parsed,
      )}
    </time>
  );
}

function RuleCard({ rule }: { rule: SkillRule }) {
  const contributors = safeNumber(rule.source_user_count);
  const epsilon = safeNumber(rule.epsilon_budget_consumed);
  return (
    <li>
      <Link
        className="src-rule"
        to={`/skill-rules/${encodeURIComponent(rule.rule_id)}`}
      >
        <header>
          <div>
            <p className="src-overline">
              {safeText(rule.domain) ?? "Domain not reported"}
            </p>
            <h3>{safeText(rule.rule_text) ?? "Rule text unavailable"}</h3>
          </div>
          <span
            className={`src-confidence src-confidence--${safeText(rule.confidence) ?? "unknown"}`}
          >
            {safeText(rule.confidence)?.replaceAll("_", " ") ?? "Unlabelled"}
          </span>
        </header>
        <dl>
          <div>
            <dt>Rule kind</dt>
            <dd>
              {safeText(rule.rule_kind)?.replaceAll("_", " ") ?? "Not reported"}
            </dd>
          </div>
          <div>
            <dt>Independent contributors</dt>
            <dd>
              {contributors === null
                ? "Not reported"
                : new Intl.NumberFormat().format(contributors)}
            </dd>
          </div>
          <div>
            <dt>Cumulative privacy spend</dt>
            <dd>
              {epsilon === null ? "Not reported" : `ε ${epsilon.toFixed(4)}`}
            </dd>
          </div>
          <div>
            <dt>Promoted</dt>
            <dd>
              <When value={rule.extracted_at} />
            </dd>
          </div>
        </dl>
        <p className="src-rule__id">
          {safeText(rule.rule_id) ?? "Rule identifier unavailable"}
        </p>
      </Link>
    </li>
  );
}

export function SkillRulesView({
  rules,
  state = "ready",
  filters,
  filtersApplied = false,
  onFiltersChange,
  onApply,
  onClear,
  onRetry,
}: SkillRulesViewProps) {
  const visibleRules = useMemo(() => rules.filter(isSkillRuleRow), [rules]);
  const counts = useMemo(
    () =>
      CONFIDENCE_ORDER.reduce<Record<string, number>>(
        (acc, label) => ({
          ...acc,
          [label]: visibleRules.filter((rule) => rule.confidence === label)
            .length,
        }),
        {},
      ),
    [visibleRules],
  );
  const otherCount =
    visibleRules.length -
    CONFIDENCE_ORDER.reduce((sum, label) => sum + counts[label], 0);
  const apply = (event: FormEvent) => {
    event.preventDefault();
    onApply();
  };
  return (
    <main className="src-shell">
      <img
        className="src-environment"
        src={environment}
        alt=""
        aria-hidden="true"
      />
      <div className="src-veil" aria-hidden="true" />
      <div className="src-content">
        <header className="src-hero">
          <div>
            <p className="src-eyebrow">
              Shared craft · privacy-preserving promotion
            </p>
            <h1>Skill Rule Conservatory</h1>
            <p>
              Inspect practices that independently recurred often enough to
              enter the shared substrate. Rule text and measured promotion
              metadata travel here; contributors’ private source material does
              not.
            </p>
          </div>
          <Werner
            mood={
              state === "loading"
                ? "thinking"
                : state === "error"
                  ? "empty"
                  : "idle"
            }
            size={88}
            label="Werner tending the Skill Rule Conservatory"
          />
        </header>
        <aside className="src-truth" aria-label="How to read this surface">
          <p className="src-overline">Reading discipline</p>
          <p>
            <strong>
              Confidence is the stored promotion label, not a probability.
            </strong>{" "}
            Contributor count records independent support. Cumulative ε records
            privacy spend; it is not a quality score.
          </p>
        </aside>
        <section className="src-summary" aria-labelledby="src-visible">
          <header>
            <div>
              <p className="src-overline">
                Current query · capped at 200 results
              </p>
              <h2 id="src-visible">Visible promoted rules</h2>
            </div>
            <strong>{state === "ready" ? visibleRules.length : "—"}</strong>
          </header>
          <div className="src-counts">
            {CONFIDENCE_ORDER.map((label) => (
              <div key={label}>
                <span>{counts[label] ?? 0}</span>
                <p>{label} label</p>
              </div>
            ))}
            {otherCount > 0 ? (
              <div>
                <span>{otherCount}</span>
                <p>other labels</p>
              </div>
            ) : null}
          </div>
          <p>
            Counts describe only the rows returned by the current server query.
            They are not totals for the whole substrate when filters are active
            or the 200-row cap is reached.
          </p>
        </section>
        <form
          className="src-filter"
          role="search"
          aria-label="Filter promoted rules"
          onSubmit={apply}
        >
          <header>
            <div>
              <p className="src-overline">Specimen finder</p>
              <h2>Find a promoted practice</h2>
            </div>
            {filtersApplied ? (
              <button type="button" className="src-clear" onClick={onClear}>
                Clear filters
              </button>
            ) : null}
          </header>
          <div className="src-filter__grid">
            <label>
              <span>Search rule text</span>
              <input
                value={filters.query}
                onChange={(e) =>
                  onFiltersChange({ ...filters, query: e.target.value })
                }
                placeholder="e.g. triangulate vendor claims"
              />
            </label>
            <label>
              <span>Domain</span>
              <input
                value={filters.domain}
                onChange={(e) =>
                  onFiltersChange({ ...filters, domain: e.target.value })
                }
                placeholder="e.g. semiconductors"
              />
            </label>
            <label>
              <span>Stored confidence label</span>
              <select
                value={filters.confidence}
                onChange={(e) =>
                  onFiltersChange({ ...filters, confidence: e.target.value })
                }
              >
                <option value="">Any label</option>
                <option value="high">High</option>
                <option value="moderate">Moderate</option>
                <option value="low">Low</option>
              </select>
            </label>
            <button type="submit">
              Apply query <span aria-hidden="true">→</span>
            </button>
          </div>
        </form>
        {state === "loading" ? (
          <section className="src-state" aria-live="polite">
            <span className="src-spinner" aria-hidden="true" />
            <h2>Checking the shared substrate…</h2>
            <p>Reading promoted rules and their audit metadata.</p>
          </section>
        ) : null}
        {state === "error" ? (
          <section className="src-state" role="alert">
            <h2>The conservatory could not be opened</h2>
            <p>No rule counts were inferred. Try the read-only query again.</p>
            {onRetry ? (
              <button type="button" onClick={onRetry}>
                Try again
              </button>
            ) : null}
          </section>
        ) : null}
        {state === "ready" && visibleRules.length === 0 ? (
          <section className="src-state">
            <Werner
              mood="empty"
              size={72}
              label="Werner found no matching promoted rules"
            />
            <h2>
              {filtersApplied
                ? "No promoted rules match this query"
                : "No rules have cleared promotion yet"}
            </h2>
            <p>
              {filtersApplied
                ? "Clear or revise the filters. An empty result does not mean the substrate has no promoted rules."
                : "Promotion requires independent contributor support and privacy accounting. Private source material remains partitioned."}
            </p>
          </section>
        ) : null}
        {state === "ready" && visibleRules.length > 0 ? (
          <section className="src-results" aria-labelledby="src-results">
            <header>
              <p className="src-overline">Promoted practice archive</p>
              <h2 id="src-results">Rules in view</h2>
              <p>
                Open a rule for its complete promotion metadata. Long text and
                identifiers remain readable rather than truncated.
              </p>
            </header>
            <ul>
              {visibleRules.map((rule) => (
                <RuleCard key={rule.rule_id} rule={rule} />
              ))}
            </ul>
          </section>
        ) : null}
      </div>
    </main>
  );
}

const EMPTY_FILTERS: SkillRuleFilters = {
  query: "",
  domain: "",
  confidence: "",
};
export default function SkillRules() {
  const [rules, setRules] = useState<SkillRule[]>([]);
  const [state, setState] = useState<"ready" | "loading" | "error">("loading");
  const [draft, setDraft] = useState<SkillRuleFilters>(EMPTY_FILTERS);
  const [applied, setApplied] = useState<SkillRuleFilters>(EMPTY_FILTERS);
  const request = useRef(0);
  const reload = useCallback(async () => {
    const token = ++request.current;
    setState("loading");
    const params = new URLSearchParams({ limit: "200" });
    if (applied.query.trim()) params.set("q", applied.query.trim());
    if (applied.domain.trim()) params.set("domain", applied.domain.trim());
    if (applied.confidence) params.set("confidence", applied.confidence);
    try {
      const response = await apiFetch(`/skill-rules?${params}`);
      if (!response.ok) throw new Error("skill rules unavailable");
      const body = (await response.json()) as { rules?: SkillRule[] };
      if (token !== request.current) return;
      setRules(
        Array.isArray(body.rules) ? body.rules.filter(isSkillRuleRow) : [],
      );
      setState("ready");
    } catch {
      if (token === request.current) {
        setRules([]);
        setState("error");
      }
    }
  }, [applied]);
  useEffect(() => {
    void reload();
    return () => {
      request.current += 1;
    };
  }, [reload]);
  const filtersApplied = Boolean(
    applied.query.trim() || applied.domain.trim() || applied.confidence,
  );
  return (
    <SkillRulesView
      rules={rules}
      state={state}
      filters={draft}
      filtersApplied={filtersApplied}
      onFiltersChange={setDraft}
      onApply={() => setApplied({ ...draft })}
      onClear={() => {
        setDraft(EMPTY_FILTERS);
        setApplied(EMPTY_FILTERS);
      }}
      onRetry={() => void reload()}
    />
  );
}
