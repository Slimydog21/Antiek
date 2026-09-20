import { useCallback, useEffect, useState } from "react";

import type {
  DispatchTierView,
  ObjectiveCardResponse,
  RawDispatchTier,
} from "../../api/ownYourMind";
import { getObjectiveCard } from "../../api/ownYourMind";
import { useServedImpression } from "../../lib/servedImpression";
import { LemonCard } from "../../components/lemon/LemonCard";
import { LemonTable } from "../../components/lemon/LemonTable";
import { LemonTag } from "../../components/lemon/LemonTag";

/**
 * ObjectiveCard — read-only rendering of the live objective (Own Your Mind
 * P0, C1a).
 *
 * Route: /objective. Fetches GET /ops/objective-card (assembled server-side
 * from live config — substrate/dispatch/config.yaml, continuous/scoring.py +
 * daemon.py, retrieval_gate.py, quality_gate/checks.py, budget modules,
 * flywheel/reuse_gate.py) and renders each surface as a structured card:
 * dispatch tier matrix, gap-scoring equation with its constants, retrieval
 * gates, quality thresholds, budgets, reuse gate.
 *
 * The footer is a binding honesty line: the objective is read-only here;
 * weights are operator-owned until P1 user settings ship.
 */

/** Walk the nested fallback chain into "provider/model → provider/model". */
function fallbackChain(tier: DispatchTierView | RawDispatchTier | null): string | null {
  if (!tier) return null;
  const parts: string[] = [];
  let current: DispatchTierView | RawDispatchTier | null = tier;
  while (current) {
    parts.push(`${current.provider ?? "?"}/${current.model ?? "?"}`);
    current = current.fallback;
  }
  return parts.join(" → ");
}

function SectionHeader({ children }: { children: string }) {
  return (
    <div className="font-mono text-[11px] uppercase tracking-wider text-shadow-1 dark:text-moonlight">
      {children}
    </div>
  );
}

function ConstantRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-rule dark:border-charcoal-1 last:border-b-0 py-1.5 text-sm">
      <span className="text-ink-soft dark:text-starlight">{label}</span>
      <span className="font-mono text-ink dark:text-bright">{value}</span>
    </div>
  );
}

