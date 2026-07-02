import { useState } from "react";
import LemonCard from "../../components/lemon/LemonCard";
import type { Event } from "../../generated/types";

function finiteNonNegativeNumber(value: unknown): number | null {
  const parsed =
    typeof value === "number"
      ? value
      : typeof value === "string" && value.trim() !== ""
        ? Number(value)
        : Number.NaN;
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function nonNegativeSafeInteger(value: unknown): number | null {
  const parsed = finiteNonNegativeNumber(value);
  return parsed !== null && Number.isSafeInteger(parsed) ? parsed : null;
}

function nonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.flatMap((item) => {
        const trimmed = nonEmptyString(item);
        return trimmed ? [trimmed] : [];
      })
    : [];
}

function recordList(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value)
    ? value.flatMap((item) =>
        item !== null && typeof item === "object"
          ? [item as Record<string, unknown>]
          : [],
      )
    : [];
}

function payloadRecord(event: Event): Record<string, unknown> {
  return event.payload !== null && typeof event.payload === "object"
    ? (event.payload as unknown as Record<string, unknown>)
    : {};
}

/**
 * Renders one trajectory event. Variant-based: each substantive
 * action_type gets a dedicated rendering shape. Noise events
 * (audit.finding_emitted, intermediate phase.enter/exit) are
 * suppressed; the parent TrajectoryView collapses them into
 * rollups instead.
 *
 * Variants implemented in Day 4:
 *   decompose.delivered           — numbered sub-questions list
 *   evidence.retrieve.delivered   — insights + open questions columns
 *   parameter_extract.delivered   — collapsible constraint count
 *   connector.delivered           — collapsible mappings count
 *   synthesize.delivered          — thesis preview + "view full" button
 *   dispatch.call                 — muted one-line cost row (collapsible)
 *   skill.auto_patch_applied      — small footer note
 */
export default function PhaseRow({ event }: { event: Event }) {
  const at = event.action_type;

  if (at === "decompose.delivered") {
    return <DecomposeRow event={event} />;
  }
  if (at === "evidence.retrieve.delivered") {
    return <EvidenceRow event={event} />;
  }
  if (at === "parameter_extract.delivered") {
    return <ParameterRow event={event} />;
  }
  if (at === "connector.delivered") {
    return <ConnectorRow event={event} />;
  }
  if (at === "synthesize.delivered") {
    return <SynthesizeRow event={event} />;
  }
  if (at === "dispatch.call") {
    return <DispatchRow event={event} />;
  }
  if (at === "skill.auto_patch_applied") {
    return <SkillPatchRow event={event} />;
  }
  // Everything else: render a compact one-liner for diagnostic visibility
  // without dominating the feed.
  return <GenericRow event={event} />;
}

// ── Variants ─────────────────────────────────────────────────────────

function DecomposeRow({ event }: { event: Event }) {
  const p = payloadRecord(event);
  const subQs = recordList(p.decomposition).flatMap((item) => {
    const subQuestion = nonEmptyString(item.sub_question);
    return subQuestion
      ? [
          {
            sub_question: subQuestion,
            category: nonEmptyString(item.category),
            evidence_type_required: nonEmptyString(item.evidence_type_required),
          },
        ]
      : [];
  });
  return (
    <Card>
      <CardHeader label="Decomposed" detail={`${subQs.length} sub-question${subQs.length === 1 ? "" : "s"}`} />
      <ol className="list-decimal list-inside space-y-1.5 text-sm text-ink dark:text-bright font-serif">
        {subQs.map((s, i) => (
          <li key={i}>
            <span className="text-ink dark:text-bright">{s.sub_question}</span>{" "}
            {s.category && (
              <span className="text-[10px] font-mono text-ink-mute dark:text-moonlight ml-1">
                · {s.category}
              </span>
            )}
            {s.evidence_type_required && (
              <span className="text-[10px] font-mono text-ink-mute dark:text-moonlight ml-1">
                · need: {s.evidence_type_required}
              </span>
            )}
          </li>
        ))}
      </ol>
    </Card>
  );
}

