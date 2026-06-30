export function sourcePageNumberFromSectionPath(sectionPath: string | null | undefined): number | null {
  if (!sectionPath) return null;
  const match = sectionPath.trim().match(/^(?:Page|p\.?)\s*(\d+)\b/i);
  if (!match) return null;
  const pageNumber = Number.parseInt(match[1], 10);
  return Number.isFinite(pageNumber) && pageNumber >= 1 ? pageNumber : null;
}

export function sourcePageNumberFromExactSectionPath(sectionPath: string | null | undefined): number | null {
  if (!sectionPath) return null;
  const match = sectionPath.trim().match(/^(?:Page|p\.?)\s*(\d+)$/i);
  if (!match) return null;
  const pageNumber = Number.parseInt(match[1], 10);
  return Number.isFinite(pageNumber) && pageNumber >= 1 ? pageNumber : null;
}

export function zeroBasedReaderPageFromSourcePage(sourcePage: number | null | undefined): number | null {
  if (sourcePage === null || sourcePage === undefined || !Number.isFinite(sourcePage)) return null;
  return Math.max(0, sourcePage - 1);
}
