import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { apiFetch } from "../../lib/api";

/**
 * Skill rule detail page (master-spec §13.2 + §13.9).
 *
 * Operator-facing single-rule view; reads the GET /skill-rules/{id}
 * endpoint. Renders the rule's content-addressed identifier, the
 * full provenance metadata (domain, kind, source_user_count,
 * cumulative ε, confidence, extraction time), and a link back to
 * the rules index.
 */

interface SkillRuleDetail {
  rule_id: string;
  rule_text: string;
  rule_kind: string;
  domain: string;
  epsilon_budget_consumed: number;
  source_user_count: number;
  confidence: string;
  extracted_at: string | null;
}

function finiteNonNegativeNumber(value: unknown): number | null {
  const number =
    typeof value === "number"
      ? value
      : typeof value === "string"
        ? Number(value)
        : Number.NaN;
  return Number.isFinite(number) && number >= 0 ? number : null;
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function nonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function nullableString(value: unknown): string | null {
  return value == null ? null : nonEmptyString(value);
}

function safeConfidence(value: unknown): string {
  const confidence = nonEmptyString(value);
  return confidence === "high" || confidence === "moderate" || confidence === "low"
    ? confidence
    : "low";
}

function safeSkillRuleDetail(value: unknown): SkillRuleDetail | null {
  const rule = record(value);
  const ruleId = nonEmptyString(rule?.rule_id);
  const ruleText = nonEmptyString(rule?.rule_text);
  if (!rule || !ruleId || !ruleText) return null;
  return {
    rule_id: ruleId,
    rule_text: ruleText,
    rule_kind: nonEmptyString(rule.rule_kind) ?? "rule",
    domain: nonEmptyString(rule.domain) ?? "general",
    epsilon_budget_consumed:
      finiteNonNegativeNumber(rule.epsilon_budget_consumed) ?? 0,
    source_user_count: finiteNonNegativeNumber(rule.source_user_count) ?? 0,
    confidence: safeConfidence(rule.confidence),
    extracted_at: nullableString(rule.extracted_at),
  };
}

function formatEpsilon(value: unknown): string {
  return (finiteNonNegativeNumber(value) ?? 0).toFixed(4);
}

function formatContributorCount(value: unknown): string {
  return Math.floor(finiteNonNegativeNumber(value) ?? 0).toLocaleString();
}

export default function SkillRuleDetail() {
  const { ruleId } = useParams<{ ruleId: string }>();
  const [rule, setRule] = useState<SkillRuleDetail | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!ruleId) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await apiFetch(
        `/skill-rules/${encodeURIComponent(ruleId)}`,
      );
      if (resp.status === 404) {
        setRule(null);
        setError("Rule not found.");
        return;
      }
      if (!resp.ok) {
        throw new Error(`GET /skill-rules/{id}: HTTP ${resp.status}`);
      }
      setRule(safeSkillRuleDetail(await resp.json()));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [ruleId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return (
    <div className="flex flex-col h-screen">
      <main className="flex-1 overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        <div className="max-w-3xl mx-auto px-8 py-10 space-y-6">
          <header className="space-y-2">
            <Link
              to="/skill-rules"
              className="text-xs font-mono text-shadow-1 dark:text-moonlight hover:text-ink dark:text-bright"
            >
              ← Back to skill rules
            </Link>
            <h1 className="text-2xl font-serif text-ink dark:text-bright">
              Skill rule detail
            </h1>
            <p className="text-xs font-mono text-shadow-1 dark:text-moonlight">
              {ruleId ?? "—"}
            </p>
          </header>

          {loading && (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">Loading…</p>
          )}

          {error && (
            <p className="text-sm text-emperor border border-red-200 bg-red-50 px-3 py-2 rounded">
              {error}
            </p>
          )}

          {rule && (
            <>
              <section className="border border-rule dark:border-charcoal-1 rounded-md p-5 space-y-3">
                <h2 className="text-base font-serif text-ink dark:text-bright">
                  Rule text
                </h2>
                <p className="text-sm text-ink dark:text-bright leading-relaxed">
                  {rule.rule_text}
                </p>
              </section>

              <section className="grid grid-cols-2 gap-3">
                <Metric label="Domain" value={rule.domain} />
                <Metric label="Rule kind" value={rule.rule_kind} />
                <Metric
                  label="Distinct contributors"
                  value={formatContributorCount(rule.source_user_count)}
                />
                <Metric
                  label="Cumulative ε"
                  value={formatEpsilon(rule.epsilon_budget_consumed)}
                />
                <Metric label="Confidence" value={rule.confidence} />
                <Metric
                  label="Extracted at"
                  value={rule.extracted_at ?? "—"}
                />
              </section>

              <section className="text-xs font-mono text-shadow-1 dark:text-moonlight leading-relaxed">
                <p>
                  Per master-spec §13.2: this rule is the substrate's
                  cross-user discovery; no individual contributor's
                  private content is recoverable from this surface
                  (only the rule text + ε accounting + audit
                  metadata).
                </p>
              </section>
            </>
          )}
        </div>
      </main>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-rule dark:border-charcoal-1 rounded-md px-3 py-2">
      <p className="text-[10px] font-mono text-shadow-1 dark:text-moonlight uppercase">
        {label}
      </p>
      <p className="text-sm font-mono text-ink dark:text-bright truncate">
        {value}
      </p>
    </div>
  );
}
