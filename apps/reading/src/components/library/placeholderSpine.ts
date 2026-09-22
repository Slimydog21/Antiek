/**
 * Deterministic placeholder spine for coverless works. The hash keeps a
 * spine stable across renders (no flicker) without storing a colour, and the
 * hue space is clamped to token-derived families (glacial / weathered sun /
 * slate) — an unrestricted 360° hash can land on hues that clash with the
 * sun edge and evades the token lint (ui-audit 11-modes-b). BookCard and
 * WorkCard share this so the two shelves never disagree on a placeholder.
 */
const SPINE_GRADIENTS = [
  // glacial — the shelf's blue-grey family
  "linear-gradient(160deg, hsl(205 38% 34%), hsl(214 42% 24%))",
  // weathered sun — the brass/ochre accent family
  "linear-gradient(160deg, hsl(43 48% 32%), hsl(36 52% 22%))",
  // slate — the night-ramp neutral
  "linear-gradient(160deg, hsl(220 20% 32%), hsl(226 24% 22%))",
] as const;

export function placeholderSpine(seed: string): string {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) % 360;
  return SPINE_GRADIENTS[h % SPINE_GRADIENTS.length];
}
