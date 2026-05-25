/**
 * taxonomy.test.ts — the mechanical guard that keeps workflowTaxonomy.ts
 * from rotting (SPR-04 rigor #3).
 *
 * Three checks:
 *
 *  1. COMPLETENESS. Enumerate the real mode set from the filesystem via
 *     import.meta.glob (NOT a hand-typed list). Every mode must have an
 *     entry in MODE_TAXONOMY. A new mode added later with no entry breaks
 *     the build here. This is the anti-orphan guard.
 *
 *  2. NO STALE ENTRIES. Every taxonomy entry must correspond to a real
 *     mode (the reverse direction) so deletions don't leave dangling
 *     classifications.
 *
 *  3. BUILT-FLAG INTEGRITY. The `built` flag is what the honest-stub
 *     system trusts, so it must reflect reality: every mode marked
 *     `built` must declare a route OR be a registered panel; shared
 *     entries must carry a reason; every entry is mapped exactly once.
 *
 * Run: npx vitest run src/shell/taxonomy.test.ts
 */
import { describe, it, expect } from "vitest";

import { MODE_TAXONOMY, type ModeId } from "./workflowTaxonomy";

/**
 * The real mode set, derived from the filesystem at build time.
 *
 * A "mode" is:
 *   - any directory under src/modes/ that has an index.tsx, EXCEPT
 *     `shared/` (a HeaderBar utility, not a product mode), OR
 *   - the two Write component modes (Write/Editor, Write/Repository),
 *     which are the Write workflow's surfaces and have no index.tsx of
 *     their own.
 *
 * import.meta.glob (eager, just the keys) gives us the index.tsx set
 * mechanically; we layer the two Write modes in explicitly because the
 * Write directory deliberately has no top-level index.tsx.
 */
function discoverModeIds(): Set<ModeId> {
  // Eager glob of every mode index — Vite/Vitest resolve this at build
  // time, so adding a new mode dir changes this set without code edits.
  const indexModules = import.meta.glob("../modes/*/index.tsx");
  const ids = new Set<ModeId>();
  for (const path of Object.keys(indexModules)) {
    // "../modes/ResearchWorkstation/index.tsx" → "ResearchWorkstation"
    const m = path.match(/\.\.\/modes\/([^/]+)\/index\.tsx$/);
    if (!m) continue;
    const dir = m[1];
    if (dir === "shared") continue; // utility, not a mode
    ids.add(dir);
  }

  // The Write workflow's two component modes — present as components,
  // no index.tsx. Discover them by globbing their entry components so
  // this stays mechanical (renaming/removing them breaks here too).
  const writeModules = import.meta.glob([
    "../modes/Write/Editor/Editor.tsx",
    "../modes/Write/Repository/Repository.tsx",
  ]);
  for (const path of Object.keys(writeModules)) {
    const m = path.match(/\.\.\/modes\/(Write\/[^/]+)\//);
    if (m) ids.add(m[1]);
  }

  return ids;
}

describe("workflowTaxonomy completeness (SPR-04 rigor #3)", () => {
  const discovered = discoverModeIds();
  const taxonomyIds = new Set(MODE_TAXONOMY.map((m) => m.id));

  it("discovers a non-trivial mode set from the filesystem", () => {
    // Guard against the glob silently returning nothing (which would
    // make every other check vacuously pass).
    expect(discovered.size).toBeGreaterThan(30);
  });

  it("maps EVERY discovered mode (no orphan escapes classification)", () => {
    const unmapped = [...discovered].filter((id) => !taxonomyIds.has(id));
    expect(
      unmapped,
      `These modes exist under src/modes/ but are missing from MODE_TAXONOMY. ` +
        `Classify each into research/read/write/speak or shared (with a reason), ` +
        `or flag it as an orphan for a retirement decision — do NOT leave it ` +
        `unmapped: ${JSON.stringify(unmapped)}`,
    ).toEqual([]);
  });

  it("has no stale taxonomy entries (every entry is a real mode)", () => {
    const stale = [...taxonomyIds].filter((id) => !discovered.has(id));
    expect(
      stale,
      `These taxonomy entries reference modes that no longer exist on disk: ` +
        `${JSON.stringify(stale)}`,
    ).toEqual([]);
  });

  it("maps each mode exactly once", () => {
    const counts = new Map<ModeId, number>();
    for (const m of MODE_TAXONOMY) {
      counts.set(m.id, (counts.get(m.id) ?? 0) + 1);
    }
    const dupes = [...counts.entries()].filter(([, n]) => n > 1).map(([id]) => id);
    expect(dupes, `Duplicated taxonomy entries: ${JSON.stringify(dupes)}`).toEqual(
      [],
    );
  });
});

describe("workflowTaxonomy built-flag + shared-bucket integrity", () => {
  it("every built mode declares a route (its build-presence signal)", () => {
    // A mode marked built must be reachable. In this app the canonical
    // reachability signal is a route in App.tsx. Panel-only modes that
    // are 'built' would carry no route — none currently do, but if one is
    // added it must opt out of this check explicitly. Keeping the check
    // strict means `built:true` can never silently mean "I think it's
    // done" — it means "the operator can get to it".
    const builtWithoutRoute = MODE_TAXONOMY.filter(
      (m) => m.built && !m.route,
    ).map((m) => m.id);
    expect(
      builtWithoutRoute,
      `Modes marked built:true but with no route — build-presence is then ` +
        `unverifiable and the honest-stub system can't trust the flag: ` +
        `${JSON.stringify(builtWithoutRoute)}`,
    ).toEqual([]);
  });

  it("every shared entry carries a one-line reason (no orphan hiding)", () => {
    const sharedNoReason = MODE_TAXONOMY.filter(
      (m) => m.workflow === "shared" && !m.sharedReason,
    ).map((m) => m.id);
    expect(
      sharedNoReason,
      `Shared-bucket entries without a sharedReason. The shared bucket must ` +
        `not be used to hide an orphan — state why each is cross-cutting: ` +
        `${JSON.stringify(sharedNoReason)}`,
    ).toEqual([]);
  });

  it("only the four product workflows + shared exist", () => {
    const valid = new Set(["research", "read", "write", "speak", "shared"]);
    const bad = MODE_TAXONOMY.filter((m) => !valid.has(m.workflow)).map(
      (m) => `${m.id}→${m.workflow}`,
    );
    expect(bad, `Entries with an invalid workflow: ${JSON.stringify(bad)}`).toEqual(
      [],
    );
  });
});
