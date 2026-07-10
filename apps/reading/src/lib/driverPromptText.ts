/**
 * driverPromptText — pure helpers for DecisionTreeDriverBadge + budget panels.
 *
 * Residual (qr): keep soft-budget projection and driver badge foresight on the
 * same prompt text (selection/question + optional publication refs). Never
 * invents content; empty parts are omitted.
 */

/**
 * Compose operator prompt text with optional knowledge-dense publication refs
 * for cost projection honesty (badge ≡ budget panel).
 */
export function composeDriverPromptText(
  body: string,
  pubRefs?: string | null,
): string {
  const main = String(body || "").trim();
  const refs = String(pubRefs || "").trim();
  if (main && refs) return `${main}\n\nPublication refs:\n${refs}`;
  if (main) return main;
  if (refs) return `Publication refs:\n${refs}`;
  return "";
}
