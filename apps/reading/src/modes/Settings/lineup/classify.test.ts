import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  actionSetsForSlot,
  advancedActionSets,
  classifyRole,
  extraActionSets,
} from "./classify";
import {
  GENERAL_SLOTS,
  LIVE_DISPATCH_EXTRAS,
  ROLE_INVENTORY,
} from "./inventory";

const here = dirname(fileURLToPath(import.meta.url));
const CONFIG_YAML = resolve(
  here,
  "../../../../../../substrate/dispatch/config.yaml",
);

function roleTiersKeys(yaml: string): string[] {
  const marker = "\nrole_tiers:\n";
  const start = yaml.indexOf(marker);
  if (start < 0) {
    throw new Error("shipping config.yaml has no role_tiers block");
  }
  const keys: string[] = [];
  for (const line of yaml.slice(start + marker.length).split("\n")) {
    if (line.length === 0) continue;
    if (/^\S/.test(line)) break;
    const match = line.match(/^\s+([A-Za-z_][A-Za-z0-9_]*):/);
    if (match) keys.push(match[1]);
  }
  return keys;
}

describe("shipped classification table", () => {
  it("names the four general categories verbatim", () => {
    expect(GENERAL_SLOTS).toEqual([
      "writer",
      "data miner",
      "data refinement",
      "data verification",
    ]);
  });

  it("classifies every shipping role_tiers key or marks it extra", () => {
    const yaml = readFileSync(CONFIG_YAML, "utf8");
    const keys = roleTiersKeys(yaml);
    expect(keys.length).toBeGreaterThan(0);
    const inventoried = new Set(ROLE_INVENTORY.map((record) => record.role));
    const missing = keys.filter((key) => !inventoried.has(key));
    expect(missing).toEqual([]);
    for (const key of keys) {
      const classification = classifyRole(key);
      expect(
        classification === "extra" ||
          (GENERAL_SLOTS as readonly string[]).includes(classification),
      ).toBe(true);
    }
  });

  it("lists every live dispatch/root_role extra found by the inventory", () => {
    const extras = extraActionSets();
    for (const role of LIVE_DISPATCH_EXTRAS) {
      expect(extras).toContain(role);
      expect(classifyRole(role)).toBe("extra");
    }
    expect(LIVE_DISPATCH_EXTRAS).toEqual(
      expect.arrayContaining([
        "interviewer",
        "wrestler",
        "rlm_orchestrator",
        "visual",
        "transcription",
        "tts",
      ]),
    );
  });

  it("keeps each inventoried role in exactly one bucket", () => {
    const seen = new Set<string>();
    for (const record of ROLE_INVENTORY) {
      expect(seen.has(record.role)).toBe(false);
      seen.add(record.role);
      expect(classifyRole(record.role)).toBe(record.classification);
    }
  });

  it("exposes classified action sets under their general slot", () => {
    for (const slot of GENERAL_SLOTS) {
      const roles = actionSetsForSlot(slot);
      expect(roles.length).toBeGreaterThan(0);
      for (const role of roles) {
        expect(classifyRole(role)).toBe(slot);
      }
    }
  });

  it("advanced action sets include extras plus every classified role", () => {
    const advanced = advancedActionSets();
    expect(advanced).toEqual(ROLE_INVENTORY.map((record) => record.role));
    expect(advanced.some((role) => classifyRole(role) === "extra")).toBe(true);
    expect(advanced).toContain("synthesizer");
    expect(advanced).toContain("thought_partner");
  });
});
