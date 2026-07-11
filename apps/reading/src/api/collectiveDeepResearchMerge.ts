/**
 * Collective deep research → written analysis draft intent (pure).
 *
 * Operator vision: after multiple floating/sub-agent deep researches complete,
 * merge them into a written analysis draft (or full authorize with ack).
 *
 * analysis_written always false in pure layer — intent only.
 */

export type AnalysisMergeKind = "draft_analysis" | "full_analysis";

export interface CompletedResearchInstance {
  instance_id: string;
  parent_asset_id: string;
  status: "completed" | "open" | "proposed" | "closed";
  highlight?: string;
  prompt?: string;
  /** Optional operator-supplied findings — never invented. */
  findings?: string[];
}

export interface CollectiveAnalysisIntent {
  kind: AnalysisMergeKind;
  parent_asset_id: string;
  instance_ids: string[];
  findings: string[];
  operator_ack: boolean;
  /** Always false — pure intent does not write analysis asset. */
  analysis_written: false;
  notes: string[];
  authority: "collective_analysis_intent_only";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Propose merging ≥2 completed (or open) floating research instances into a
 * written analysis draft/full intent. Never invents findings; never writes.
 */
export function proposeCollectiveAnalysisMerge(
  instances: CompletedResearchInstance[],
  input: {
    kind: AnalysisMergeKind;
    operator_ack: boolean;
    /** Optional additional operator findings. */
    extra_findings?: string[] | null;
  },
): CollectiveAnalysisIntent {
  if (!Array.isArray(instances) || instances.length < 2) {
    throw new Error("collective analysis requires at least 2 instances");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (input.kind !== "draft_analysis" && input.kind !== "full_analysis") {
    throw new Error("kind must be draft_analysis or full_analysis");
  }
  if (input.kind === "full_analysis" && input.operator_ack !== true) {
    throw new Error("full_analysis requires operator_ack=true (fail closed)");
  }

  const parent = requireNonEmpty(
    instances[0]?.parent_asset_id,
    "instances[0].parent_asset_id",
  );
  const ids: string[] = [];
  const findings: string[] = [];
  const notes: string[] = [];

  for (let i = 0; i < instances.length; i++) {
    const inst = instances[i];
    if (!inst || typeof inst !== "object") {
      throw new Error(`instances[${i}] must be an object`);
    }
    const id = requireNonEmpty(inst.instance_id, `instances[${i}].instance_id`);
    const p = requireNonEmpty(
      inst.parent_asset_id,
      `instances[${i}].parent_asset_id`,
    );
    if (p !== parent) {
      throw new Error("collective analysis requires same parent_asset_id");
    }
    if (
      inst.status !== "completed" &&
      inst.status !== "open" &&
      inst.status !== "proposed"
    ) {
      throw new Error(
        `instances[${i}] status must be proposed|open|completed (not closed)`,
      );
    }
    if (input.kind === "full_analysis" && inst.status !== "completed") {
      throw new Error("full_analysis requires all instances completed");
    }
    ids.push(id);
    if (inst.findings != null) {
      if (!Array.isArray(inst.findings)) {
        throw new Error(`instances[${i}].findings must be string[] when set`);
      }
      for (let j = 0; j < inst.findings.length; j++) {
        const f = inst.findings[j];
        if (typeof f !== "string" || !f.trim()) {
          throw new Error(`instances[${i}].findings[${j}] must be non-empty string`);
        }
        findings.push(f.trim());
      }
    }
  }

  // de-dupe instance ids
  const seen = new Set<string>();
  const unique = ids.filter((id) => {
    if (seen.has(id)) return false;
    seen.add(id);
    return true;
  });
  if (unique.length < 2) {
    throw new Error("collective analysis requires at least 2 distinct instance_ids");
  }

  if (input.extra_findings != null) {
    if (!Array.isArray(input.extra_findings)) {
      throw new Error("extra_findings must be string[] or null");
    }
    for (let j = 0; j < input.extra_findings.length; j++) {
      const f = input.extra_findings[j];
      if (typeof f !== "string" || !f.trim()) {
        throw new Error(`extra_findings[${j}] must be non-empty string`);
      }
      findings.push(f.trim());
    }
  }

  if (findings.length === 0) {
    notes.push(
      "no findings supplied — analysis scaffold intent only (no invent content)",
    );
  } else {
    notes.push(`findings=${findings.length} caller-supplied only`);
  }

  notes.push("analysis_written=false");
  notes.push(
    input.kind === "draft_analysis"
      ? "draft analysis intent — provisional combined document not written"
      : "full analysis intent — parent/analysis asset not mutated in pure layer",
  );

  return {
    kind: input.kind,
    parent_asset_id: parent,
    instance_ids: unique,
    findings,
    operator_ack: input.operator_ack,
    analysis_written: false,
    notes,
    authority: "collective_analysis_intent_only",
  };
}

export function formatCollectiveAnalysisSummary(
  intent: CollectiveAnalysisIntent,
): string {
  return (
    `${intent.kind} · instances=${intent.instance_ids.length} · ` +
    `findings=${intent.findings.length} · analysis_written=false`
  );
}
