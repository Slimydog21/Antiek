/**
 * sectionRef.ts — the ref a Write section tab carries: `section:<id>`.
 * Section tabs are sub-surfaces of a piece, not routes, so the ref
 * deliberately does not start with "/" (activation never navigates to a
 * fabricated URL). Its own module so the title resolver and the tree sync
 * share it without pulling each other.
 */
export const SECTION_REF_PREFIX = "section:";

export function sectionRefOf(sectionId: string): string {
  return `${SECTION_REF_PREFIX}${sectionId}`;
}

export function sectionIdFromRef(ref: string): string | null {
  return ref.startsWith(SECTION_REF_PREFIX) ? ref.slice(SECTION_REF_PREFIX.length) : null;
}
