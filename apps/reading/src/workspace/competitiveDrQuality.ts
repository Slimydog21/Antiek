/**
 * Competitive deep-research quality pure helpers (residual apw).
 *
 * Extracted from UI panels so world-class DR metrics are hard to vary and
 * importable without panel coupling (parity domainSearchDefaults).
 *
 * - Multi-stage pipeline: plan → gather → synthesize → cite → terminal (ape)
 * - Citation hop pipeline: insights → questions → sources (api)
 * - World-class readiness: multi-stage × hops (apu)
 * - Residual (atj): competitive duration bands by tier (mw · atf/atg foresight)
 *
 * Never invents stages or hops that inputs do not report.
 */

import { RESEARCH_TIER_PROGRESS_POLL_MS } from "../lib/researchTier";

/**
 * Residual (mw/atj): competitive long-horizon duration bands (honest estimates).
 * Not a timer — posture for operator expectations vs OpenAI Deep Research-class
 * multi-minute jobs. Offline-honest; does not invent live ETA.
 */
export type CompetitiveDurationBand = {
  label: string;
  bandMinutes: string;
  pollMs: number;
};

export function competitiveDurationBand(
  tier: "fast" | "deep" | "wrestle" | null,
): CompetitiveDurationBand {
  if (tier === "wrestle") {
    return {
      label: "wrestle long-horizon",
      bandMinutes: "10–30+",
      pollMs: RESEARCH_TIER_PROGRESS_POLL_MS.wrestle,
    };
  }
  if (tier === "fast") {
    return {
      label: "fast distill",
      bandMinutes: "1–3",
      pollMs: RESEARCH_TIER_PROGRESS_POLL_MS.fast,
    };
  }
  // deep default (and null → deep synthesize posture for projection honesty)
  return {
    label: "deep synthesize",
    bandMinutes: "3–10",
    pollMs: RESEARCH_TIER_PROGRESS_POLL_MS.deep,
  };
}

/** Residual (ape): competitive multi-stage deep-research pipeline. */
export const COMPETITIVE_DR_PIPELINE_STAGES = [
  "plan",
  "gather",
  "synthesize",
  "cite",
  "terminal",
] as const;

export type CompetitiveDrPipelineStage =
  (typeof COMPETITIVE_DR_PIPELINE_STAGES)[number];

export type CompetitiveDrStageProgress = {
  stages: readonly CompetitiveDrPipelineStage[];
  completed: CompetitiveDrPipelineStage[];
  current: CompetitiveDrPipelineStage | null;
  completed_count: number;
  total: number;
  coverage_ratio: number;
  is_terminal: boolean;
};

/** Normalize free-form stage labels onto closed competitive pipeline tokens. */
export function normalizeCompetitiveDrStage(
  stage: string | null | undefined,
): CompetitiveDrPipelineStage | null {
  const s = String(stage || "")
    .trim()
    .toLowerCase();
  if (!s) return null;
  if (s === "plan" || s.includes("plan")) return "plan";
  if (s === "gather" || s.includes("gather") || s.includes("search"))
    return "gather";
  if (s === "synthesize" || s.includes("synth") || s.includes("draft"))
    return "synthesize";
  if (s === "cite" || s.includes("cite") || s.includes("citation"))
    return "cite";
  if (
    s === "terminal" ||
    s.includes("complete") ||
    s.includes("done") ||
    s.includes("terminal")
  ) {
    return "terminal";
  }
  return null;
}

/**
 * Residual (ape): derive pipeline completeness from progress events +
 * latest_stage + is_terminal. Does not invent unreported stages.
 */
export function competitiveDrStageProgress(opts: {
  events?: readonly { stage?: string | null }[] | null;
  latest_stage?: string | null;
  is_terminal?: boolean | null;
}): CompetitiveDrStageProgress {
  const seen = new Set<CompetitiveDrPipelineStage>();
  for (const e of opts.events || []) {
    const n = normalizeCompetitiveDrStage(e?.stage);
    if (n) seen.add(n);
  }
  const latest = normalizeCompetitiveDrStage(opts.latest_stage);
  if (latest) seen.add(latest);
  if (opts.is_terminal) seen.add("terminal");

  const completed = COMPETITIVE_DR_PIPELINE_STAGES.filter((s) => seen.has(s));
  const total = COMPETITIVE_DR_PIPELINE_STAGES.length;
  const completed_count = completed.length;
  let current: CompetitiveDrPipelineStage | null = null;
  if (opts.is_terminal || seen.has("terminal")) {
    current = "terminal";
  } else if (latest && latest !== "terminal") {
    current = latest;
  } else if (completed.length > 0) {
    current = completed[completed.length - 1] ?? null;
  }

  return {
    stages: COMPETITIVE_DR_PIPELINE_STAGES,
    completed,
    current,
    completed_count,
    total,
    coverage_ratio: total > 0 ? completed_count / total : 0,
    is_terminal: Boolean(opts.is_terminal) || seen.has("terminal"),
  };
}

