/**
 * Midnight Oil — pure preflight / operator-consent policy (reading UI).
 *
 * Spec: `.infinite/sprint-briefs/midnight-oil-execution-control-plane.md`
 *
 * This layer is intentionally **no-spend**:
 *   - recommends a USD-cent ceiling from goals + duration
 *   - requires explicit operator ack before an approval *request* is formed
 *   - never launches work, never commits holds, never claims analysis_written
 *
 * Authority for spend remains on the authenticated server (ResearchSpendLedger).
 */

export type MidnightOilGoal = {
  id: string;
  text: string;
};

export type MidnightOilPreflightInput = {
  goals: MidnightOilGoal[];
  /** Work window length in minutes (operator-set). */
  durationMinutes: number;
  /** Optional operator override for ceiling (cents). */
  ceilingOverrideCents?: number | null;
};

export type MidnightOilPreflightReject =
  | { ok: false; reason: "need_goals" }
  | { ok: false; reason: "duration_out_of_range" }
  | { ok: false; reason: "ceiling_invalid" };

export type MidnightOilPreflightPlan = {
  ok: true;
  goals: MidnightOilGoal[];
  durationMinutes: number;
  /** Recommended ceiling in integer USD cents. */
  recommendedCeilingCents: number;
  /** Effective ceiling after optional override (still advisory until server). */
  ceilingCents: number;
  /** Human-readable rationale (no fabricated receipts). */
  rationale: string;
  authority: "preflight_advisory";
  /** Always false — this plan does not authorize spend. */
  spend_authorized: false;
};

export type MidnightOilPreflightResult =
  | MidnightOilPreflightPlan
  | MidnightOilPreflightReject;

export type MidnightOilApprovalRequest = {
  ok: true;
  plan: MidnightOilPreflightPlan;
  operatorAck: true;
  requestedAt: string;
  /** Server must still mint approval_id — client cannot assert authority. */
  authority: "operator_request_only";
};

const MIN_MINUTES = 15;
const MAX_MINUTES = 12 * 60;

/**
 * Rough heuristic for a recommended ceiling:
 *   base 50¢ + 25¢ per goal + 2¢ per minute, capped at $50.00 demo.
 * Live rates come from server cost_projection — this is UI guidance only.
 */
export function recommendCeilingCents(
  goalCount: number,
  durationMinutes: number,
): number {
  const raw = 50 + goalCount * 25 + durationMinutes * 2;
  return Math.min(5000, Math.max(50, Math.round(raw)));
}

export function buildMidnightOilPreflight(
  input: MidnightOilPreflightInput,
): MidnightOilPreflightResult {
  const goals = input.goals
    .map((g) => ({ id: g.id, text: g.text.trim() }))
    .filter((g) => g.text.length > 0);
  if (goals.length === 0) return { ok: false, reason: "need_goals" };

  const durationMinutes = input.durationMinutes;
  if (
    !Number.isFinite(durationMinutes) ||
    durationMinutes < MIN_MINUTES ||
    durationMinutes > MAX_MINUTES
  ) {
    return { ok: false, reason: "duration_out_of_range" };
  }

  const recommendedCeilingCents = recommendCeilingCents(
    goals.length,
    durationMinutes,
  );
  const override = input.ceilingOverrideCents;
  let ceilingCents = recommendedCeilingCents;
  if (override != null) {
    if (!Number.isInteger(override) || override <= 0) {
      return { ok: false, reason: "ceiling_invalid" };
    }
    ceilingCents = override;
  }

  return {
    ok: true,
    goals,
    durationMinutes,
    recommendedCeilingCents,
    ceilingCents,
    rationale: `Advisory ceiling for ${goals.length} goal(s) over ${durationMinutes}m. Server ResearchSpendLedger is the only spend authority.`,
    authority: "preflight_advisory",
    spend_authorized: false,
  };
}

export function requestMidnightOilApproval(
  plan: MidnightOilPreflightResult,
  operatorAck: boolean,
  now: () => Date = () => new Date(),
): MidnightOilApprovalRequest | { ok: false; reason: string } {
  if (!plan.ok) return { ok: false, reason: plan.reason };
  if (!operatorAck) return { ok: false, reason: "operator_ack_required" };
  return {
    ok: true,
    plan,
    operatorAck: true,
    requestedAt: now().toISOString(),
    authority: "operator_request_only",
  };
}
