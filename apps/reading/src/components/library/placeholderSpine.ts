/**
 * Deterministic placeholder spine for coverless works. The hash keeps a
 * spine stable across renders (no flicker) without storing a colour, and the
 * families are literal tokens (the --spine-* pairs in tokens.css: glacial /
 * weathered sun / slate) — an unrestricted 360° hash can land on hues that
 * clash with the sun edge and evades the token lint (ui-audit 11-modes-b).
 * BookCard and WorkCard share this so the two shelves never disagree on a
 * placeholder.
 */
const SPINE_GRADIENTS = [
  // glacial — the shelf's blue-grey family
  "linear-gradient(160deg, var(--spine-glacial-a), var(--spine-glacial-b))",
  // weathered sun — the brass/ochre accent family
  "linear-gradient(160deg, var(--spine-sun-a), var(--spine-sun-b))",
  // slate — the night-ramp neutral
  "linear-gradient(160deg, var(--spine-slate-a), var(--spine-slate-b))",
] as const;

export function placeholderSpine(seed: string): string {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) % 360;
  return SPINE_GRADIENTS[h % SPINE_GRADIENTS.length];
}
