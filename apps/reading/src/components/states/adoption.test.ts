/**
 * adoption.test.ts — the shared states replace the anonymous "Loading…"
 * (audit-components M9: 19 identical `text-sm text-shadow-1
 * dark:text-moonlight italic` "Loading…" lines, 4.08:1 at night).
 *
 * Each of these ten surfaces now names what is opening through LoadingState.
 * This pins the adoption so a copy-paste of the old recipe fails review.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const src = join(dirname(fileURLToPath(import.meta.url)), "..", "..");

const ADOPTED: Record<string, string> = {
  "modes/ResearchWorkstation/MyResearch.tsx": "Opening your research",
  "modes/Reading/PersonalSpace/index.tsx": "Opening your readings",
  "modes/Library/index.tsx": "Opening the library",
  "components/library/LibraryView.tsx": "Opening the library",
  "modes/DocumentsIndex/index.tsx": "Opening your documents",
  "modes/NotebooksIndex/index.tsx": "Opening your notebooks",
  "modes/InvestigationsIndex/index.tsx": "Opening your research",
  "modes/OutcomesIndex/index.tsx": "Opening the outcomes audit",
  "modes/Outcomes/index.tsx": "Opening the outcome history",
  "modes/Explain/index.tsx": "Opening the explanation",
};

describe("the top ten loading sites name what is opening", () => {
  it.each(Object.entries(ADOPTED))("%s uses LoadingState", (file, label) => {
    const text = readFileSync(join(src, file), "utf8");
    expect(text).not.toMatch(/italic">\s*Loading…\s*</);
    expect(text).toMatch(/import \{[^}]*\bLoadingState\b[^}]*\} from "[./]+components\/states"|from "\.\.\/states"/);
    expect(text).toContain(`label="${label}"`);
  });
});
