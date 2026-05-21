import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { apiFetch } from "../../lib/api";
import HeaderBar from "../shared/HeaderBar";

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
      <HeaderBar />
      <main className="flex-1 overflow-y-auto bg-white">
        <div className="max-w-3xl mx-auto px-8 py-10 space-y-6">
          <header className="space-y-2">
            <Link
              to="/skill-rules"
              className="text-xs font-mono text-stone-500 hover:text-stone-900"
            >
              ← Back to skill rules
            </Link>
            <h1 className="text-2xl font-serif text-stone-900">
              Skill rule detail
            </h1>
            <p className="text-xs font-mono text-stone-500">
              {ruleId ?? "—"}
            </p>
          </header>

          {loading && (
            <p className="text-sm text-stone-500 italic">Loading…</p>
          )}

          {error && (
            <p className="text-sm text-red-700 border border-red-200 bg-red-50 px-3 py-2 rounded">
              {error}
            </p>
          )}

          {rule && (
            <>
              <section className="border border-stone-200 rounded-md p-5 space-y-3">
                <h2 className="text-base font-serif text-stone-900">
                  Rule text
                </h2>
                <p className="text-sm text-stone-800 leading-relaxed">
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

              <section className="text-xs font-mono text-stone-500 leading-relaxed">
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
    <div className="border border-stone-200 rounded-md px-3 py-2">
      <p className="text-[10px] font-mono text-stone-500 uppercase">
        {label}
      </p>
      <p className="text-sm font-mono text-stone-900 truncate">
        {value}
      </p>
    </div>
  );
}
