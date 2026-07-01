import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

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

import {
  MODE_TAXONOMY,
  WORKFLOWS,
  landingModeForWorkflow,
  modeById,
  workflowForPath,
  type ModeId,
} from "./workflowTaxonomy";
import { OPERATOR_ROUTES } from "./operatorRoutes";

const _here = dirname(fileURLToPath(import.meta.url));
const readSrc = (rel: string): string =>
  readFileSync(resolve(_here, "..", rel), "utf-8")
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, "")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:])\/\/[^\n]*/g, "$1");

const operatorRoutePaths = (): Set<string> =>
  new Set(OPERATOR_ROUTES.map((route) => route.path));

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

describe("Sprint 25+ economics dashboard route integrity", () => {
  const dashboards = [
    {
      id: "AdvertiserConsole",
      route: "/operator/advertiser-campaigns",
      component: "AdvertiserConsole",
      sharedReason: /operator-only/i,
    },
    {
      id: "PayoutDashboard",
      route: "/operator/payouts/dashboard",
      component: "PayoutDashboard",
      sharedReason: /read-only/i,
    },
    {
      id: "CreatorPayouts",
      route: "/me/payouts",
      component: "CreatorPayouts",
      sharedReason: /read-only/i,
    },
    {
      id: "MarketplaceMetrics",
      route: "/marketplace",
      component: "MarketplaceMetrics",
      sharedReason: /read-only/i,
    },
  ] as const;

  it("marks backend-backed dashboards as built shared surfaces with production routes", () => {
    for (const dashboard of dashboards) {
      const entry = modeById(dashboard.id);
      expect(entry, `${dashboard.id} taxonomy entry`).toBeDefined();
      expect(entry?.workflow).toBe("shared");
      expect(entry?.built).toBe(true);
      expect(entry?.route).toBe(dashboard.route);
      expect(entry?.sharedReason).toMatch(dashboard.sharedReason);
    }
  });

  it("mounts each built economics dashboard in App.tsx", () => {
    const app = readSrc("App.tsx");
    for (const dashboard of dashboards) {
      expect(app).toContain(`import ${dashboard.component} from "./modes/${dashboard.component}"`);
      expect(app).toContain(
        `<Route path="${dashboard.route}" element={<${dashboard.component} />} />`,
      );
    }
  });

  it("lists each dashboard in operator discovery surfaces", () => {
    const routes = operatorRoutePaths();
    for (const dashboard of dashboards) {
      expect(routes, `operator discovery must list ${dashboard.route}`).toContain(
        dashboard.route,
      );
    }
  });

  it("keeps trust and privacy discovery copy user-facing", () => {
    const routes = operatorRoutePaths();
    const routeRegistry = readSrc("shell/operatorRoutes.ts");
    const settings = readSrc("modes/Settings/index.tsx");
    const taxonomy = readSrc("shell/workflowTaxonomy.ts");
    const paletteStories = readSrc("components/CommandPalette.stories.tsx");
    const discoveryCopy = [
      routeRegistry,
      settings,
      taxonomy,
      paletteStories,
    ].join("\n");

    expect(discoveryCopy).toContain("Privacy budgets and deletion controls");
    expect(discoveryCopy).toContain(
      "Published privacy, deletion, and training commitments",
    );
    expect(discoveryCopy).not.toMatch(/ε exposure|delete-all|deletion SLA|DP budget/i);
    expect(discoveryCopy).not.toMatch(/Substrate-level operations snapshot/i);
    expect(discoveryCopy).not.toMatch(/\(\/privacy\)|\(\/trust\)/i);

    for (const route of ["/privacy", "/trust"]) {
      expect(routes, `operator discovery must list ${route}`).toContain(route);
    }

    expect(modeById("PrivacyDashboard")?.label).toBe("Privacy dashboard");
  });

  it("keeps CommandPalette and Application map route indexes in parity", () => {
    const app = readSrc("App.tsx");
    const map = readSrc("modes/Map/index.tsx");
    const palette = readSrc("components/CommandPalette.tsx");
    const routes = operatorRoutePaths();
    const pinnedMountedRoutes = [
      "/home",
      "/deep-research",
      "/write",
      "/library",
      "/library/browse",
      "/readings",
      "/meta-readings",
      "/read/meta-reading",
      "/biography",
      "/settings",
      "/coordination",
      "/coordination/cost-consent",
      "/map",
      "/cross-graph/citations",
    ];

    expect(map).toContain("operatorRouteGroups");
    expect(palette).toContain("OPERATOR_ROUTES");

    for (const route of [...routes]) {
      expect(app, `App.tsx must mount discovery route ${route}`).toContain(
        `<Route path="${route}"`,
      );
    }

    for (const route of pinnedMountedRoutes) {
      expect(routes, `operator discovery must list ${route}`).toContain(route);
    }

    expect(OPERATOR_ROUTES.find((route) => route.id === "home")?.workflow).toBe("shared");
  });

  it("keeps CreatorPayouts on the scoped /me/payouts contract", () => {
    const app = readSrc("App.tsx");
    const component = readSrc("modes/CreatorPayouts/index.tsx");
    const creator = modeById("CreatorPayouts");
    expect(creator?.built).toBe(true);
    expect(creator?.route).toBe("/me/payouts");
    expect(creator?.sharedReason).toMatch(/scoped/i);
    expect(app).toContain('<Route path="/me/payouts" element={<CreatorPayouts />} />');
    expect(component).toContain('apiFetch("/me/payouts")');
    expect(component).not.toContain("/creator-payouts/");
  });

  it("keeps AdvertiserConsole on the operator-only campaign contract", () => {
    const component = readSrc("modes/AdvertiserConsole/index.tsx");
    const advertiser = modeById("AdvertiserConsole");
    expect(advertiser?.built).toBe(true);
    expect(advertiser?.route).toBe("/operator/advertiser-campaigns");
    expect(advertiser?.sharedReason).toMatch(/operator-only/i);
    expect(component).toContain('apiFetch("/operator/advertiser-campaigns")');
    expect(component).not.toContain("/advertiser-self-service");
  });

  it("keeps Federation on the canonical federation config API", () => {
    const app = readSrc("App.tsx");
    const component = readSrc("modes/Federation/index.tsx");
    const federation = modeById("Federation");
    expect(federation?.built).toBe(true);
    expect(federation?.route).toBe("/federation");
    expect(federation?.sharedReason).toMatch(/cross-substrate/i);
    expect(app).toContain('<Route path="/federation" element={<Federation />} />');
    expect(component).toContain('apiFetch("/federation/config")');
    expect(component).not.toContain("/cross-graph/federation-config");
  });
});

