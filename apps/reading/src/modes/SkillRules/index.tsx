import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import SessionBrandChrome from "../../brand/SessionBrandChrome";
import { apiFetch } from "../../lib/api";

/**
 * Shared-substrate skill rules surface (master-spec §13.2 + §13.9).
 *
 * Read-only listing of rules that cleared the cross-user promotion
 * gate (``SkillRuleAccumulator`` → ``skill_writer``). Per master-spec
 * §13.2: rules propagate; underlying private content does not. This
 * surface is the operator's window into the cross-user inference
 * the substrate has accumulated.
 *
 * Filters by domain and confidence; counters at the top summarize the
 * full result set before any filter is applied so the operator can
 * gauge total substrate maturity at a glance.
 */

interface SkillRule {
  rule_id: string;
  rule_text: string;
  rule_kind: string;
  domain: string;
  epsilon_budget_consumed: number;
  source_user_count: number;
  confidence: string;
  extracted_at: string | null;
}

const CONFIDENCE_ORDER = ["high", "moderate", "low"] as const;

export default function SkillRules() {
  const [rules, setRules] = useState<SkillRule[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [domain, setDomain] = useState<string>("");
  const [confidence, setConfidence] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState<string>("");

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (domain.trim()) params.set("domain", domain.trim());
      if (confidence) params.set("confidence", confidence);
      if (searchQuery.trim()) params.set("q", searchQuery.trim());
      params.set("limit", "200");
      const resp = await apiFetch(`/skill-rules?${params.toString()}`);
      if (!resp.ok) {
        throw new Error(`GET /skill-rules failed: HTTP ${resp.status}`);
      }
      const data = await resp.json();
      setRules(data.rules ?? []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [domain, confidence, searchQuery]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const counts = useMemo(() => {
    const acc = { high: 0, moderate: 0, low: 0 } as Record<string, number>;
    for (const r of rules) {
      acc[r.confidence] = (acc[r.confidence] ?? 0) + 1;
    }
    return acc;
  }, [rules]);

  return (
    <div className="flex flex-col h-screen">
      <main className="flex-1 overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        <div className="max-w-4xl mx-auto px-8 py-10 space-y-6">
          <SessionBrandChrome
            testIdPrefix="skill-rules-home"
            title="Shared substrate skill rules"
          >
            <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
              Cross-user discovered rules that cleared the §13.9
              promotion gate. Each rule is content-addressed —
              independent users producing the same rule land in the
              same bucket without coordination. Private content stays
              in its partition; only the rule + ε accounting + audit
              metadata propagate.
            </p>
          </SessionBrandChrome>

          <section className="grid grid-cols-3 gap-3">
            {CONFIDENCE_ORDER.map((c) => (
              <div
                key={c}
                className="border border-rule dark:border-charcoal-1 rounded-md px-4 py-3 text-center"
              >
                <p className="text-2xl font-serif text-ink dark:text-bright">
                  {counts[c] ?? 0}
                </p>
                <p className="text-[10px] font-mono text-shadow-1 dark:text-moonlight uppercase">
                  {c} confidence
                </p>
              </div>
            ))}
          </section>

          <section className="border border-rule dark:border-charcoal-1 rounded-md p-4 space-y-3">
            <h2 className="text-sm font-serif text-ink dark:text-bright">Filter</h2>
            <div className="space-y-1">
              <label className="text-[10px] font-mono uppercase text-shadow-1 dark:text-moonlight">
                Search rule text
              </label>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="case-insensitive substring match…"
                className="w-full text-xs font-mono text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <label className="text-[10px] font-mono uppercase text-shadow-1 dark:text-moonlight">
                  Domain
                </label>
                <input
                  type="text"
                  value={domain}
                  onChange={(e) => setDomain(e.target.value)}
                  placeholder="quantum, defense, …"
                  className="w-full text-xs font-mono text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2"
                />
              </div>
              <div className="space-y-1">
                <label className="text-[10px] font-mono uppercase text-shadow-1 dark:text-moonlight">
                  Confidence
                </label>
                <select
                  value={confidence}
                  onChange={(e) => setConfidence(e.target.value)}
                  className="w-full text-xs font-mono text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2 bg-ice-0 dark:bg-charcoal-2"
                >
                  <option value="">any</option>
                  <option value="high">high</option>
                  <option value="moderate">moderate</option>
                  <option value="low">low</option>
                </select>
              </div>
            </div>
          </section>

          {error && (
            <p className="text-sm text-emperor border border-red-200 bg-red-50 px-3 py-2 rounded">
              {error}
            </p>
          )}

          {loading && (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">Loading…</p>
          )}

          {!loading && rules.length === 0 && (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">
              No promoted rules yet. The accumulator needs at least
              3 distinct contributors before a rule clears the
              §13.9 gate.
            </p>
          )}

          <section className="space-y-3">
            {rules.map((r) => (
              <Link
                key={r.rule_id}
                to={`/skill-rules/${encodeURIComponent(r.rule_id)}`}
                className="block border border-rule dark:border-charcoal-1 rounded-md p-4 space-y-2 hover:bg-ice-1 dark:bg-charcoal-2 transition-colors"
              >
                <div className="flex items-baseline justify-between gap-3">
                  <h3 className="text-sm font-serif text-ink dark:text-bright truncate">
                    {r.rule_text}
                  </h3>
                  <span
                    className={`text-[10px] uppercase tracking-wider font-mono px-2 py-0.5 rounded shrink-0 ${
                      r.confidence === "high"
                        ? "bg-emerald-100 text-emerald-700"
                        : r.confidence === "moderate"
                        ? "bg-ice-3 dark:bg-charcoal-1 text-ink dark:text-bright"
                        : "bg-ice-1 dark:bg-charcoal-2 text-shadow-1 dark:text-moonlight"
                    }`}
                  >
                    {r.confidence}
                  </span>
                </div>
                <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight">
                  {r.domain} · {r.rule_kind} · users={r.source_user_count}
                  {" · "}ε={r.epsilon_budget_consumed.toFixed(4)}
                  {r.extracted_at ? ` · ${r.extracted_at}` : ""}
                </p>
                <p className="text-[10px] font-mono text-ink-mute dark:text-moonlight">
                  {r.rule_id}
                </p>
              </Link>
            ))}
          </section>
        </div>
      </main>
    </div>
  );
}
