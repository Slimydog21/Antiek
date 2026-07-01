export function sourcePageNumberFromSectionPath(sectionPath: string | null | undefined): number | null {
  if (!sectionPath) return null;
  const match = sectionPath.trim().match(/^(?:Page|p\.?)\s*(\d+)(?:\s|$)/i);
  if (!match) return null;
  const pageNumber = Number(match[1]);
  return Number.isSafeInteger(pageNumber) && pageNumber >= 1 ? pageNumber : null;
}

export function sourcePageNumberFromExactSectionPath(sectionPath: string | null | undefined): number | null {
  if (!sectionPath) return null;
  const match = sectionPath.trim().match(/^(?:Page|p\.?)\s*(\d+)$/i);
  if (!match) return null;
  const pageNumber = Number(match[1]);
  return Number.isSafeInteger(pageNumber) && pageNumber >= 1 ? pageNumber : null;
}

export function zeroBasedReaderPageFromSourcePage(sourcePage: number | null | undefined): number | null {
  if (
    sourcePage === null ||
    sourcePage === undefined ||
    !Number.isSafeInteger(sourcePage) ||
    sourcePage < 1
  ) {
    return null;
  }
  return Math.max(0, sourcePage - 1);
}
