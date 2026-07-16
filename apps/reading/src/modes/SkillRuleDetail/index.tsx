import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import SessionBrandChrome from "../../brand/SessionBrandChrome";
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
      setRule(await resp.json());
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
          <div className="space-y-2">
            <Link
              to="/skill-rules"
              className="text-xs font-mono text-shadow-1 dark:text-moonlight hover:text-ink dark:text-bright"
            >
              ← Back to skill rules
            </Link>
            <SessionBrandChrome
              testIdPrefix="skill-rule-detail"
              title="Skill rule detail"
            >
              <p className="text-xs font-mono text-shadow-1 dark:text-moonlight">
                {ruleId ?? "—"}
              </p>
            </SessionBrandChrome>
          </div>

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
                  value={`${rule.source_user_count}`}
                />
                <Metric
                  label="Cumulative ε"
                  value={rule.epsilon_budget_consumed.toFixed(4)}
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