/**
 * Read SPR-06 — the door re-home + operator-surface eviction, pinned so a
 * future nav change can't silently revert them (rigor #5, defensibility).
 */
describe("Read door re-home + operator-surface eviction (Read SPR-06)", () => {
  it("the Read door opens on the Library, not the PDF wrestler", () => {
    // The load-bearing claim: clicking the Read rail door (NavRail navigates
    // WORKFLOWS.read.defaultRoute) lands on the Library shelf — never /wrestle.
    expect(WORKFLOWS.read.defaultRoute).toBe("/library");
    expect(WORKFLOWS.read.defaultRoute).not.toBe("/wrestle");
  });

  it("the Read landing surface resolves to the Library (ThreadJump + stub agree)", () => {
    // landingModeForWorkflow is the single source ThreadJump uses; it must
    // agree with the door so the re-home holds everywhere, not just on the rail.
    const landing = landingModeForWorkflow("read");
    expect(landing?.id).toBe("Library");
    expect(landing?.route).toBe("/library");
  });

  it("the PDF wrestler stays reachable (a demoted Read power surface), just not the door", () => {
    const wrestle = modeById("WrestleApp");
    expect(wrestle?.workflow).toBe("read"); // still Read — it IS reading
    expect(wrestle?.built).toBe(true);
    expect(wrestle?.route).toBe("/wrestle");
    expect(WORKFLOWS.read.defaultRoute).not.toBe(wrestle?.route); // not the door
  });

  it("DocumentsIndex + Sources are evicted out of the Read door into shared/More", () => {
    for (const id of ["DocumentsIndex", "Sources"]) {
      const m = modeById(id);
      expect(m, `${id} must still exist`).toBeDefined();
      // Re-classed to shared (the More bucket) — no longer a Read-door surface.
      expect(m?.workflow, `${id} must move out of the Read workflow`).toBe("shared");
      // Code/route untouched — capability preserved, reachable via More + ⌘K.
      expect(m?.built).toBe(true);
      expect(m?.route).toBeTruthy();
      // Shared entries must say why (the test elsewhere enforces this too).
      expect(m?.sharedReason).toBeTruthy();
    }
  });

  it("the evicted surfaces no longer set the Read rail active (off the Read door)", () => {
    // workflowForPath drives the active-rail highlight. An operator on
    // /documents or /sources is in the shared bucket, not on the Read door.
    expect(workflowForPath("/documents")).toBe("shared");
    expect(workflowForPath("/sources")).toBe("shared");
    // And the Read door itself resolves to read.
    expect(workflowForPath("/library")).toBe("read");
  });
});

