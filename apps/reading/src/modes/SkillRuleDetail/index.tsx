import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import Werner from "../../brand/Werner";
import environment from "../../brand/werner/skill-rules/skill_rule_conservatory_environment_v1.webp";
import { apiFetch } from "../../lib/api";
import "./skill-rule-specimen.css";

export interface SkillRuleDetailRecord {
  rule_id: string;
  rule_text: string;
  rule_kind: string;
  domain: string;
  epsilon_budget_consumed: number;
  source_user_count: number;
  confidence: string;
  extracted_at: string | null;
}

export type SkillRuleDetailViewProps = {
  ruleId: string;
  rule?: SkillRuleDetailRecord | null;
  state?: "ready" | "loading" | "not-found" | "error";
  onRetry?: () => void;
};

const safeText = (value: unknown) =>
  typeof value === "string" && value.trim() ? value : null;
const safeNumber = (value: unknown) =>
  typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value
    : null;
const isRuleRecord = (value: unknown): value is SkillRuleDetailRecord =>
  Boolean(value) &&
  typeof value === "object" &&
  !Array.isArray(value) &&
  Boolean(safeText((value as Record<string, unknown>).rule_id));

function When({ value }: { value: unknown }) {
  const label = safeText(value);
  if (!label) return <>Time not reported</>;
  const parsed = Date.parse(label);
  if (Number.isNaN(parsed)) return <>Time not reported</>;
  return (
    <time dateTime={label}>
      {new Intl.DateTimeFormat(undefined, {
        dateStyle: "long",
        timeStyle: "short",
      }).format(parsed)}
    </time>
  );
}

