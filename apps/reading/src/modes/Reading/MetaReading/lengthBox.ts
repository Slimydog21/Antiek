export type MetaReadingLengthUnit = "pages" | "minutes";

export const META_READING_LENGTH_BOUNDS = {
  pages: { min: 1, max: 60 },
  minutes: { min: 1, max: 120 },
} as const satisfies Record<MetaReadingLengthUnit, { min: number; max: number }>;

export function lengthBoundLabel(unit: MetaReadingLengthUnit): string {
  const bounds = META_READING_LENGTH_BOUNDS[unit];
  return `${bounds.min}-${bounds.max} ${unit}`;
}

export function validateLengthBox(unit: MetaReadingLengthUnit, amount: number): string | null {
  const bounds = META_READING_LENGTH_BOUNDS[unit];
  if (!Number.isFinite(amount) || amount < bounds.min) {
    return `Length must be at least ${bounds.min} ${unit === "pages" ? "page" : "minute"}.`;
  }
  if (!Number.isInteger(amount)) {
    return `Length must be a whole number of ${unit}.`;
  }
  if (amount > bounds.max) {
    return `Length is capped at ${bounds.max} ${unit}.`;
  }
  return null;
}