/**
 * Read SPR-13 M4 — the Meta-docs tab sits AFTER the Library as a Read noun, and
 * the personal-space surfaces are Read-workflow destinations. Pinned so a future
 * nav change can't silently drop the tab or mis-classify the surfaces.
 */
describe("Read personal space + meta-docs tab (Read SPR-13 M4)", () => {
  it("Meta-docs is a Read noun, declared AFTER Library", () => {
    const nouns = WORKFLOWS.read.nouns;
    const libraryIdx = nouns.indexOf("Library");
    const metaIdx = nouns.indexOf("Meta-docs");
    expect(libraryIdx).toBeGreaterThanOrEqual(0);
    expect(metaIdx).toBeGreaterThan(libraryIdx);
  });

  it("the personal-space + meta-docs routes resolve to the Read workflow (active rail)", () => {
    expect(workflowForPath("/readings")).toBe("read");
    expect(workflowForPath("/meta-readings")).toBe("read");
    expect(workflowForPath("/read/meta-reading/mr-abc")).toBe("read");
    // The book reader stays Read too; /readings must NOT be mistaken for it.
    expect(workflowForPath("/read/doc-1")).toBe("read");
  });
});

/**
 * Write SPR-07 — the door re-home, pinned so a future nav change can't
 * silently revert it (rigor #5, defensibility). Mirrors the Read SPR-06
 * pattern: the door opens on the real lego-block loop, the legacy studio is
 * demoted but reachable.
 */