function Datum({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

export function SkillRuleDetailView({
  ruleId,
  rule = null,
  state = "ready",
  onRetry,
}: SkillRuleDetailViewProps) {
  const validRule = isRuleRecord(rule) ? rule : null;
  const contributors = safeNumber(validRule?.source_user_count);
  const epsilon = safeNumber(validRule?.epsilon_budget_consumed);
  return (
    <main className="srd-shell">
      <img
        className="srd-environment"
        src={environment}
        alt=""
        aria-hidden="true"
      />
      <div className="srd-veil" aria-hidden="true" />
      <div className="srd-content">
        <Link className="srd-back" to="/skill-rules">
          <span aria-hidden="true">←</span> Skill Rule Conservatory
        </Link>
        <header className="srd-hero">
          <div>
            <p className="srd-eyebrow">Promotion specimen · shared craft</p>
            <h1>Rule under glass</h1>
            <p>
              Inspect the exact practice and the metadata that accompanied its
              promotion. This is an audit view, not a universal-truth
              certificate.
            </p>
            <p className="srd-id">Requested rule · {ruleId || "Unavailable"}</p>
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
            label="Werner inspecting a promoted skill rule"
          />
        </header>
        {state === "loading" ? (
          <section className="srd-state" aria-live="polite">
            <span className="srd-spinner" aria-hidden="true" />
            <h2>Opening the specimen record…</h2>
            <p>Reading the promoted rule and its audit metadata.</p>
          </section>
        ) : null}
        {state === "not-found" ? (
          <section className="srd-state">
            <h2>This promoted rule was not found</h2>
            <p>
              The identifier may be stale or may never have existed in this
              substrate.
            </p>
            <Link to="/skill-rules">Return to promoted rules</Link>
          </section>
        ) : null}
        {state === "error" ? (
          <section className="srd-state" role="alert">
            <h2>The specimen record could not be opened</h2>
            <p>No rule or promotion metadata was inferred.</p>
            {onRetry ? (
              <button type="button" onClick={onRetry}>
                Try again
              </button>
            ) : null}
          </section>
        ) : null}
        {state === "ready" && !validRule ? (
          <section className="srd-state">
            <h2>Rule data is unavailable</h2>
            <p>The response did not contain a usable promoted-rule record.</p>
          </section>
        ) : null}
        {state === "ready" && validRule ? (
          <>
            <article className="srd-rule">
              <p className="srd-eyebrow">Promoted practice</p>
              <h2>
                {safeText(validRule.rule_text) ?? "Rule text unavailable"}
              </h2>
              <div className="srd-labels">
                <span>
                  {safeText(validRule.domain) ?? "Domain not reported"}
                </span>
                <span>
                  {safeText(validRule.rule_kind)?.replaceAll("_", " ") ??
                    "Rule kind not reported"}
                </span>
              </div>
            </article>
            <aside
              className="srd-reading"
              aria-label="How to interpret this promotion record"
            >
              <p className="srd-eyebrow">Reading discipline</p>
              <p>
                <strong>
                  {safeText(validRule.confidence)?.replaceAll("_", " ") ??
                    "Unlabelled"}{" "}
                  is the stored confidence label—not a probability.
                </strong>{" "}
                Contributor count records independent support for promotion.
                Cumulative ε records privacy spend, not rule quality.
              </p>
            </aside>
            <section className="srd-metadata" aria-labelledby="srd-metadata">
              <header>
                <p className="srd-eyebrow">Promotion record</p>
                <h2 id="srd-metadata">Measured metadata</h2>
                <p>
                  Values below come from the shared-substrate row. Missing or
                  malformed values remain explicitly unreported.
                </p>
              </header>
              <dl>
                <Datum label="Stored confidence label">
                  {safeText(validRule.confidence)?.replaceAll("_", " ") ??
                    "Not reported"}
                </Datum>
                <Datum label="Independent contributors">
                  {contributors === null
                    ? "Not reported"
                    : new Intl.NumberFormat().format(contributors)}
                </Datum>
                <Datum label="Cumulative privacy spend">
                  {epsilon === null
                    ? "Not reported"
                    : `ε ${epsilon.toFixed(4)}`}
                </Datum>
                <Datum label="Promoted">
                  <When value={validRule.extracted_at} />
                </Datum>
                <Datum label="Domain">
                  {safeText(validRule.domain) ?? "Not reported"}
                </Datum>
                <Datum label="Rule kind">
                  {safeText(validRule.rule_kind)?.replaceAll("_", " ") ??
                    "Not reported"}
                </Datum>
              </dl>
            </section>
            <section
              className="srd-boundaries"
              aria-labelledby="srd-boundaries"
            >
              <header>
                <p className="srd-eyebrow">Epistemic boundary</p>
                <h2 id="srd-boundaries">
                  What promotion does—and does not—say
                </h2>
              </header>
              <div>
                <article>
                  <h3>It records</h3>
                  <ul>
                    <li>
                      A normalized practice reached the substrate’s promotion
                      gate.
                    </li>
                    <li>
                      Independent support and privacy accounting were stored
                      with it.
                    </li>
                    <li>
                      The rule can inform future work as a reviewable shared
                      heuristic.
                    </li>
                  </ul>
                </article>
                <article>
                  <h3>It does not establish</h3>
                  <ul>
                    <li>
                      That the practice is universally true or optimal in every
                      context.
                    </li>
                    <li>
                      That the confidence label is a calibrated probability.
                    </li>
                    <li>
                      Who contributed, or what their private source material
                      contained.
                    </li>
                  </ul>
                </article>
              </div>
            </section>
            <footer className="srd-footer">
              <div>
                <p className="srd-eyebrow">Content-addressed record</p>
                <p>
                  {safeText(validRule.rule_id) ?? "Identifier not reported"}
                </p>
              </div>
              <Link to="/skill-rules">
                Inspect other promoted rules <span aria-hidden="true">→</span>
              </Link>
            </footer>
          </>
        ) : null}
      </div>
    </main>
  );
}

export default function SkillRuleDetail() {
  const { ruleId = "" } = useParams<{ ruleId: string }>();
  const [rule, setRule] = useState<SkillRuleDetailRecord | null>(null);
  const [state, setState] = useState<SkillRuleDetailViewProps["state"]>(
    ruleId ? "loading" : "not-found",
  );
  const request = useRef(0);
  const reload = useCallback(async () => {
    const token = ++request.current;
    setRule(null);
    if (!ruleId) {
      setState("not-found");
      return;
    }
    setState("loading");
    try {
      const response = await apiFetch(
        `/skill-rules/${encodeURIComponent(ruleId)}`,
      );
      if (token !== request.current) return;
      if (response.status === 404) {
        setState("not-found");
        return;
      }
      if (!response.ok) throw new Error("rule unavailable");
      const body: unknown = await response.json();
      if (token !== request.current) return;
      if (!isRuleRecord(body)) {
        setState("ready");
        return;
      }
      setRule(body);
      setState("ready");
    } catch {
      if (token === request.current) setState("error");
    }
  }, [ruleId]);
  useEffect(() => {
    void reload();
    return () => {
      request.current += 1;
    };
  }, [reload]);
  return (
    <SkillRuleDetailView
      ruleId={ruleId}
      rule={rule}
      state={state}
      onRetry={() => void reload()}
    />
  );
}