/** Residual (api): competitive citation multi-hop pipeline. */
export const CITATION_HOP_PIPELINE_STAGES = [
  "insights",
  "questions",
  "sources",
] as const;

export type CitationHopPipelineStage =
  (typeof CITATION_HOP_PIPELINE_STAGES)[number];

export type CitationHopStageProgress = {
  stages: readonly CitationHopPipelineStage[];
  present: CitationHopPipelineStage[];
  missing: CitationHopPipelineStage[];
  present_count: number;
  total: number;
  coverage_ratio: number;
  chain_complete: boolean;
  insight_count: number;
  question_count: number;
  ref_count: number;
};

function hopStagePresent(
  stage: CitationHopPipelineStage,
  opts: {
    citation_chain?: readonly {
      hop?: string;
      count?: number;
      items?: unknown[];
    }[] | null;
    insight_count?: number;
    question_count?: number;
    ref_count?: number;
  },
): boolean {
  const chain = opts.citation_chain || [];
  const hopRow = chain.find(
    (h) => String(h.hop || "").toLowerCase() === stage,
  );
  if (hopRow) {
    const n =
      typeof hopRow.count === "number" && Number.isFinite(hopRow.count)
        ? hopRow.count
        : (hopRow.items || []).length;
    if (n > 0) return true;
  }
  if (stage === "insights") return (opts.insight_count ?? 0) > 0;
  if (stage === "questions") return (opts.question_count ?? 0) > 0;
  if (stage === "sources") return (opts.ref_count ?? 0) > 0;
  return false;
}

/**
 * Residual (api): derive citation hop pipeline completeness from evidence pack.
 * Does not invent sources or twin content — empty counts stay missing.
 */
export function citationHopStageProgress(opts: {
  citation_chain?: readonly {
    hop?: string;
    count?: number;
    items?: unknown[];
  }[] | null;
  insight_count?: number;
  question_count?: number;
  ref_count?: number;
  chain_complete?: boolean | null;
}): CitationHopStageProgress {
  const insight_count =
    typeof opts.insight_count === "number" && Number.isFinite(opts.insight_count)
      ? opts.insight_count
      : 0;
  const question_count =
    typeof opts.question_count === "number" &&
    Number.isFinite(opts.question_count)
      ? opts.question_count
      : 0;
  const ref_count =
    typeof opts.ref_count === "number" && Number.isFinite(opts.ref_count)
      ? opts.ref_count
      : 0;
  const present = CITATION_HOP_PIPELINE_STAGES.filter((s) =>
    hopStagePresent(s, {
      citation_chain: opts.citation_chain,
      insight_count,
      question_count,
      ref_count,
    }),
  );
  const missing = CITATION_HOP_PIPELINE_STAGES.filter(
    (s) => !present.includes(s),
  );
  const total = CITATION_HOP_PIPELINE_STAGES.length;
  const present_count = present.length;
  const chain_complete =
    opts.chain_complete === true || (insight_count > 0 && ref_count > 0);
  return {
    stages: CITATION_HOP_PIPELINE_STAGES,
    present,
    missing,
    present_count,
    total,
    coverage_ratio: total > 0 ? present_count / total : 0,
    chain_complete,
    insight_count,
    question_count,
    ref_count,
  };
}

/**
 * Residual (apu): world-class DR bar readiness combining multi-stage coverage
 * (ape) with optional citation hop coverage (api). Null hop ratio = unknown.
 */
export type CompetitiveDrWorldClassReadiness = {
  multi_stage_ready: boolean;
  citation_hops_ready: boolean | null;
  stage_coverage_ratio: number;
  hop_coverage_ratio: number | null;
  world_class_bar: "incomplete" | "multi_stage" | "multi_stage_and_hops";
  notes: string[];
};

