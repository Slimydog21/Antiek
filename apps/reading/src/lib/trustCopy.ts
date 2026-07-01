export const EPSILON_CAP = 10;

const BUDGET_LABELS: Record<string, string> = {
  skill_invocation_frequency: "Skill Use Frequency",
  source_tier_preference_signals: "Source Preference Signals",
  query_content_telemetry: "Search Content Telemetry",
};

const SYSTEM_CONTROL_LABELS: Record<string, string> = {
  "encryption at rest (per-graph keys via KMS)":
    "Encryption at rest with managed keys",
  "access logging (append-only)": "Append-only access logs",
  "change management (CI gates on schema)":
    "Database changes pass automated checks",
  "vulnerability scanning (Dependabot/Snyk)":
    "Dependency and vulnerability scanning",
  "backup testing (quarterly restore drill)": "Quarterly backup restore tests",
  "retrieval-time policy_tag gating (§9.0)":
    "Access checks run before retrieved content is shown",
};

const COMPLIANCE_LABELS: Record<string, string> = {
  "GDPR Article 13/14 transparency": "GDPR transparency notice",
  "CCPA notice + opt-out": "CCPA notice and opt-out",
  "engineering-grade differential privacy (ε ≤ 10 hard cap)":
    "Differential privacy with epsilon capped at 10",
  "SOC 2 Type II — deferred (not required for consumer Phase 1)":
    "SOC 2 Type II is not required for the consumer preview",
};

const TRAINING_CRITERION_LABELS: Record<string, string> = {
  trajectory_volume: "Enough approved activity",
  sft_readiness: "Training data quality review",
  validated_reward: "Reward checks validated",
  open_weight_justification: "Open model release justification",
  eval_headroom: "Evaluation safety margin",
};

const BUDGET_DESCRIPTIONS: Record<string, string> = {
  skill_invocation_frequency:
    "How often privacy-preserving tools are used, reported only as a noisy aggregate.",
  source_tier_preference_signals:
    "Which source quality tiers you opt into, prefer, or reject, aggregated with privacy noise.",
  query_content_telemetry:
    "Search text and private note content are not collected for this purpose.",
};

export type PrivacySensitivity = "low" | "medium" | "high" | "forbidden";

const BUDGET_SENSITIVITY: Record<string, PrivacySensitivity> = {
  skill_invocation_frequency: "low",
  source_tier_preference_signals: "medium",
  query_content_telemetry: "forbidden",
};

function formatTrustLabel(value: string): string {
  return value
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatBackendPhrase(value: string): string {
  const cleaned = value
    .replace(/\s*\(§[^)]*\)/g, "")
    .replace(/§\s*[\d.]+/g, "")
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
}

export function formatBudgetLabel(value: string): string {
  return BUDGET_LABELS[value] ?? formatTrustLabel(value);
}

export function formatBudgetDescription(value: string): string {
  return (
    BUDGET_DESCRIPTIONS[value] ??
    "A privacy budget registered by Antiek. The daily limit is shown here."
  );
}

export function sensitivityForBudget(
  category: string,
  epsilon: number,
): PrivacySensitivity {
  if (BUDGET_SENSITIVITY[category]) return BUDGET_SENSITIVITY[category];
  if (epsilon === 0) return "forbidden";
  if (epsilon <= 1.0) return "high";
  if (epsilon <= 2.0) return "medium";
  return "low";
}

export function formatSensitivityLabel(sensitivity: PrivacySensitivity): string {
  if (sensitivity === "forbidden") return "Not collected";
  return sensitivity.charAt(0).toUpperCase() + sensitivity.slice(1);
}

export function formatSystemControl(value: string): string {
  return SYSTEM_CONTROL_LABELS[value] ?? formatBackendPhrase(value);
}

export function formatComplianceLabel(value: string): string {
  return COMPLIANCE_LABELS[value] ?? formatBackendPhrase(value);
}

export function formatTrainingCriterion(value: string): string {
  return TRAINING_CRITERION_LABELS[value] ?? formatTrustLabel(value);
}