function DispatchSection({ dispatch }: { dispatch: ObjectiveCardResponse["dispatch"] }) {
  const roles = Object.entries(dispatch.role_tiers ?? {});
  const tierEntries = Object.entries(dispatch.tiers ?? {});
  const defaults = dispatch.tier_defaults ?? {};
  return (
    <LemonCard title="Dispatch tier matrix">
      <div className="space-y-4">
        <p className="text-xs font-mono text-ink-mute dark:text-moonlight">
          {dispatch.source}
          {dispatch.version ? ` · config version ${dispatch.version}` : ""}
        </p>
        <div>
          <SectionHeader>Role → tier</SectionHeader>
          {roles.length === 0 ? (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">No role mappings reported.</p>
          ) : (
            <div className="mt-1.5">
              <LemonTable<{ role: string; tier: string }>
                rows={roles.map(([role, tier]) => ({ role, tier }))}
                columns={[
                  { key: "role", header: "Role", render: (r) => <span className="font-mono text-xs">{r.role}</span> },
                  { key: "tier", header: "Tier", render: (r) => <LemonTag colour="sun">{r.tier}</LemonTag> },
                ]}
                rowKey={(r) => r.role}
                dense
              />
            </div>
          )}
        </div>
        <div>
          <SectionHeader>Tier definitions (provider → model → fallback chain)</SectionHeader>
          {tierEntries.length === 0 ? (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">No tier definitions reported.</p>
          ) : (
            <div className="mt-1.5">
              <LemonTable<DispatchTierView>
                rows={tierEntries.map(([name, tier]) => ({ name, ...tier }))}

                columns={[
                  { key: "name", header: "Tier", render: (t) => <span className="font-mono text-xs">{t.name}</span> },
                  { key: "provider", header: "Provider", render: (t) => <span className="font-mono text-xs">{t.provider ?? "—"}</span> },
                  { key: "model", header: "Model", render: (t) => <span className="font-mono text-xs">{t.model ?? "—"}</span> },
                  {
                    key: "fallback",
                    header: "Fallback chain",
                    render: (t) => (
                      <span className="font-mono text-[11px] text-ink-soft dark:text-starlight">
                        {fallbackChain(t) ?? "—"}
                      </span>
                    ),
                  },
                  {
                    key: "pricing",
                    header: "$/mtok in/out",
                    render: (t) =>
                      t.pricing ? (
                        <span className="font-mono text-[11px]">
                          {t.pricing.input_per_mtok} / {t.pricing.output_per_mtok}
                        </span>
                      ) : (
                        "—"
                      ),
                  },
                ]}
                rowKey={(t) => t.name}
                dense
              />
            </div>
          )}
          {dispatch.pricing_placeholder && (
            <p className="mt-2 text-xs text-shadow-1 dark:text-moonlight italic">
              {dispatch.pricing_note}
            </p>
          )}
        </div>
        <div>
          <SectionHeader>Tier defaults</SectionHeader>
          {Object.keys(defaults).length === 0 ? (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">No tier defaults reported.</p>
          ) : (
            <div className="mt-1.5 space-y-2">
              {Object.entries(defaults).map(([tier, vals]) => (
                <div key={tier} className="text-xs space-y-0.5">
                  <span className="font-mono text-ink dark:text-bright uppercase">{tier}</span>
                  <div className="pl-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    {Object.entries(vals ?? {})
                      .map(([k, v]) => `${k}=${v}`)
                      .join(" · ")}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </LemonCard>
  );
}

function GapScoringSection({ section }: { section: ObjectiveCardResponse["gap_scoring"] }) {
  const rows = Object.entries(section.constants ?? {}).map(([k, v]) => ({
    label: k,
    value: v,
  }));
  const spawn = section.daemon_spawn_params ?? {};
  return (
    <LemonCard title="Gap scoring (continuous daemon)">
      <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
        <code className="font-mono text-ink dark:text-bright">{section.objective}</code>
      </p>
      <div className="mt-3">
        {rows.map((r) => (
          <ConstantRow key={r.label} label={r.label} value={r.value} />
        ))}
      </div>
      {Object.keys(spawn).length > 0 && (
        <div className="mt-4">
          <SectionHeader>Spawn parameters</SectionHeader>
          <div className="mt-1">
            {Object.entries(spawn).map(([k, v]) => (
              <ConstantRow key={k} label={k} value={String(v)} />
            ))}
          </div>
        </div>
      )}
    </LemonCard>
  );
}

function RetrievalGatesSection({ gates }: { gates: ObjectiveCardResponse["retrieval_gates"] }) {
  const lists: Array<{ label: string; values: string[] }> = [
    { label: "Privileged policy tags (bypass rights withholding)", values: gates.privileged_policy_tags ?? [] },
    { label: "Restricted content classes (gated-but-public)", values: gates.restricted_content_classes ?? [] },
    { label: "Owner-only content classes (never non-privileged)", values: gates.personal_only_content_classes ?? [] },
    { label: "Excluded on non-privileged retrieval", values: gates.non_privileged_excluded_content_classes ?? [] },
  ];
  return (
    <LemonCard title="Retrieval gates">
      <div className="space-y-3 text-sm">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-mono text-ink dark:text-bright">Policy</span>
          <LemonTag colour="danger">{gates.policy ?? "deny_by_default"}</LemonTag>
        </div>
        {lists.map((l) => (
          <div key={l.label} className="space-y-1">
            <SectionHeader>{l.label}</SectionHeader>
            {l.values.length === 0 ? (
              <p className="text-sm text-shadow-1 dark:text-moonlight italic">None.</p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {l.values.map((v) => (
                  <LemonTag key={v} colour="muted">{v}</LemonTag>
                ))}
              </div>
            )}
          </div>
        ))}
        {gates.note && (
          <p className="text-xs text-ink-soft dark:text-starlight italic">{gates.note}</p>
        )}
      </div>
    </LemonCard>
  );
}

function QualityGateSection({ gate }: { gate: ObjectiveCardResponse["quality_gate"] }) {
  const checks = gate.checks ?? {};
  return (
    <LemonCard title="Quality-gate thresholds">
      <div className="space-y-3 text-sm">
        {checks.voice_style && (
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-ink dark:text-bright">voice_style</span>
            <LemonTag colour="sun">threshold {checks.voice_style.threshold}</LemonTag>
          </div>
        )}
        {checks.source_tier && (
          <div className="space-y-0.5">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono text-ink dark:text-bright">source_tier</span>
              <LemonTag colour="sun">
                {checks.source_tier.min_acceptable}–{checks.source_tier.max_acceptable}
              </LemonTag>
            </div>
            {checks.source_tier.note && (
              <p className="text-xs text-ink-soft dark:text-starlight">{checks.source_tier.note}</p>
            )}
          </div>
        )}
        {checks.extraction_quality && (
          <div className="space-y-0.5">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono text-ink dark:text-bright">extraction_quality</span>
              <LemonTag colour="sun">
                ≥ {checks.extraction_quality.min_distinct_chars} distinct chars
              </LemonTag>
            </div>
            {checks.extraction_quality.note && (
              <p className="text-xs text-ink-soft dark:text-starlight">{checks.extraction_quality.note}</p>
            )}
          </div>
        )}
        {checks.verification?.rule && (
          <p className="text-xs text-ink-soft dark:text-starlight">{checks.verification.rule}</p>
        )}
        {gate.source && (
          <p className="text-[10px] font-mono text-ink-mute dark:text-moonlight">{gate.source}</p>
        )}
      </div>
    </LemonCard>
  );
}

function BudgetsSection({ budgets }: { budgets: ObjectiveCardResponse["budgets"] }) {
  const runner = budgets.research_runner ?? null;
  const daemon = budgets.continuous_daemon ?? null;
  return (
    <LemonCard title="Budget caps">
      <div className="space-y-4 text-sm">
        {runner && (
          <div className="space-y-0.5">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono text-ink dark:text-bright">research_runner aggregate</span>
              <LemonTag colour="sun">${runner.aggregate_cap_usd}</LemonTag>
            </div>
            <p className="text-xs text-ink-soft dark:text-starlight">{runner.scope}</p>
          </div>
        )}
        {daemon && (
          <div className="space-y-1">
            <SectionHeader>Continuous daemon</SectionHeader>
            <ConstantRow label="per_investigation_cap_usd" value={daemon.per_investigation_cap_usd} />
            <ConstantRow label="default_daily_cap_usd" value={daemon.default_daily_cap_usd} />
            <ConstantRow label="max_topic_depth" value={daemon.max_topic_depth} />
            <p className="text-xs font-mono text-ink-mute dark:text-moonlight">
              env override {daemon.daily_cap_env_override} · {daemon.scope}
            </p>
          </div>
        )}
      </div>
    </LemonCard>
  );
}

function ReuseGateSection({ reuse }: { reuse: ObjectiveCardResponse["reuse_gate"] }) {
  return (
    <LemonCard title="Reuse gate">
      <div className="space-y-2 text-sm">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-mono text-ink dark:text-bright">groundedness_threshold</span>
          <LemonTag colour="sun">{reuse.groundedness_threshold}</LemonTag>
          {reuse.env_override && (
            <span className="text-[10px] font-mono text-ink-mute dark:text-moonlight">
              env override {reuse.env_override}
            </span>
          )}
        </div>
        {reuse.rule && (
          <p className="text-xs text-ink-soft dark:text-starlight">{reuse.rule}</p>
        )}
      </div>
    </LemonCard>
  );
}

export function ObjectiveCard() {
  const [data, setData] = useState<ObjectiveCardResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // P0 §5: audit-only served-impression record.
  useServedImpression({ surface: "objective-card", itemKind: "surface", itemId: "/objective" });

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getObjectiveCard());
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
        <div className="max-w-4xl mx-auto px-8 py-10 space-y-6">
          <header className="space-y-2">
            <h1 className="text-2xl font-serif text-ink dark:text-bright">
              Objective card
            </h1>
            <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
              The live objective the substrate is tuned to — dispatch tiers,
              gap scoring, retrieval gates, quality thresholds, budgets, and
              the reuse gate — rendered read-only from GET /ops/objective-card.
              Every value below comes from the running config, never from
              this page.
            </p>
            {data?.generated_at && (
              <p className="text-[10px] font-mono text-ink-mute dark:text-moonlight">
                generated {new Date(data.generated_at).toLocaleString()}
              </p>
            )}
          </header>

          {error && (
            <p className="text-sm text-emperor border border-red-200 bg-red-50 px-3 py-2 rounded">
              {error}
            </p>
          )}

          {loading && (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">Loading…</p>
          )}

          {data && (
            <>
              <DispatchSection dispatch={data.dispatch} />
              <GapScoringSection section={data.gap_scoring} />
              <RetrievalGatesSection gates={data.retrieval_gates} />
              <QualityGateSection gate={data.quality_gate} />
              <BudgetsSection budgets={data.budgets} />
              <ReuseGateSection reuse={data.reuse_gate} />
            </>
          )}

          <footer className="text-xs text-shadow-1 dark:text-moonlight italic border-t border-rule dark:border-charcoal-1 pt-3">
            Read-only rendering of the live objective; weights are
            operator-owned until P1 user settings ship.
          </footer>
        </div>
      </main>
    </div>
  );
}

export default ObjectiveCard;
