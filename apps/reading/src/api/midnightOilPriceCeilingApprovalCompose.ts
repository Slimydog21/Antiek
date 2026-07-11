/**
 * Midnight Oil price-ceiling recommendation → approval → unattended pack (pure).
 *
 * Operator vision: set time of work and goals; system recommends a price
 * ceiling to approve; after operator approves ceiling (and unattended/spend
 * consents), package is ready for unattended swarm — never live-executes.
 *
 * live_execution_authorized always false.
 * charge_executed always false.
 */

import {
  recommendMidnightOilPriceCeiling,
  type MidnightOilPriceCeilingRecommend,
} from "./midnightOilLaunchPackageCompose";
import {
  composeMidnightOilUnattendedPackage,
  type MidnightOilUnattendedPackageCompose,
  type MoGoalEntry,
} from "./midnightOilUnattendedPackageCompose";

export type { MoGoalEntry };

export type MoPriceCeilingStage =
  | "recommend_only"
  | "approve_ceiling"
  | "unattended_pack";

export interface MidnightOilPriceCeilingApprovalInput {
  operator_id: string;
  work_minutes: number;
  goals: MoGoalEntry[];
  /**
   * Blended USD/hour for recommendation. Null → recommended stays null
   * (never invent $0).
   */
  usd_per_hour?: number | null;
  goal_intensity?: number | null;
  /**
   * Operator-approved ceiling after seeing recommendation.
   * Required for approve_ceiling and unattended_pack stages.
   */
  approved_ceiling_usd?: number | null;
  /**
   * When true, allow approved_ceiling below recommended (explicit override).
   * Fail closed when false and approved < recommended.
   */
  below_recommend_override?: boolean;
  /** Explicit ack that operator reviewed the recommendation. */
  price_ceiling_ack: boolean;
  operator_ack: boolean;
  unattended_ack?: boolean;
  spend_consent?: boolean;
  stage: MoPriceCeilingStage;
}

export interface MidnightOilPriceCeilingApprovalCompose {
  operator_id: string;
  stage: MoPriceCeilingStage;
  recommend: MidnightOilPriceCeilingRecommend;
  approved_ceiling_usd: number | null;
  /**
   * True when approved meets recommendation policy (or override) and
   * price_ceiling_ack. Does not authorize spend.
   */
  ceiling_approved: boolean;
  unattended: MidnightOilUnattendedPackageCompose | null;
  /**
   * True when stage gates pass:
   * - recommend_only: recommendation composed (may be null ceiling)
   * - approve_ceiling: ceiling_approved
   * - unattended_pack: ceiling_approved + unattended.unattended_package_ready
   */
  pack_ready: boolean;
  live_execution_authorized: false;
  charge_executed: false;
  notes: string[];
  authority: "midnight_oil_price_ceiling_approval_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function requirePositiveFinite(value: unknown, name: string): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) {
    throw new Error(`${name} must be a positive finite number`);
  }
  return value;
}

/**
 * Recommend price ceiling → operator approve → optional unattended pack.
 * Never charges; never launches workers.
 */
