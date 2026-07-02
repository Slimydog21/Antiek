import { describe, expect, it } from "vitest";

import { destinationForMode } from "./modeDestinations";
import { MODE_TAXONOMY } from "./workflowTaxonomy";

const mode = (id: string) => {
  const found = MODE_TAXONOMY.find((m) => m.id === id);
  if (!found) throw new Error(`missing mode ${id}`);
  return found;
};

describe("destinationForMode", () => {
  it("opens bare routes directly", () => {
    expect(destinationForMode(mode("Library"))).toBe("/library");
  });

  it("opens param routes through a real index when one exists", () => {
    expect(destinationForMode(mode("Outcomes"))).toBe("/outcomes");
  });

  it("keeps instance-only param routes visible but non-navigable", () => {
    expect(destinationForMode(mode("Reading"))).toBeNull();
    expect(destinationForMode(mode("Replay"))).toBeNull();
  });
});