export function competitiveDrWorldClassReadiness(opts: {
  stage_coverage_ratio?: number | null;
  hop_coverage_ratio?: number | null;
  stage_is_terminal?: boolean | null;
  stage_ready_threshold?: number;
  hop_ready_threshold?: number;
}): CompetitiveDrWorldClassReadiness {
  const stageRatio =
    typeof opts.stage_coverage_ratio === "number" &&
    Number.isFinite(opts.stage_coverage_ratio)
      ? Math.max(0, Math.min(1, opts.stage_coverage_ratio))
      : 0;
  const hopRatio =
    typeof opts.hop_coverage_ratio === "number" &&
    Number.isFinite(opts.hop_coverage_ratio)
      ? Math.max(0, Math.min(1, opts.hop_coverage_ratio))
      : null;
  const stageThresh =
    typeof opts.stage_ready_threshold === "number" &&
    Number.isFinite(opts.stage_ready_threshold)
      ? opts.stage_ready_threshold
      : 0.6;
  const hopThresh =
    typeof opts.hop_ready_threshold === "number" &&
    Number.isFinite(opts.hop_ready_threshold)
      ? opts.hop_ready_threshold
      : 2 / 3;
  const multi_stage_ready =
    stageRatio >= stageThresh || opts.stage_is_terminal === true;
  const citation_hops_ready =
    hopRatio == null ? null : hopRatio >= hopThresh;
  let world_class_bar: CompetitiveDrWorldClassReadiness["world_class_bar"] =
    "incomplete";
  if (multi_stage_ready && citation_hops_ready === true) {
    world_class_bar = "multi_stage_and_hops";
  } else if (multi_stage_ready) {
    world_class_bar = "multi_stage";
  }
  const notes: string[] = [];
  if (!multi_stage_ready) {
    notes.push(
      "multi-stage pipeline incomplete (plan→gather→synthesize→cite→terminal)",
    );
  } else {
    notes.push("multi-stage pipeline ready");
  }
  if (citation_hops_ready === null) {
    notes.push(
      "citation hops unknown on progress surface · open evidence pack (never invent hops)",
    );
  } else if (citation_hops_ready) {
    notes.push("citation hop pipeline ready (insights→questions→sources)");
  } else {
    notes.push("citation hop pipeline incomplete");
  }
  return {
    multi_stage_ready,
    citation_hops_ready,
    stage_coverage_ratio: stageRatio,
    hop_coverage_ratio: hopRatio,
    world_class_bar,
    notes,
  };
}

/**
 * Residual (arm): closed catalog of offline product surfaces that constitute
 * Antiek competitive DR quality (scorecard honesty · never invents live).
 * Live injectors (L1–L7) remain dual-gate deferred — not listed as shipped live.
 */
export const COMPETITIVE_DR_OFFLINE_PRODUCT_SURFACES = [
  "highlight_float_full_path",
  "spawn_merge_draft_into_parent",
  "collective_multi_select_written_analysis",
  "midnight_oil_goals_duration_ceiling",
  "twin_seed_recursive_note_taker",
  // Residual (art): twin substrate readiness (arq–arr).
  "twin_substrate_insights_questions",
  "research_context_evidence_hop_pipeline",
  "multi_stage_progress_pipeline",
  "marketplace_html_free_host",
  // Residual (aru): free host readiness pure helper.
  "marketplace_free_host_readiness",
  // Residual (art): L5 offline receipt readiness (ars).
  "marketplace_l5_receipt_readiness",
  "publication_hydrate_offline_identity",
  // Residual (ash): knowledge-dense attach readiness pure + CTA (asb).
  "publication_attach_readiness",
  "decision_tree_budget_foresight",
  // Residual (ash): manual install model-id gate (asd) · never auto-route.
  "decision_tree_install_model_gate",
  "antiek_bench_recursive_rewrite",
  "notdiamond_advisory_never_router",
  // Residual (ash): readiness→CTA wave (arw–asg) product contracts.
  "readiness_cta_free_host_twin_path_moil",
  "written_analysis_multi_agent_path",
  "highlight_float_full_path_choices",
  // Residual (asr): highlight→DR launch readiness pure helper (asq) on reading hosts.
  "highlight_dr_launch_readiness",
  // Residual (atn): marketplace hosted open pure readiness (atm) seamless HTML port.
  "marketplace_hosted_open_readiness",
  // Residual (atn): multi-minute duration band pure helper (atj) for budget foresight.
  "competitive_duration_band_foresight",
  // Residual (atn): MO deposit HTML open pure readiness (ate).
  "moil_deposit_html_readiness",
  // Residual (atz): intelligent context search open pure readiness (aty).
  "context_search_open_readiness",
  // Residual (atz): publication hydrate open pure readiness (aty · offline-honest).
  "publication_hydrate_open_readiness",
  // Residual (aud): evidence pack open pure readiness (aua · citation-trust).
  "evidence_pack_open_readiness",
  // Residual (aud): research context pack open pure readiness (aub).
  "research_context_pack_open_readiness",
  // Residual (aud): Add model install-path budget bar foresight (auc).
  "add_model_budget_bar_foresight",
] as const;

export type CompetitiveDrOfflineProductSurface =
  (typeof COMPETITIVE_DR_OFFLINE_PRODUCT_SURFACES)[number];

export type CompetitiveDrOfflineSurfaceCatalog = {
  surfaces: readonly CompetitiveDrOfflineProductSurface[];
  count: number;
  live_injectors_deferred: true;
  notdiamond_is_router: false;
  summary: string;
};

/** Honesty catalog for Settings competitive scorecard / FUTURE agents. */
export function competitiveDrOfflineSurfaceCatalog(): CompetitiveDrOfflineSurfaceCatalog {
  return {
    surfaces: COMPETITIVE_DR_OFFLINE_PRODUCT_SURFACES,
    count: COMPETITIVE_DR_OFFLINE_PRODUCT_SURFACES.length,
    live_injectors_deferred: true,
    notdiamond_is_router: false,
    summary: `${COMPETITIVE_DR_OFFLINE_PRODUCT_SURFACES.length} offline product surfaces shipped · live L1–L7 dual-gate deferred · ND never router`,
  };
}