export function composeMidnightOilPriceCeilingApproval(
  input: MidnightOilPriceCeilingApprovalInput,
): MidnightOilPriceCeilingApprovalCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.price_ceiling_ack !== "boolean") {
    throw new Error("price_ceiling_ack must be an explicit boolean");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (
    input.stage !== "recommend_only" &&
    input.stage !== "approve_ceiling" &&
    input.stage !== "unattended_pack"
  ) {
    throw new Error(
      "stage must be recommend_only|approve_ceiling|unattended_pack",
    );
  }
  const operator_id = requireNonEmpty(input.operator_id, "operator_id");
  const work_minutes = requirePositiveFinite(
    input.work_minutes,
    "work_minutes",
  );
  if (!Array.isArray(input.goals) || input.goals.length === 0) {
    throw new Error("goals must be a non-empty array");
  }

  const notes: string[] = [
    "live_execution_authorized=false — MO never launches from pure pack",
    "charge_executed=false — recommended ceiling is advisory only",
    "system recommends; operator must approve ceiling before unattended pack",
  ];

  const recommend = recommendMidnightOilPriceCeiling({
    work_minutes,
    goal_count: input.goals.length,
    usd_per_hour: input.usd_per_hour,
    goal_intensity: input.goal_intensity,
  });
  notes.push(...recommend.notes.map((n) => `[recommend] ${n}`));

  let approved_ceiling_usd: number | null = null;
  if (
    input.approved_ceiling_usd !== undefined &&
    input.approved_ceiling_usd !== null
  ) {
    if (
      typeof input.approved_ceiling_usd !== "number" ||
      !Number.isFinite(input.approved_ceiling_usd) ||
      input.approved_ceiling_usd < 0
    ) {
      throw new Error(
        "approved_ceiling_usd must be non-negative finite when set",
      );
    }
    approved_ceiling_usd = input.approved_ceiling_usd;
    notes.push(`approved_ceiling_usd=${approved_ceiling_usd}`);
  } else {
    notes.push("approved_ceiling_usd=null — operator has not set a ceiling");
  }

  const override =
    input.below_recommend_override === undefined
      ? false
      : input.below_recommend_override;
  if (typeof override !== "boolean") {
    throw new Error("below_recommend_override must be boolean when set");
  }

  let ceiling_approved = false;
  if (input.stage === "recommend_only") {
    notes.push(
      "stage=recommend_only — show recommended ceiling; no approval required yet",
    );
    ceiling_approved = false;
  } else {
    // approve_ceiling | unattended_pack
    if (!input.price_ceiling_ack) {
      notes.push(
        "ceiling_approved=false — price_ceiling_ack required after reviewing recommendation",
      );
    } else if (approved_ceiling_usd === null) {
      notes.push(
        "ceiling_approved=false — approved_ceiling_usd required to approve",
      );
    } else if (
      recommend.recommended_ceiling_usd !== null &&
      approved_ceiling_usd + 1e-9 < recommend.recommended_ceiling_usd &&
      !override
    ) {
      notes.push(
        `ceiling_approved=false — approved $${approved_ceiling_usd} < recommended $${recommend.recommended_ceiling_usd}; set below_recommend_override=true to force`,
      );
    } else if (!input.operator_ack) {
      notes.push(
        "ceiling_approved=false — operator_ack required with ceiling approval",
      );
    } else {
      ceiling_approved = true;
      if (
        recommend.recommended_ceiling_usd !== null &&
        approved_ceiling_usd + 1e-9 < recommend.recommended_ceiling_usd &&
        override
      ) {
        notes.push(
          "ceiling_approved=true with below_recommend_override (operator accepted lower ceiling)",
        );
      } else {
        notes.push(
          "ceiling_approved=true — operator accepted recommended or higher ceiling",
        );
      }
    }
  }

  let unattended: MidnightOilUnattendedPackageCompose | null = null;
  if (input.stage === "unattended_pack") {
    if (typeof input.unattended_ack !== "boolean") {
      throw new Error(
        "unattended_ack must be an explicit boolean when stage=unattended_pack",
      );
    }
    if (typeof input.spend_consent !== "boolean") {
      throw new Error(
        "spend_consent must be an explicit boolean when stage=unattended_pack",
      );
    }
    if (!ceiling_approved) {
      notes.push(
        "unattended pack deferred — ceiling not approved under policy",
      );
    } else {
      unattended = composeMidnightOilUnattendedPackage({
        operator_id,
        work_minutes,
        goals: input.goals,
        usd_per_hour: input.usd_per_hour,
        approved_ceiling_usd,
        operator_ack: input.operator_ack,
        unattended_ack: input.unattended_ack,
        spend_consent: input.spend_consent,
      });
      notes.push(...unattended.notes.map((n) => `[unattended] ${n}`));
    }
  }

  let pack_ready = false;
  if (input.stage === "recommend_only") {
    pack_ready = true; // recommendation always composable when inputs valid
    notes.push(
      "pack_ready=true — recommendation surface ready (advisory only)",
    );
  } else if (input.stage === "approve_ceiling") {
    pack_ready = ceiling_approved;
    notes.push(
      pack_ready
        ? "pack_ready=true — ceiling approval intent ready; charge_executed=false"
        : "pack_ready=false — ceiling approval gates open",
    );
  } else {
    pack_ready =
      ceiling_approved === true &&
      unattended !== null &&
      unattended.unattended_package_ready === true;
    notes.push(
      pack_ready
        ? "pack_ready=true — ceiling approved + unattended package ready; still no live execution"
        : "pack_ready=false — ceiling or unattended package gates open",
    );
  }

  if (
    unattended != null &&
    unattended.live_execution_authorized !== false
  ) {
    throw new Error("invariant: live_execution_authorized must remain false");
  }

  notes.push("live_execution_authorized=false");
  notes.push("charge_executed=false");

  return {
    operator_id,
    stage: input.stage,
    recommend,
    approved_ceiling_usd,
    ceiling_approved,
    unattended,
    pack_ready,
    live_execution_authorized: false,
    charge_executed: false,
    notes,
    authority: "midnight_oil_price_ceiling_approval_compose_advisory",
  };
}

export function formatMidnightOilPriceCeilingApprovalSummary(
  c: MidnightOilPriceCeilingApprovalCompose,
): string {
  const rec = c.recommend.recommended_ceiling_usd;
  return (
    `pack_ready=${c.pack_ready} · stage=${c.stage} · ` +
    `recommended=${rec === null ? "null" : `$${rec}`} · ` +
    `approved=${c.approved_ceiling_usd === null ? "null" : `$${c.approved_ceiling_usd}`} · ` +
    `ceiling_approved=${c.ceiling_approved} · ` +
    `live_execution_authorized=false · charge_executed=false`
  );
}
