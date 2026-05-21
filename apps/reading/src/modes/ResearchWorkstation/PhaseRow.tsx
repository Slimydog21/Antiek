import { useState } from "react";
import type { Event } from "../../generated/types";

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
  const p = event.payload as {
    decomposition?: Array<{
      sub_question: string;
      category?: string;
      evidence_type_required?: string;
    }>;
    keywords?: Array<{ term: string }>;
  };
  const subQs = p.decomposition ?? [];
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
  const p = event.payload as {
    sub_question?: string;
    insufficient_evidence?: boolean;
    supporting_claims?: Array<{
      claim: string;
      evidence_type?: string;
      source_tier_min?: number | null;
      chunk_ids?: string[];
    }>;
    evidentiary_gaps?: Array<{ gap?: string; description?: string }>;
  };
  const claims = p.supporting_claims ?? [];
  const gaps = p.evidentiary_gaps ?? [];
  return (
    <Card>
      <CardHeader
        label={
          p.insufficient_evidence ? "Evidence — insufficient" : "Evidence retrieved"
        }
        detail={`${claims.length} claim${claims.length === 1 ? "" : "s"} · ${gaps.length} gap${gaps.length === 1 ? "" : "s"}`}
      />
      {p.sub_question && (
        <div className="text-xs text-shadow-1 dark:text-moonlight mb-2 font-serif italic">
          For: "{p.sub_question}"
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
                <span className="text-ink dark:text-bright">{c.claim}</span>
                {c.chunk_ids && c.chunk_ids.length > 0 && (
                  <span className="text-[10px] font-mono text-ink-mute dark:text-moonlight ml-1.5">
                    [{c.chunk_ids.length} chunk{c.chunk_ids.length === 1 ? "" : "s"}]
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
              <li key={i}>{g.gap ?? g.description ?? "(empty)"}</li>
            ))}
          </ul>
        </div>
      </div>
    </Card>
  );
}

function ParameterRow({ event }: { event: Event }) {
  const p = event.payload as {
    constraints?: Array<{ strictness?: string }>;
  };
  const cs = p.constraints ?? [];
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
  const p = event.payload as {
    paths?: unknown[];
    mapped_nodes?: unknown[];
  };
  const np = p.paths?.length ?? 0;
  const nn = p.mapped_nodes?.length ?? 0;
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
  const p = event.payload as {
    thesis_summary?: string;
    implicit_recommendation?: string;
  };
  const summary = p.thesis_summary ?? "";
  return (
    <Card highlight>
      <CardHeader
        label="Thesis synthesized"
        detail={p.implicit_recommendation ?? ""}
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
    input_tokens?: number;
    output_tokens?: number;
    cost_usd?: number;
    latency_ms?: number;
  };
  return (
    <div className="text-[11px] font-mono text-ink-mute dark:text-moonlight flex gap-2 flex-wrap">
      <span>→</span>
      <span>{p.target_role}</span>
      <span>·</span>
      <span>{p.provider}/{p.model}</span>
      <span>·</span>
      <span>in={p.input_tokens} out={p.output_tokens}</span>
      <span>·</span>
      <span>${(p.cost_usd ?? 0).toFixed(6)}</span>
      <span>·</span>
      <span>{((p.latency_ms ?? 0) / 1000).toFixed(1)}s</span>
    </div>
  );
}

function SkillPatchRow({ event }: { event: Event }) {
  const p = event.payload as { domains_patched?: string[] };
  const ds = p.domains_patched ?? [];
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

function Card({
  children,
  highlight,
}: {
  children: React.ReactNode;
  highlight?: boolean;
}) {
  return (
    <div
      className={`border rounded-md p-3 ${
        highlight
          ? "border-rule dark:border-charcoal-1 bg-ice-1 dark:bg-charcoal-2"
          : "border-rule dark:border-charcoal-1 bg-ice-0 dark:bg-charcoal-2"
      }`}
    >
      {children}
    </div>
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
