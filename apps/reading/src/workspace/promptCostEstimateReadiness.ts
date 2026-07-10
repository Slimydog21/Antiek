/**
 * Residual (avh): pure prompt-cost Project estimate CTA readiness.
 *
 * Soft budget foresight for any prompt — operator sees projection before burn.
 * Requires finite non-negative input_chars and expected_output_tokens.
 * Never invents $0 when pricing/ledger unknown (API honesty · soft gate).
 *
 * Outside dual-gate pure thrash (ave–avg) · Settings model pure thrash.
 */

export type PromptCostEstimateBlockReason =
  | "ok"
  | "bad_input_chars"
  | "bad_output_tokens";

export type PromptCostEstimateReadiness = {
  input_chars: number;
  expected_output_tokens: number;
  estimate_ready: boolean;
  block_reason: PromptCostEstimateBlockReason;
  soft_budget: true;
  never_invent_zero: true;
  never_auto_route: true;
  summary: string;
  estimate_title: string;
};

/**
 * Project cost CTA readiness from form fields.
 * estimate_ready when both counts are finite numbers ≥ 0.
 */
export function promptCostEstimateReadiness(opts: {
  input_chars?: number | null;
  expected_output_tokens?: number | null;
}): PromptCostEstimateReadiness {
  const input_raw = opts.input_chars;
  const out_raw = opts.expected_output_tokens;
  const input_chars =
    typeof input_raw === "number" && Number.isFinite(input_raw)
      ? input_raw
      : NaN;
  const expected_output_tokens =
    typeof out_raw === "number" && Number.isFinite(out_raw) ? out_raw : NaN;

  let block_reason: PromptCostEstimateBlockReason = "ok";
  if (!Number.isFinite(input_chars) || input_chars < 0) {
    block_reason = "bad_input_chars";
  } else if (
    !Number.isFinite(expected_output_tokens) ||
    expected_output_tokens < 0
  ) {
    block_reason = "bad_output_tokens";
  }

  const estimate_ready = block_reason === "ok";

  let summary: string;
  let estimate_title: string;
  if (estimate_ready) {
    summary = `estimate ready · input_chars=${input_chars} · out_tokens=${expected_output_tokens} · soft budget · never invent $0`;
    estimate_title =
      "Project prompt cost vs daily budget (soft gate · unknown pricing stays unknown · never auto-route)";
  } else if (block_reason === "bad_input_chars") {
    summary = "input chars invalid · enter a non-negative number";
    estimate_title = "Enter valid input character count before projecting cost";
  } else {
    summary = "output tokens invalid · enter a non-negative number";
    estimate_title =
      "Enter valid expected output tokens before projecting cost";
  }

  return {
    input_chars: estimate_ready ? input_chars : Number.isFinite(input_chars) ? input_chars : 0,
    expected_output_tokens: estimate_ready
      ? expected_output_tokens
      : Number.isFinite(expected_output_tokens)
        ? expected_output_tokens
        : 0,
    estimate_ready,
    block_reason,
    soft_budget: true,
    never_invent_zero: true,
    never_auto_route: true,
    summary,
    estimate_title,
  };
}
