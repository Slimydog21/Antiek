import { readdirSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { describe, it, expect } from "vitest";

import {
  WORKFLOW_TAXONOMY,
  WORKFLOWS,
  workflowForRoute,
  WORKFLOW_HOME,
  modesForWorkflow,
} from "./workflowTaxonomy";

/**
 * Completeness check (SPR-02). Enumerates the REAL mode directories from the
 * filesystem — not a hand-written list — so the taxonomy cannot rot: add a
 * mode and forget to classify it, and this test goes red. The functional
 * standard ("nothing exists in the product without a stated job") is kept by
 * CI, not by vigilance.
 */
const modesDir = resolve(dirname(fileURLToPath(import.meta.url)), "../modes");

function realModeDirs(): string[] {
  if (!existsSync(modesDir)) return [];
  return readdirSync(modesDir, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => d.name);
}

describe("workflowTaxonomy — completeness", () => {
  const dirs = realModeDirs();

  it("finds the mode directories (sanity)", () => {
    expect(dirs.length).toBeGreaterThan(0);
  });

  it("maps every real mode directory exactly once", () => {
    const unmapped = dirs.filter((d) => !(d in WORKFLOW_TAXONOMY));
    expect(unmapped, `unmapped modes — classify them in workflowTaxonomy.ts: ${unmapped.join(", ")}`).toEqual([]);
  });

  it("has no phantom entries (taxonomy ⊆ real dirs)", () => {
    const phantom = Object.keys(WORKFLOW_TAXONOMY).filter((id) => !dirs.includes(id));
    expect(phantom, `taxonomy references non-existent modes: ${phantom.join(", ")}`).toEqual([]);
  });

  it("assigns every entry a valid workflow", () => {
    const valid = new Set(["research", "read", "write", "speak", "shared"]);
    for (const [id, e] of Object.entries(WORKFLOW_TAXONOMY)) {
      expect(valid.has(e.workflow), `${id} has invalid workflow ${e.workflow}`).toBe(true);
      expect(e.reason.length, `${id} missing a reason`).toBeGreaterThan(0);
    }
  });

  it("gives each of the four workflows at least one mode", () => {
    for (const w of WORKFLOWS) {
      expect(modesForWorkflow(w).length, `${w} has no modes`).toBeGreaterThan(0);
    }
  });
});

describe("workflowTaxonomy — route derivation", () => {
  it("derives the active workflow from representative routes", () => {
    expect(workflowForRoute("/")).toBe("research");
    expect(workflowForRoute("/inv/web-gaming-2026")).toBe("research");
    expect(workflowForRoute("/wrestle/nilo-deck")).toBe("research");
    expect(workflowForRoute("/documents")).toBe("read");
    expect(workflowForRoute("/notebook/abc")).toBe("read");
    expect(workflowForRoute("/create")).toBe("write");
    expect(workflowForRoute("/interviews")).toBe("speak");
  });

  it("returns null for shared/operator routes (no active workflow)", () => {
    expect(workflowForRoute("/billing")).toBeNull();
    expect(workflowForRoute("/settings")).toBeNull();
    expect(workflowForRoute("/trust")).toBeNull();
  });

  it("every workflow home routes back to that workflow", () => {
    for (const w of WORKFLOWS) {
      expect(workflowForRoute(WORKFLOW_HOME[w])).toBe(w);
    }
  });
});