describe("Write door re-home (Write SPR-07)", () => {
  it("the Write door opens on the real loop (/write), not the legacy studio (/create)", () => {
    // Clicking the Write rail door navigates WORKFLOWS.write.defaultRoute; it
    // must land on WriteHome (the blocks → outline → generate → edit loop),
    // never the CreationStudio "select or create a deliverable" dead-end.
    expect(WORKFLOWS.write.defaultRoute).toBe("/write");
    expect(WORKFLOWS.write.defaultRoute).not.toBe("/create");
  });

  it("the Write landing surface resolves on /write (ThreadJump + stub agree)", () => {
    // landingModeForWorkflow is the single source ThreadJump uses; it must
    // agree with the door so the re-home holds everywhere, not just on the rail.
    const landing = landingModeForWorkflow("write");
    expect(landing?.workflow).toBe("write");
    expect(landing?.route).toBe("/write");
  });

  it("the Write component modes (Repository, Editor) are mounted on the door", () => {
    for (const id of ["Write/Repository", "Write/Editor"]) {
      const m = modeById(id);
      expect(m, `${id} must exist`).toBeDefined();
      expect(m?.workflow).toBe("write");
      // Now reachable (mounted inside WriteHome) — built + on the door route.
      expect(m?.built, `${id} must be built (mounted in WriteHome)`).toBe(true);
      expect(m?.route).toBe("/write");
    }
  });

  it("the legacy CreationStudio stays reachable (a demoted power surface), just not the door", () => {
    const studio = modeById("CreationStudio");
    expect(studio?.workflow).toBe("write"); // still Write — it IS writing
    expect(studio?.built).toBe(true);
    expect(studio?.route).toBe("/create");
    expect(WORKFLOWS.write.defaultRoute).not.toBe(studio?.route); // not the door
  });

  it("the Write door resolves to write (active-rail state)", () => {
    expect(workflowForPath("/write")).toBe("write");
    expect(workflowForPath("/write/dlv-123")).toBe("write");
    // The demoted studio still belongs to write (reachable), just off the door.
    expect(workflowForPath("/create")).toBe("write");
  });
});

/**
 * Research SPR-05 — ONE MONITOR. The old flat InvestigationsIndex is folded
 * into MyResearch, preserving list/status/cost/replay without re-opening a
 * second discovery door.
 */
describe("Research one-monitor consolidation (Research SPR-05)", () => {
  it("the retired /investigations door is not advertised from Map", () => {
    const routes = operatorRoutePaths();
    expect(routes).not.toContain("/investigations");
    expect(routes).toContain("/my-research");
  });

  it("InvestigationsIndex points at the canonical MyResearch route", () => {
    const m = modeById("InvestigationsIndex");
    expect(m?.workflow).toBe("research");
    expect(m?.built).toBe(true);
    expect(m?.route).toBe("/my-research");
    expect(m?.route).not.toBe("/investigations");
  });
});

/**
 * Speak SPR-08 — ONE DOOR. The duplicate Interview surface is folded into
 * Speak (mirrors the SPR-05 InvestigationsIndex fold). Pinned so a future nav
 * change can't silently re-create a second door to interview-as-acquisition.
 */
describe("Speak one-door consolidation (Speak SPR-08)", () => {
  it("there is exactly one Speak door — /speak", () => {
    expect(WORKFLOWS.speak.defaultRoute).toBe("/speak");
    expect(WORKFLOWS.speak.defaultRoute).not.toBe("/interviews");
  });

  it("the Interview surfaces fold into Speak (capability preserved, no second door)", () => {
    for (const id of ["Interview", "InterviewIndex"]) {
      const m = modeById(id);
      expect(m, `${id} must still exist (capability preserved)`).toBeDefined();
      expect(m?.workflow).toBe("speak"); // still Speak — it IS Speak
      expect(m?.built).toBe(true); // reachable…
      expect(m?.route).toBe("/speak"); // …because it folds into the one door
      // The old standalone doors are no longer the route for these surfaces.
      expect(m?.route).not.toBe("/interviews");
      expect(m?.route).not.toBe("/interview/:interviewId");
    }
  });

  it("the Speak landing resolves to the home, and /speak resolves to speak", () => {
    const landing = landingModeForWorkflow("speak");
    expect(landing?.route).toBe("/speak");
    expect(workflowForPath("/speak")).toBe("speak");
    expect(workflowForPath("/speak/p-123")).toBe("speak");
  });

  it("shared discovery does not re-advertise the retired /interviews door", () => {
    const routes = operatorRoutePaths();
    const chrome = readSrc("shell/SceneChrome.tsx");
    expect(routes).not.toContain("/interviews");
    expect(routes).toContain("/speak");
    expect(chrome).not.toContain('to: "/interviews"');
    expect(chrome).toContain('to: "/speak"');
  });
});