function EvidenceRow({ event }: { event: Event }) {
  const p = payloadRecord(event);
  const claims = recordList(p.supporting_claims).flatMap((item) => {
    const claim = nonEmptyString(item.claim);
    const sourceIds = stringList(item.chunk_ids);
    if (!claim) return [];
    const entry = { text: claim, sourceIds };
    return [entry];
  });
  const gaps = recordList(p.evidentiary_gaps).map(
    (item) =>
      nonEmptyString(item.gap) ??
      nonEmptyString(item.description) ??
      "(empty)",
  );
  const subQuestion = nonEmptyString(p.sub_question);
  return (
    <Card>
      <CardHeader
        label={
          p.insufficient_evidence === true
            ? "Evidence — insufficient"
            : "Evidence retrieved"
        }
        detail={`${claims.length} claim${claims.length === 1 ? "" : "s"} · ${gaps.length} gap${gaps.length === 1 ? "" : "s"}`}
      />
      {subQuestion && (
        <div className="text-xs text-shadow-1 dark:text-moonlight mb-2 font-serif italic">
          For: "{subQuestion}"
        </div>
      )}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <div className="text-[10px] font-mono uppercase text-emerald-700 mb-1">
            insights ({claims.length})
          </div>
          <ul className="space-y-1.5 text-sm text-ink dark:text-bright font-serif">
            {claims.length === 0 && (
              <li className="text-ink-mute dark:text-moonlight italic">(none)</li>
            )}
            {claims.map((c, i) => (
              <li key={i}>
                <span className="text-ink dark:text-bright">{c.text}</span>
                {c.sourceIds.length > 0 && (
                  <span className="text-[10px] font-mono text-ink-mute dark:text-moonlight ml-1.5">
                    [{c.sourceIds.length} source{c.sourceIds.length === 1 ? "" : "s"}]
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <div className="text-[10px] font-mono uppercase text-sun-deep dark:text-sun mb-1">
            open questions ({gaps.length})
          </div>
          <ul className="space-y-1.5 text-sm text-ink dark:text-bright font-serif">
            {gaps.length === 0 && (
              <li className="text-ink-mute dark:text-moonlight italic">(none)</li>
            )}
            {gaps.map((g, i) => (
              <li key={i}>{g}</li>
            ))}
          </ul>
        </div>
      </div>
    </Card>
  );
}

function ParameterRow({ event }: { event: Event }) {
  const p = payloadRecord(event);
  const cs = recordList(p.constraints);
  const hard = cs.filter((c) => c.strictness === "hard").length;
  const soft = cs.filter((c) => c.strictness === "soft").length;
  return (
    <Card>
      <CardHeader
        label="Parameters extracted"
        detail={`${cs.length} constraints (${hard} hard · ${soft} soft)`}
      />
    </Card>
  );
}

function ConnectorRow({ event }: { event: Event }) {
  const p = payloadRecord(event);
  const np = Array.isArray(p.paths) ? p.paths.length : 0;
  const nn = Array.isArray(p.mapped_nodes) ? p.mapped_nodes.length : 0;
  return (
    <Card>
      <CardHeader
        label="Cross-domain mappings"
        detail={`${np} path${np === 1 ? "" : "s"} · ${nn} node${nn === 1 ? "" : "s"}`}
      />
    </Card>
  );
}

function SynthesizeRow({ event }: { event: Event }) {
  const p = payloadRecord(event);
  const summary = nonEmptyString(p.thesis_summary) ?? "";
  const recommendation = nonEmptyString(p.implicit_recommendation) ?? "";
  return (
    <Card highlight>
      <CardHeader
        label="Thesis synthesized"
        detail={recommendation}
      />
      <p className="text-sm text-ink dark:text-bright leading-relaxed font-serif">
        {summary.length > 280 ? summary.slice(0, 280) + "…" : summary}
      </p>
      {summary.length > 280 && (
        <div className="text-xs text-shadow-1 dark:text-moonlight mt-2 italic font-serif">
          Full thesis renders below when investigation completes.
        </div>
      )}
    </Card>
  );
}

function DispatchRow({ event }: { event: Event }) {
  const p = event.payload as {
    provider?: string;
    model?: string;
    target_role?: string;
    input_tokens?: unknown;
    output_tokens?: unknown;
    cost_usd?: unknown;
    latency_ms?: unknown;
  };
  const inputTokens = nonNegativeSafeInteger(p.input_tokens);
  const outputTokens = nonNegativeSafeInteger(p.output_tokens);
  const costUsd = finiteNonNegativeNumber(p.cost_usd) ?? 0;
  const latencyMs = finiteNonNegativeNumber(p.latency_ms) ?? 0;
  const targetRole = nonEmptyString(p.target_role) ?? "role?";
  const provider = nonEmptyString(p.provider) ?? "provider?";
  const model = nonEmptyString(p.model) ?? "model?";
  return (
    <div className="text-[11px] font-mono text-ink-mute dark:text-moonlight flex gap-2 flex-wrap">
      <span>→</span>
      <span>{targetRole}</span>
      <span>·</span>
      <span>{provider}/{model}</span>
      <span>·</span>
      <span>in={inputTokens ?? "?"} out={outputTokens ?? "?"}</span>
      <span>·</span>
      <span>${costUsd.toFixed(6)}</span>
      <span>·</span>
      <span>{(latencyMs / 1000).toFixed(1)}s</span>
    </div>
  );
}

function SkillPatchRow({ event }: { event: Event }) {
  const p = payloadRecord(event);
  const ds = stringList(p.domains_patched);
  return (
    <div className="text-[11px] font-mono text-shadow-1 dark:text-moonlight italic">
      ✦ Phase 8: patched {ds.length === 0 ? "no" : ds.length} domain skill
      {ds.length === 1 ? "" : "s"}
      {ds.length > 0 && ` (${ds.join(", ")})`}
    </div>
  );
}

function GenericRow({ event }: { event: Event }) {
  return (
    <div className="text-[10px] font-mono text-ink-mute dark:text-moonlight truncate">
      · {event.action_type}
    </div>
  );
}

// ── Shared chrome ────────────────────────────────────────────────────

/**
 * Phase card. S10 acceptance: PhaseRow renders as LemonCard with
 * elevation z1 and a yellow accent on the "highlight" variant (used
 * for the active phase). The Card wrapper here is a thin adapter so
 * every PhaseRow variant doesn't need to import LemonCard directly.
 */
function Card({
  children,
  highlight,
}: {
  children: React.ReactNode;
  highlight?: boolean;
}) {
  return (
    <LemonCard
      elevation="z1"
      colour={highlight ? "sun" : "card"}
      className="p-3"
    >
      {children}
    </LemonCard>
  );
}

function CardHeader({ label, detail }: { label: string; detail?: string }) {
  return (
    <div className="flex items-baseline justify-between mb-2">
      <div className="text-xs font-semibold text-ink dark:text-bright">{label}</div>
      {detail && (
        <div className="text-[10px] font-mono text-shadow-1 dark:text-moonlight">{detail}</div>
      )}
    </div>
  );
}

export function useCollapsed(defaultCollapsed = true) {
  return useState(defaultCollapsed);
}
